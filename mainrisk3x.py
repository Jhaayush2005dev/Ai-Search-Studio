import os
import sys
import time
import socket
import threading
import webbrowser
import urllib.parse
from pathlib import Path
import customtkinter as ctk
from tkinter import filedialog, messagebox
from dotenv import load_dotenv

# Voice Recognition Import
import speech_recognition as sr

# LangChain Imports
from langchain_mistralai import ChatMistralAI, MistralAIEmbeddings
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma 
from langchain_core.messages import HumanMessage
from langchain_core.documents import Document

# Keyless Web Search Import
from langchain_community.utilities import DuckDuckGoSearchAPIWrapper

# Image Processing Imports
from PIL import Image
import pytesseract

# --- Path config for Windows Tesseract (Adjust if yours is installed elsewhere) ---
if os.name == 'nt':
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# --- Pre-flight Checks ---
load_dotenv(override=True)
api_key = os.getenv("MISTRAL_API_KEY")

if not api_key:
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror("Error", "MISTRAL_API_KEY not found in .env")
    sys.exit(1)

root_path = Path(__file__).resolve().parent
docs_folder = root_path / "documents loaders"
os.makedirs(docs_folder, exist_ok=True) 

pdf_path = docs_folder / "a.pdf"
notes_path = docs_folder / "notes.txt"

ctk.set_appearance_mode("dark")  
ctk.set_default_color_theme("blue")  

# --- Network Check Utility ---
def is_internet_available():
    try:
        # Attempt to connect to a reliable DNS server
        socket.create_connection(("8.8.8.8", 53), timeout=2)
        return True
    except OSError:
        return False

class ImmersiveQAApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Universal Document & Web Knowledge Assistant")
        self.geometry("1000x750")
        self.minsize(800, 600)
        
        self.vector_store = None
        self.model = ChatMistralAI(model="mistral-small-2506", api_key=api_key)
        self.embeddings = MistralAIEmbeddings(model="mistral-embed", api_key=api_key)
        self.loaded_files_status = []

        # Voice Search State
        self.is_listening = False

        # --- Initialize Direct Web Search ---
        self.web_search = DuckDuckGoSearchAPIWrapper(max_results=3)

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ==========================================
        # SIDEBAR
        # ==========================================
        self.sidebar = ctk.CTkFrame(self, width=240, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(4, weight=1) 

        self.logo = ctk.CTkLabel(self.sidebar, text="🧠 AI AYUSH", font=("Segoe UI", 20, "bold"), text_color="#3498db")
        self.logo.grid(row=0, column=0, padx=20, pady=(20, 5))

        self.status_label = ctk.CTkLabel(self.sidebar, text="🟡 Syncing Knowledge...", font=("Segoe UI", 11, "bold"), text_color="#f1c40f")
        self.status_label.grid(row=1, column=0, padx=20, pady=(0, 10))

        self.upload_btn = ctk.CTkButton(self.sidebar, text="📂 Upload File / Photo", font=("Segoe UI", 13, "bold"), command=self.trigger_upload)
        self.upload_btn.grid(row=2, column=0, padx=20, pady=(5, 15), sticky="ew")

        self.history_title = ctk.CTkLabel(self.sidebar, text="ACTIVE SOURCES", font=("Segoe UI", 11, "bold"), text_color="#7f8c8d")
        self.history_title.grid(row=3, column=0, padx=20, pady=(15, 5), sticky="w")

        self.sources_frame = ctk.CTkScrollableFrame(self.sidebar, fg_color="transparent", corner_radius=0)
        self.sources_frame.grid(row=4, column=0, padx=10, pady=5, sticky="nsew")
        self.sources_frame.grid_columnconfigure(0, weight=1)

        self.slider_label = ctk.CTkLabel(self.sidebar, text="Context Retrieval Depth", font=("Segoe UI", 11))
        self.slider_label.grid(row=5, column=0, padx=20, pady=(10, 0))
        
        self.context_slider = ctk.CTkSlider(self.sidebar, from_=1, to=10, number_of_steps=9)
        self.context_slider.grid(row=6, column=0, padx=20, pady=(5, 20))
        self.context_slider.set(5) 

        # ==========================================
        # MAIN FRAME
        # ==========================================
        self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_frame.grid(row=0, column=1, sticky="nsew")
        self.main_frame.grid_rowconfigure(0, weight=1)
        self.main_frame.grid_columnconfigure(0, weight=1)

        self.chat_display = ctk.CTkTextbox(self.main_frame, font=("Segoe UI", 14), wrap="word")
        self.chat_display.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="nsew")
        
        self.chat_display._textbox.tag_config("user_color", foreground="#00BFFF", justify="right", font=("Segoe UI", 14, "bold"))
        self.chat_display._textbox.tag_config("ai_color", foreground="#FFFFFF", justify="left")
        self.chat_display._textbox.tag_config("sys_color", foreground="#888888", justify="center", font=("Segoe UI", 11, "italic"))
        self.chat_display._textbox.tag_config("success_color", foreground="#2ecc71", justify="center", font=("Segoe UI", 11, "bold"))

        self.progress = ctk.CTkProgressBar(self.main_frame, height=4, progress_color="#3498db")
        self.progress.grid(row=1, column=0, padx=20, pady=5, sticky="ew")
        self.progress.set(0)

        self.input_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.input_frame.grid(row=2, column=0, padx=20, pady=(5, 20), sticky="ew")
        self.input_frame.grid_columnconfigure(0, weight=1) 
        self.input_frame.grid_columnconfigure(1, weight=0) 
        self.input_frame.grid_columnconfigure(2, weight=0) 

        self.entry = ctk.CTkEntry(self.input_frame, placeholder_text="Initializing Chroma DB...", height=40, font=("Segoe UI", 14), state="disabled")
        self.entry.grid(row=0, column=0, padx=(0, 5), sticky="ew")
        self.entry.bind("<Return>", lambda e: self.send_message())

        self.mic_btn = ctk.CTkButton(
            self.input_frame, 
            text="🎤", 
            width=40, 
            height=40, 
            font=("Segoe UI", 16),
            fg_color="#2c3e50", 
            hover_color="#34495e",
            command=self.toggle_voice_search, 
            state="disabled"
        )
        self.mic_btn.grid(row=0, column=1, padx=(0, 10))

        self.btn = ctk.CTkButton(self.input_frame, text="✨ Send", height=40, font=("Segoe UI", 14, "bold"), command=self.send_message, state="disabled")
        self.btn.grid(row=0, column=2)

        self.run_embedding_diagnostic()
        threading.Thread(target=self.initialize_knowledge_base, daemon=True).start()

    # ==========================================
    # VOICE TO TEXT LOGIC
    # ==========================================
    def toggle_voice_search(self):
        if not self.is_listening:
            self.is_listening = True
            self.mic_btn.configure(fg_color="#e74c3c", hover_color="#c0392b") 
            
            self.entry.configure(state="normal")
            self.entry.delete(0, "end")
            self.entry.insert(0, "🎙️ Listening... Speak now.")
            self.entry.configure(state="disabled")
            
            threading.Thread(target=self.voice_recognition_worker, daemon=True).start()
        else:
            self.is_listening = False
            self.reset_mic_ui(clear=True)

    def voice_recognition_worker(self):
        r = sr.Recognizer()
        with sr.Microphone() as source:
            try:
                r.adjust_for_ambient_noise(source, duration=0.5)
                audio = r.listen(source, timeout=5, phrase_time_limit=15)
            except sr.WaitTimeoutError:
                if self.is_listening:
                    self.append_chat("⚠️ Voice search timed out. No speech detected.", "sys_color")
                self.reset_mic_ui(clear=True)
                return
            except Exception as e:
                self.append_chat(f"❌ Microphone Error: {e}", "sys_color")
                self.reset_mic_ui(clear=True)
                return

        if not self.is_listening:
            return 

        try:
            self.entry.configure(state="normal")
            self.entry.delete(0, "end")
            self.entry.insert(0, "⏳ Converting to text...")
            self.entry.configure(state="disabled")
            
            text = r.recognize_google(audio)
            
            if self.is_listening:
                self.entry.configure(state="normal")
                self.entry.delete(0, "end")
                self.entry.insert(0, text)
                self.reset_mic_ui(clear=False)
                
        except sr.UnknownValueError:
            self.append_chat("⚠️ Could not understand the audio. Please speak clearly and try again.", "sys_color")
            self.reset_mic_ui(clear=True)
        except sr.RequestError as e:
            self.append_chat(f"❌ Speech recognition service error: {e}", "sys_color")
            self.reset_mic_ui(clear=True)

    def reset_mic_ui(self, clear=False):
        self.is_listening = False
        try:
            self.mic_btn.configure(fg_color="#2c3e50", hover_color="#34495e")
            self.entry.configure(state="normal")
            if clear:
                self.entry.delete(0, "end")
            
            current_text = self.entry.get()
            if not current_text or current_text in ["🎙️ Listening... Speak now.", "⏳ Converting to text..."]:
                self.entry.delete(0, "end")
                self.entry.configure(placeholder_text="Ask a question...")
        except Exception:
            pass 

    def run_embedding_diagnostic(self):
        try:
            if not is_internet_available():
                print("Warning: Currently offline. Cloud embeddings will fail until connection is restored.")
                return
            test_vector = self.embeddings.embed_query("This is a test.")
            print("--- Embedding Engine Online ---")
        except Exception as e:
            print(f"Warning: Preliminary embedding test failed: {e}")

    # ==========================================
    # FILE UPLOAD & INGESTION LOGIC
    # ==========================================
    def trigger_upload(self):
        file_paths = filedialog.askopenfilenames(
            title="Select Documents or Photos",
            filetypes=[
                ("All Supported", "*.pdf *.txt *.png *.jpg *.jpeg"),
                ("PDF Documents", "*.pdf"),
                ("Text Files", "*.txt"),
                ("Images", "*.png *.jpg *.jpeg")
            ]
        )
        if file_paths:
            threading.Thread(target=self.process_uploaded_files, args=(file_paths,), daemon=True).start()

    def process_uploaded_files(self, file_paths):
        self.progress.start()
        self.upload_btn.configure(state="disabled")
        self.btn.configure(state="disabled")
        self.mic_btn.configure(state="disabled")
        
        try:
            if not is_internet_available():
                self.append_chat("⚠️ Offline Mode: Cannot process new files to ChromaDB without internet access to Mistral Embeddings.", "sys_color")
                return

            all_raw_docs = []
            new_files_added = []

            for path in file_paths:
                ext = path.lower().split('.')[-1]
                file_name = Path(path).name
                self.append_chat(f"Reading '{file_name}'...", "sys_color")

                if ext == 'pdf':
                    docs = PyPDFLoader(path).load()
                    for d in docs: d.metadata["source"] = file_name 
                    all_raw_docs.extend(docs)
                    new_files_added.append(f"📄 {file_name}")
                elif ext == 'txt':
                    docs = TextLoader(path, encoding="utf-8").load()
                    for d in docs: d.metadata["source"] = file_name
                    all_raw_docs.extend(docs)
                    new_files_added.append(f"📝 {file_name}")
                elif ext in ['png', 'jpg', 'jpeg']:
                    img = Image.open(path)
                    extracted_text = pytesseract.image_to_string(img)
                    if not extracted_text.strip():
                        self.append_chat(f"⚠️ No readable text found in photo: {file_name}", "sys_color")
                        continue
                    
                    doc = Document(page_content=extracted_text, metadata={"source": file_name})
                    all_raw_docs.append(doc)
                    new_files_added.append(f"🖼️ {file_name}")

            if not all_raw_docs:
                self.append_chat("⚠️ No text could be parsed from the provided files.", "sys_color")
                return

            self.append_chat("Chunking and updating vector database...", "sys_color")
            text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
            doc_chunks = text_splitter.split_documents(all_raw_docs)

            if self.vector_store is None:
                self.vector_store = Chroma.from_documents(documents=doc_chunks, embedding=self.embeddings, persist_directory="./chroma_db")
            else:
                self.vector_store.add_documents(doc_chunks)

            self.loaded_files_status.extend(new_files_added)
            self.refresh_sidebar_sources()
            
            self.append_chat(f"\n✅ Successfully appended {len(doc_chunks)} chunks to Knowledge Base.", "success_color")
            self.status_label.configure(text="🟢 Engine Ready", text_color="#2ecc71")
            
            self.entry.configure(state="normal", placeholder_text="Ask a question...")
            
        except Exception as e:
            self.append_chat(f"\n❌ Upload Processing Error: {e}", "sys_color")
            
        finally:
            self.progress.stop()
            self.progress.set(0)
            self.upload_btn.configure(state="normal")
            self.btn.configure(state="normal")
            self.mic_btn.configure(state="normal")

    # ==========================================
    # DELETION LOGIC
    # ==========================================
    def refresh_sidebar_sources(self):
        for widget in self.sources_frame.winfo_children():
            widget.destroy()
        
        for idx, file_label in enumerate(self.loaded_files_status):
            btn = ctk.CTkButton(
                self.sources_frame, 
                text=file_label, 
                font=("Segoe UI", 12), 
                anchor="w",
                fg_color="transparent",
                hover_color="#c0392b", 
                text_color="#ecf0f1",
                command=lambda f=file_label: self.confirm_delete(f)
            )
            btn.grid(row=idx, column=0, padx=5, pady=2, sticky="ew")

    def confirm_delete(self, file_label):
        filename = file_label.split(" ", 1)[-1] 
        confirm = messagebox.askyesno("Delete Source", f"Are you sure you want to remove '{filename}' from the active knowledge base?")
        if confirm:
            threading.Thread(target=self.delete_source, args=(file_label, filename), daemon=True).start()

    def delete_source(self, file_label, filename):
        self.progress.start()
        try:
            if self.vector_store:
                db_data = self.vector_store.get(where={"source": filename})
                ids_to_delete = db_data.get("ids", [])
                
                if ids_to_delete:
                    self.vector_store.delete(ids=ids_to_delete)
                    self.append_chat(f"\n🗑️ Removed '{filename}' (Deleted {len(ids_to_delete)} chunks).", "sys_color")
                else:
                    self.append_chat(f"\n⚠️ Database mismatch: Could not find chunks for '{filename}'.", "sys_color")

            if file_label in self.loaded_files_status:
                self.loaded_files_status.remove(file_label)
            
            self.refresh_sidebar_sources()
            
            if not self.loaded_files_status:
                self.status_label.configure(text="🟡 Web Search Only", text_color="#f1c40f")
                
        except Exception as e:
            self.append_chat(f"\n❌ Error deleting source: {e}", "sys_color")
        finally:
            self.progress.stop()
            self.progress.set(0)

    def initialize_knowledge_base(self):
        self.progress.start()
        
        try:
            all_raw_docs = []
            
            if pdf_path.exists():
                docs = PyPDFLoader(str(pdf_path)).load()
                for d in docs: d.metadata["source"] = pdf_path.name
                all_raw_docs.extend(docs)
                self.loaded_files_status.append(f"📄 {pdf_path.name}")
                
            if notes_path.exists():
                docs = TextLoader(str(notes_path), encoding="utf-8").load()
                for d in docs: d.metadata["source"] = notes_path.name
                all_raw_docs.extend(docs)
                self.loaded_files_status.append(f"📝 {notes_path.name}")

            if not all_raw_docs:
                self.append_chat("No default documents found. Web Search is active. Upload files for local context.", "sys_color")
                self.status_label.configure(text="🟡 Web Search Only", text_color="#f1c40f")
                self.entry.configure(state="normal", placeholder_text="Ask a question...")
                self.btn.configure(state="normal")
                self.mic_btn.configure(state="normal")
                return

            if not is_internet_available():
                self.append_chat("⚠️ Offline Mode: Cannot generate fresh ChromaDB chunks without internet.", "sys_color")
                self.entry.configure(state="normal", placeholder_text="Ask a question...")
                self.btn.configure(state="normal")
                self.mic_btn.configure(state="normal")
                return

            self.refresh_sidebar_sources()
            self.append_chat("Generating vector structural matrix points in './chroma_db'...", "sys_color")
            
            text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
            doc_chunks = text_splitter.split_documents(all_raw_docs)
            
            self.vector_store = Chroma.from_documents(
                documents=doc_chunks,
                embedding=self.embeddings,
                persist_directory="./chroma_db"
            )
            
            self.append_chat(f"\n✅ Initial Database Loaded! Indexed {len(doc_chunks)} chunks.", "success_color")
            self.status_label.configure(text="🟢 Engine Ready", text_color="#2ecc71")
            
            self.entry.configure(state="normal", placeholder_text="Ask a question...")
            self.btn.configure(state="normal")
            self.mic_btn.configure(state="normal")
            
        except Exception as e:
            self.append_chat(f"\n❌ Initialization Error: {e}", "sys_color")
            self.status_label.configure(text="🔴 Loading Failed", text_color="#e74c3c")
            
        finally:
            self.progress.stop()
            self.progress.set(0)

    # ==========================================
    # CHAT INTERACTIONS
    # ==========================================
    def append_chat(self, text, role):
        self.chat_display.configure(state="normal")
        self.chat_display.insert("end", text + "\n", role)
        self.chat_display.see("end")
        self.chat_display.configure(state="disabled")

    def animate_typing(self, text):
        self.chat_display.configure(state="normal")
        self.chat_display.insert("end", "\n🤖 Assistant:\n", "ai_color")
        self.chat_display.see("end")
        
        for char in text:
            self.chat_display.insert("end", char, "ai_color")
            self.chat_display.see("end")
            time.sleep(0.008)
            
        self.chat_display.insert("end", "\n\n", "ai_color")
        self.chat_display.configure(state="disabled")

    def send_message(self):
        question = self.entry.get().strip()
        if not question or self.btn.cget("state") == "disabled": 
            return
            
        # ==========================================
        # DIRECT YOUTUBE PLAYBACK LOGIC (ROBUST WAY)
        # ==========================================
        lower_q = question.lower()
        trigger_words = ["play ", "watch ", "listen to "]
        
        if any(lower_q.startswith(keyword) for keyword in trigger_words):
            self.append_chat(f"\n🧑 You:\n{question}\n", "user_color")
            self.entry.delete(0, "end")
            
            # Extract the actual media search term
            search_term = question
            for keyword in trigger_words:
                if lower_q.startswith(keyword):
                    search_term = question[len(keyword):].strip()
                    break
                    
            self.append_chat(f"🎶 Opening YouTube for: '{search_term}'...", "success_color")
            
            # Formulate clean URL encoding for the search term
            encoded_search = urllib.parse.quote(search_term)
            youtube_url = f"https://www.youtube.com/results?search_query={encoded_search}"
            
            # Fire safely in a background thread
            threading.Thread(target=lambda: webbrowser.open(youtube_url), daemon=True).start()
            return 
        # ==========================================

        self.append_chat(f"\n🧑 You:\n{question}\n", "user_color")
        self.entry.delete(0, "end")
        
        self.btn.configure(state="disabled")
        self.mic_btn.configure(state="disabled")
        self.entry.configure(state="disabled")
        threading.Thread(target=self.fetch_ai_response, args=(question,), daemon=True).start()

    def fetch_ai_response(self, question):
        self.progress.start()
        try:
            # Check connection state for dynamic fallback rules
            online = is_internet_available()

            # 1. Fetch Local DB Context
            local_context = ""
            if self.vector_store:
                depth = int(self.context_slider.get())
                try:
                    relevant_docs = self.vector_store.similarity_search(question, k=depth)
                    if relevant_docs:
                        local_context = "\n\n".join([f"--- Source ({doc.metadata.get('source','')}): ---\n{doc.page_content}" for doc in relevant_docs])
                except Exception as e:
                    self.append_chat(f"⚠️ Local DB read error: {e}", "sys_color")
            
            if not local_context:
                local_context = "No local documents uploaded or relevant."

            # 2. Phase 1 Prompt: Force AI to look ONLY at local data
            prompt_local = f"""
            You are a strict helpful assistant. You must answer the user's question using ONLY the 'LOCAL DOCUMENTS CONTEXT' below.
            
            RULES:
            1. If the exact answer or necessary context is present in the LOCAL DOCUMENTS CONTEXT, answer the question comprehensively.
            2. If the answer is NOT in the context, you must reply with the exact phrase: "WEB_SEARCH_REQUIRED". Do not include any other text.
            
            --- LOCAL DOCUMENTS CONTEXT ---
            {local_context}

            User's Question: {question}
            """
            
            try:
                # Ask Mistral to evaluate local documents
                message = HumanMessage(content=prompt_local)
                response = self.model.invoke([message])
                ai_answer = response.content.strip()
            except Exception as e:
                # Catch Mistral connection crash if fully offline
                if not online:
                    self.append_chat("\n⚠️ System is fully offline and cannot reach the Mistral Cloud API. Please reconnect or use a local LLM model like Ollama.", "sys_color")
                    return
                else:
                    raise e
            
            # 3. Phase 2: Web Search Fallback Trigger
            if "WEB_SEARCH_REQUIRED" in ai_answer:
                if not online:
                    self.append_chat("⚠️ Information not found in active sources.", "sys_color")
                    self.animate_typing("I don't have the answer in your uploaded documents, and because we are offline, I cannot search the web right now.")
                    return
                
                self.append_chat("🌍 Information not found locally. Searching the web directly...", "sys_color")
                try:
                    web_results = self.web_search.run(question)
                except Exception as e:
                    web_results = f"Web Search failed or timed out: {e}"

                prompt_web = f"""
                You are a helpful assistant. The user asked a question that was not found in their local documents.
                Answer the user's question clearly using the live web search results provided below.
                
                --- LIVE WEB SEARCH RESULTS ---
                {web_results}

                User's Question: {question}
                """
                
                web_message = HumanMessage(content=prompt_web)
                final_response = self.model.invoke([web_message])
                self.animate_typing(final_response.content)
            
            else:
                self.append_chat("📄 Answer generated from Local Documents.", "sys_color")
                self.animate_typing(ai_answer)
                
        except Exception as e:
            self.append_chat(f"\n❌ AI Generation Layer Fault: {e}", "sys_color")
            
        finally:
            self.progress.stop()
            self.progress.set(0)
            self.btn.configure(state="normal")
            self.mic_btn.configure(state="normal")
            self.entry.configure(state="normal")

if __name__ == "__main__":
    app = ImmersiveQAApp()
    app.mainloop()