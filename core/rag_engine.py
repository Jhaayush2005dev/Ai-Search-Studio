import os
import time
import threading
from typing import List, Dict, Any, Generator, Optional, Callable
from pathlib import Path

from langchain_mistralai import ChatMistralAI, MistralAIEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.documents import Document

from core.config import MISTRAL_API_KEY, DEFAULT_MODEL, EMBEDDING_MODEL, CHROMA_DIR, is_internet_available
from core.web_service import WebService

class RAGEngine:
    """Core RAG, vector store, and AI inference engine with real-time streaming and rate-limit resilience."""

    def __init__(self, api_key: str = MISTRAL_API_KEY, model_name: str = DEFAULT_MODEL):
        self.api_key = api_key
        self.model_name = model_name
        self.temperature = 0.3
        self.search_mode = "Auto (Hybrid)" # "Auto (Hybrid)", "Docs Only", "Web Only"
        self.context_depth = 4
        self.max_memory_turns = 4

        self.chat_history: List[Any] = []
        self.active_sources_meta: List[Dict[str, Any]] = []
        self.vector_store: Optional[Chroma] = None
        self.web_service = WebService(max_results=4)

        self._is_generating = False
        self._abort_generation = False

        self._init_models()

    def _init_models(self):
        if not self.api_key:
            return
        try:
            self.embeddings = MistralAIEmbeddings(
                model=EMBEDDING_MODEL,
                api_key=self.api_key
            )
        except Exception as e:
            print(f"Embedding init warning: {e}")
            self.embeddings = None

        try:
            self.model = ChatMistralAI(
                model=self.model_name,
                api_key=self.api_key,
                temperature=self.temperature,
                max_retries=2
            )
        except Exception as e:
            print(f"Model init warning: {e}")
            self.model = None

    def set_model(self, model_name: str):
        self.model_name = model_name
        self._init_models()

    def set_temperature(self, temp: float):
        self.temperature = temp
        self._init_models()

    def set_search_mode(self, mode: str):
        self.search_mode = mode

    def set_context_depth(self, depth: int):
        self.context_depth = depth

    def stop_generation(self):
        self._abort_generation = True
        self._is_generating = False

    # ==========================================
    # VECTOR STORE MANAGEMENT
    # ==========================================
    def init_vector_store(self, default_docs: Optional[List[Document]] = None):
        """Initializes Chroma DB with existing or default documents."""
        if not is_internet_available():
            return False, "Offline: Cannot reach Mistral embedding API."

        try:
            if default_docs:
                self.vector_store = Chroma.from_documents(
                    documents=default_docs,
                    embedding=self.embeddings,
                    persist_directory=str(CHROMA_DIR)
                )
            else:
                self.vector_store = Chroma(
                    persist_directory=str(CHROMA_DIR),
                    embedding_function=self.embeddings
                )
            return True, "Vector engine online."
        except Exception as e:
            return False, f"Chroma DB init error: {str(e)}"

    def add_documents(self, documents: List[Document], meta_list: List[Dict[str, Any]]):
        """Ingests new document chunks into Chroma vector store."""
        if not self.vector_store:
            self.vector_store = Chroma.from_documents(
                documents=documents,
                embedding=self.embeddings,
                persist_directory=str(CHROMA_DIR)
            )
        else:
            self.vector_store.add_documents(documents)

        for meta in meta_list:
            existing = next((m for m in self.active_sources_meta if m["filename"] == meta["filename"]), None)
            if existing:
                existing["chunks"] += meta["chunks"]
            else:
                self.active_sources_meta.append(meta)

    def delete_source(self, filename: str) -> bool:
        """Removes all chunks belonging to a specific source from vector store."""
        if not self.vector_store:
            return False
        try:
            db_data = self.vector_store.get(where={"source": filename})
            ids_to_delete = db_data.get("ids", [])
            if ids_to_delete:
                self.vector_store.delete(ids=ids_to_delete)

            self.active_sources_meta = [m for m in self.active_sources_meta if m["filename"] != filename]
            return True
        except Exception as e:
            print(f"Delete source error: {e}")
            return False

    def clear_knowledge_base(self):
        """Clears all vectors and memory."""
        try:
            if self.vector_store:
                self.vector_store.delete_collection()
                self.vector_store = None
            self.active_sources_meta = []
            return True
        except Exception as e:
            print(f"Clear DB error: {e}")
            return False

    def get_knowledge_stats(self) -> Dict[str, Any]:
        total_chunks = sum(m.get("chunks", 0) for m in self.active_sources_meta)
        total_size_kb = sum(m.get("size_kb", 0) for m in self.active_sources_meta)
        return {
            "total_files": len(self.active_sources_meta),
            "total_chunks": total_chunks,
            "total_size_kb": round(total_size_kb, 1),
            "sources": self.active_sources_meta
        }

    # ==========================================
    # STREAMING INFERENCE WITH 429 AUTO-RETRY & FALLBACK
    # ==========================================
    def stream_query(
        self,
        query: str,
        token_callback: Callable[[str], None],
        source_callback: Optional[Callable[[List[str]], None]] = None,
        status_callback: Optional[Callable[[str], None]] = None
    ) -> str:
        """
        Executes query retrieval, prompt synthesis, and live token streaming
        with automatic 429 rate limit backoff and graceful fallback.
        """
        self._is_generating = True
        self._abort_generation = False
        full_response = []
        citations = []

        if not is_internet_available():
            msg = "⚠️ Network offline: Cannot connect to AI model or web."
            token_callback(msg)
            return msg

        try:
            # 1. Retrieve Context
            local_context = ""
            retrieved_docs = []

            if self.search_mode in ["Auto (Hybrid)", "Docs Only"] and self.vector_store:
                if status_callback:
                    status_callback("🔍 Searching vector database...")
                try:
                    retrieved_docs = self.vector_store.similarity_search(query, k=self.context_depth)
                    if retrieved_docs:
                        context_parts = []
                        for doc in retrieved_docs:
                            src = doc.metadata.get("source", "Document")
                            citations.append(src)
                            # Keep each snippet concise to reduce token count
                            content = doc.page_content.strip()
                            if len(content) > 1500:
                                content = content[:1500] + "..."
                            context_parts.append(f"--- SOURCE: {src} ---\n{content}")
                        local_context = "\n\n".join(context_parts)
                except Exception as e:
                    print(f"Vector search warning: {e}")

            citations = list(dict.fromkeys(citations))

            # 2. Check if Web Search is needed
            need_web_search = (self.search_mode == "Web Only")
            if self.search_mode == "Auto (Hybrid)":
                if not local_context or len(local_context.strip()) < 40:
                    need_web_search = True

            web_context = ""
            if need_web_search:
                if status_callback:
                    status_callback("🌐 Querying live web search...")
                web_results = self.web_service.search_text(query)
                web_context = f"\n--- LIVE WEB RESULTS ---\n{web_results}\n"
                citations.append("DuckDuckGo Web Search")

            if source_callback and citations:
                source_callback(citations)

            # 3. Construct System Prompt
            system_prompt = f"""You are a helpful, concise AI Knowledge Assistant.
Answer the user's question clearly based on the context below. If answering from documents or web search, highlight key facts.

{f'=== LOCAL DOCUMENTS CONTEXT ===' if local_context else ''}
{local_context}

{f'=== LIVE WEB SEARCH CONTEXT ===' if web_context else ''}
{web_context}
"""
            messages = [SystemMessage(content=system_prompt)]

            if self.chat_history:
                recent_history = self.chat_history[-(self.max_memory_turns * 2):]
                messages.extend(recent_history)

            messages.append(HumanMessage(content=query))

            if status_callback:
                status_callback("⚡ Generating response...")

            # 4. Stream with Exponential Backoff & Fallback Models on Rate Limits
            success = False
            attempts = 0
            max_attempts = 3
            current_model_instance = self.model

            fallback_models = ["open-mistral-7b", "mistral-small-latest"]

            while attempts < max_attempts and not success:
                attempts += 1
                try:
                    if not current_model_instance:
                        current_model_instance = ChatMistralAI(
                            model=self.model_name,
                            api_key=self.api_key,
                            temperature=self.temperature
                        )

                    for chunk in current_model_instance.stream(messages):
                        if self._abort_generation:
                            token_callback("\n\n*[Generation stopped by user]*")
                            break

                        content = chunk.content
                        if content:
                            full_response.append(content)
                            token_callback(content)

                    success = True
                    break

                except Exception as e:
                    err_str = str(e).lower()
                    is_rate_limit = ("429" in err_str or "rate limit" in err_str or "rate_limited" in err_str)

                    if is_rate_limit and attempts < max_attempts:
                        delay = attempts * 2 # 2s, 4s
                        if status_callback:
                            status_callback(f"⏳ Rate limit hit. Retrying in {delay}s...")
                        time.sleep(delay)

                        # Try fallback model on second retry
                        if attempts == 2:
                            for fb in fallback_models:
                                if fb != self.model_name:
                                    if status_callback:
                                        status_callback(f"🔄 Switching to fallback model ({fb})...")
                                    current_model_instance = ChatMistralAI(
                                        model=fb,
                                        api_key=self.api_key,
                                        temperature=self.temperature
                                    )
                                    break
                    else:
                        # Non-retryable error or all retries exhausted
                        raise e

            final_text = "".join(full_response).strip()

            if final_text and not self._abort_generation:
                self.chat_history.append(HumanMessage(content=query))
                self.chat_history.append(AIMessage(content=final_text))

            return final_text

        except Exception as e:
            err_str = str(e)
            is_rate_limit = ("429" in err_str or "rate limit" in err_str.lower() or "rate_limited" in err_str.lower())

            if is_rate_limit:
                # Provide a clean, helpful fallback extract rather than raw JSON
                fallback_info = ""
                if local_context:
                    fallback_info += f"\n\n**📄 Relevant Document Passages Found:**\n{local_context[:800]}..."
                if web_context:
                    fallback_info += f"\n\n**🌐 Live Web Search Results:**\n{web_context[:800]}..."

                user_friendly_msg = (
                    "⚠️ **Mistral API Rate Limit (429) Reached**\n\n"
                    "Your Mistral API free-tier request quota was temporarily exceeded.\n"
                    f"{fallback_info}\n\n"
                    "---\n"
                    "💡 **Tips to continue:**\n"
                    "• Wait **5 to 10 seconds** and ask again.\n"
                    "• Switch the **AI Model** in the sidebar to `open-mistral-7b` (higher free tier throughput).\n"
                    "• Reduce **Retrieval Depth** slider in the sidebar."
                )
                token_callback(user_friendly_msg)
                return user_friendly_msg
            else:
                err_msg = f"❌ **AI Service Notice:** {err_str}"
                token_callback(err_msg)
                return err_msg

        finally:
            self._is_generating = False
            self._abort_generation = False

    # ==========================================
    # QUICK ONE-CLICK AI TOOLS
    # ==========================================
    def generate_summary(self, token_callback: Callable[[str], None], status_callback: Callable[[str], None]):
        query = "Provide a comprehensive, structured executive summary of all the uploaded documents. Include main topics, key facts, takeaways, and bullet points."
        return self.stream_query(query, token_callback, status_callback=status_callback)

    def generate_quiz(self, token_callback: Callable[[str], None], status_callback: Callable[[str], None]):
        query = "Generate an interactive 5-question study quiz (with multiple choice and short answer questions) based strictly on the uploaded knowledge base. Include an Answer Key and Explanations at the bottom."
        return self.stream_query(query, token_callback, status_callback=status_callback)

    def generate_key_takeaways(self, token_callback: Callable[[str], None], status_callback: Callable[[str], None]):
        query = "Extract the top 5 to 7 key insights, actionable takeaways, and critical definitions from the available documents."
        return self.stream_query(query, token_callback, status_callback=status_callback)
