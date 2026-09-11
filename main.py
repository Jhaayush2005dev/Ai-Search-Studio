import os
import sys
import threading
import urllib.parse
import webbrowser
from pathlib import Path
from typing import Optional, List
from PIL import Image

import customtkinter as ctk
from tkinter import filedialog, messagebox

# Core Engine & Service Imports
from core.config import (
    DOCS_DIR, MISTRAL_API_KEY, get_theme_colors,
    is_internet_available, THEMES, SUPPORTED_EXTENSIONS
)
from core.doc_loader import UniversalDocumentLoader
from core.rag_engine import RAGEngine
from core.voice_service import VoiceService
from core.web_service import WebService

# UI Components & Modals
from ui.sidebar import Sidebar
from ui.chat_view import ChatView
from ui.components import StatusPill, PromptChip, ChatMessageCard, ModeActivationHUD, SearchInputBox
from ui.modals import ImageViewerModal, KnowledgeStatsModal, ExportChatModal

# Set appearance default
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class AISearchStudioApp(ctk.CTk):
    """Main Application Window for AI Search Studio."""

    def __init__(self):
        super().__init__()
        self.colors = get_theme_colors()

        # Responsive Startup Dimensions
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        is_small_device = screen_w < 768 or screen_h > screen_w

        if is_small_device:
            init_w = min(screen_w, 420)
            init_h = min(screen_h, 840)
            self.geometry(f"{init_w}x{init_h}+0+0")
        else:
            init_w = min(1150, screen_w - 60)
            init_h = min(820, screen_h - 60)
            self.geometry(f"{init_w}x{init_h}")

        self.minsize(320, 450)
        self.title("🧠 AI Search Studio - Universal Document & Web Intelligence Studio")
        self.configure(fg_color=self.colors["bg_base"])

        # Responsive State
        self.is_mobile = False
        self.drawer_open = False
        self._resize_debounce_job = None

        # Validate API Key Notice (Non-blocking)
        if not MISTRAL_API_KEY:
            self.after(200, lambda: self.chat_view.add_system_notice("⚠️ **MISTRAL_API_KEY** not found in `.env`. Please add your key to enable AI completions."))

        # Services & State
        self.doc_loader = UniversalDocumentLoader()
        self.rag_engine = RAGEngine(api_key=MISTRAL_API_KEY)
        self.voice_service = VoiceService()
        self.web_service = WebService()
        self.auto_speak_enabled = False
        self.is_processing = False

        # Build Main UI Layout
        self._setup_layout()
        self._build_header()
        self._build_chat_area()
        self._build_input_area()

        # Bind responsive layout resize
        self.bind("<Configure>", self._on_window_configure)

        # Apply initial responsive pass
        self.after(50, self._apply_responsive_layout)

        # Kick off startup background initialization
        threading.Thread(target=self._startup_init_worker, daemon=True).start()

    # ==========================================
    # LAYOUT & UI CONSTRUCTION
    # ==========================================
    def _setup_layout(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Dim Backdrop Frame for Mobile Drawer Overlay
        self.backdrop_frame = ctk.CTkFrame(self, fg_color="#000000", corner_radius=0)
        self.backdrop_frame.bind("<Button-1>", lambda e: self.close_sidebar_drawer())

        # Sidebar
        self.sidebar = Sidebar(
            self,
            on_upload_click=self._on_sidebar_upload,
            on_delete_source=self.trigger_delete_source,
            on_mode_change=self._on_sidebar_mode_change,
            on_model_change=self.on_model_selected,
            on_temp_change=self.on_temp_changed,
            on_depth_change=self.on_depth_changed,
            on_theme_change=self._on_sidebar_theme_change,
            on_tts_toggle=self.on_tts_toggled,
            on_stats_click=self._on_sidebar_stats_click,
            on_close=self.close_sidebar_drawer
        )
        self.sidebar.grid(row=0, column=0, sticky="nsew")

        # Main Content Container
        self.main_container = ctk.CTkFrame(self, fg_color="transparent")
        self.main_container.grid(row=0, column=1, sticky="nsew")
        self.main_container.grid_rowconfigure(1, weight=1) # Chat feed expands
        self.main_container.grid_columnconfigure(0, weight=1)

        # Mode Activation HUD Overlay
        self.mode_hud = ModeActivationHUD(self.main_container)

    def _build_header(self):
        """Top action bar with live status badge, mobile hamburger, and quick tools."""
        self.header_bar = ctk.CTkFrame(
            self.main_container,
            height=50,
            fg_color=self.colors["bg_sidebar"],
            corner_radius=0,
            border_width=1,
            border_color=self.colors["border_color"]
        )
        self.header_bar.grid(row=0, column=0, sticky="ew")

        # Hamburger Menu Button (Mobile Only)
        self.menu_btn = ctk.CTkButton(
            self.header_bar,
            text="☰",
            font=("Segoe UI", 16, "bold"),
            width=36,
            height=32,
            corner_radius=6,
            fg_color=self.colors["chip_bg"],
            hover_color=self.colors["chip_hover"],
            text_color=self.colors["text_primary"],
            command=self.toggle_sidebar_drawer
        )

        # Left Status Pill
        self.status_pill = StatusPill(self.header_bar, text="Syncing Knowledge Base...", status_type="warning")
        self.status_pill.pack(side="left", padx=15, pady=10)

        # Right Action Buttons
        self.export_btn = ctk.CTkButton(
            self.header_bar,
            text="💾 Export Chat",
            font=("Segoe UI", 11, "bold"),
            height=30,
            width=100,
            fg_color=self.colors["chip_bg"],
            hover_color=self.colors["chip_hover"],
            text_color=self.colors["text_primary"],
            command=self.trigger_export_chat
        )
        self.export_btn.pack(side="right", padx=(0, 15), pady=10)

        self.clear_btn = ctk.CTkButton(
            self.header_bar,
            text="🧹 Clear Chat",
            font=("Segoe UI", 11),
            height=30,
            width=90,
            fg_color="transparent",
            hover_color=self.colors["chip_hover"],
            text_color=self.colors["text_muted"],
            command=self.trigger_clear_chat
        )
        self.clear_btn.pack(side="right", padx=(0, 8), pady=10)

    def _build_chat_area(self):
        """Scrollable message cards container."""
        self.chat_view = ChatView(
            self.main_container,
            on_tts_click=self.speak_text,
            on_view_image=self.open_image_viewer
        )
        self.chat_view.grid(row=1, column=0, sticky="nsew")

    def _build_input_area(self):
        """Bottom interactive panel with quick chips, voice recording, and input entry."""
        self.bottom_panel = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.bottom_panel.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 15))
        self.bottom_panel.grid_columnconfigure(0, weight=1)

        # 1. Horizontally Scrollable Action Chips (Swipable on mobile)
        self.chips_scroll = ctk.CTkScrollableFrame(
            self.bottom_panel,
            orientation="horizontal",
            height=34,
            fg_color="transparent"
        )
        self.chips_scroll.pack(fill="x", pady=(0, 6))

        chips = [
            ("📝 Summarize Docs", lambda: self.run_quick_ai_tool("summary")),
            ("🎯 Practice Quiz", lambda: self.run_quick_ai_tool("quiz")),
            ("💡 Key Insights", lambda: self.run_quick_ai_tool("insights")),
            ("🌐 Web Mode", lambda: self.on_mode_selected("Web Only")),
            ("📄 Docs Mode", lambda: self.on_mode_selected("Docs Only")),
            ("🔄 Auto Mode", lambda: self.on_mode_selected("Auto (Hybrid)")),
        ]

        for text, cmd in chips:
            chip = PromptChip(self.chips_scroll, text=text, command=cmd)
            chip.pack(side="left", padx=(0, 6))

        # 2. Progress Bar
        self.progress_bar = ctk.CTkProgressBar(self.bottom_panel, height=3, progress_color=self.colors["accent_primary"])
        self.progress_bar.pack(fill="x", pady=(0, 6))
        self.progress_bar.set(0)

        # 3. Input Controls Bar
        self.input_card = ctk.CTkFrame(
            self.bottom_panel,
            fg_color=self.colors["bg_input"],
            corner_radius=12,
            border_width=1,
            border_color=self.colors["border_color"]
        )
        self.input_card.pack(fill="x")
        self.input_card.grid_columnconfigure(1, weight=1)

        # Attach File Button (+)
        self.attach_btn = ctk.CTkButton(
            self.input_card,
            text="+",
            font=("Segoe UI", 18, "bold"),
            width=40,
            height=40,
            corner_radius=8,
            fg_color="transparent",
            hover_color=self.colors["chip_hover"],
            text_color=self.colors["text_secondary"],
            command=self.trigger_file_upload
        )
        self.attach_btn.grid(row=0, column=0, padx=(6, 2), pady=6)

        # Text Entry (Supports Shift+Enter for multiline, Enter for search)
        self.query_entry = SearchInputBox(
            self.input_card,
            placeholder_text="Ask any question about your documents, code, or search the web...",
            on_submit=self.send_user_query
        )
        self.query_entry.grid(row=0, column=1, padx=6, pady=6, sticky="ew")

        # Microphone STT Button
        self.mic_btn = ctk.CTkButton(
            self.input_card,
            text="🎤",
            font=("Segoe UI", 15),
            width=40,
            height=40,
            corner_radius=8,
            fg_color="transparent",
            hover_color=self.colors["chip_hover"],
            text_color=self.colors["text_secondary"],
            command=self.toggle_voice_stt
        )
        self.mic_btn.grid(row=0, column=2, padx=2, pady=6)

        # Dynamic Search / Stop Button
        self.send_btn = ctk.CTkButton(
            self.input_card,
            text="🔍 Search",
            font=("Segoe UI", 12, "bold"),
            width=88,
            height=38,
            corner_radius=8,
            fg_color=self.colors["accent_primary"],
            hover_color=self.colors["accent_hover"],
            command=self.send_user_query
        )
        self.send_btn.grid(row=0, column=3, padx=(4, 6), pady=6)

    # ==========================================
    # RESPONSIVE ADAPTIVE LAYOUT & DRAWER
    # ==========================================
    def _on_window_configure(self, event):
        if event.widget == self:
            curr_w = event.width
            curr_h = event.height
            if getattr(self, "_last_win_w", None) == curr_w and getattr(self, "_last_win_h", None) == curr_h:
                return
            self._last_win_w = curr_w
            self._last_win_h = curr_h
            if self._resize_debounce_job:
                try:
                    self.after_cancel(self._resize_debounce_job)
                except Exception:
                    pass
            self._resize_debounce_job = self.after(80, self._apply_responsive_layout)

    def _apply_responsive_layout(self):
        try:
            win_w = self.winfo_width()
            if win_w < 50:
                return

            is_mobile = (win_w < 768)

            if is_mobile != self.is_mobile:
                self.is_mobile = is_mobile
                if is_mobile:
                    # Switch to Mobile View
                    self.grid_columnconfigure(0, weight=0)
                    self.grid_columnconfigure(1, weight=1)
                    self.sidebar.grid_forget()
                    self.main_container.grid(row=0, column=0, columnspan=2, sticky="nsew")

                    # Header Mobile Layout
                    self.status_pill.pack_forget()
                    self.menu_btn.pack(side="left", padx=(10, 6), pady=8)
                    self.status_pill.pack(side="left", padx=(0, 6), pady=8)
                    self.status_pill.set_compact(True)

                    self.export_btn.configure(text="💾", width=34)
                    self.clear_btn.configure(text="🧹", width=34)

                    # Input Mobile Layout
                    self.bottom_panel.grid_configure(padx=10, pady=(0, 10))
                    self.query_entry.configure(placeholder_text="Ask question or search web...")

                    # Subcomponents Mobile Mode
                    self.sidebar.set_mobile_mode(True)
                    self.chat_view.set_mobile_mode(True)
                else:
                    # Switch to Desktop View
                    self.close_sidebar_drawer()
                    self.sidebar.set_mobile_mode(False)
                    self.chat_view.set_mobile_mode(False)

                    self.grid_columnconfigure(0, weight=0)
                    self.grid_columnconfigure(1, weight=1)
                    self.sidebar.grid(row=0, column=0, sticky="nsew")
                    self.main_container.grid(row=0, column=1, columnspan=1, sticky="nsew")

                    # Header Desktop Layout
                    self.menu_btn.pack_forget()
                    self.status_pill.pack_forget()
                    self.status_pill.pack(side="left", padx=15, pady=10)
                    self.status_pill.set_compact(False)

                    self.export_btn.configure(text="💾 Export Chat", width=100)
                    self.clear_btn.configure(text="🧹 Clear Chat", width=90)

                    # Input Desktop Layout
                    self.bottom_panel.grid_configure(padx=20, pady=(0, 15))
                    self.query_entry.configure(placeholder_text="Ask any question about your documents, code, or search the web...")

            if self.is_mobile and self.drawer_open:
                drawer_w = min(320, int(win_w * 0.88))
                self.sidebar.configure(width=drawer_w)
                self.sidebar.place(x=0, y=0, relheight=1.0)
        except Exception:
            pass

    def toggle_sidebar_drawer(self):
        if self.drawer_open:
            self.close_sidebar_drawer()
        else:
            self.open_sidebar_drawer()

    def open_sidebar_drawer(self):
        if not self.is_mobile:
            return
        self.drawer_open = True
        win_w = max(self.winfo_width(), 320)
        drawer_w = min(320, int(win_w * 0.88))

        self.backdrop_frame.place(x=0, y=0, relwidth=1.0, relheight=1.0)
        self.backdrop_frame.lift()
        self.sidebar.set_mobile_mode(True)
        self.sidebar.configure(width=drawer_w)
        self.sidebar.place(x=0, y=0, relheight=1.0)
        self.sidebar.lift()

    def close_sidebar_drawer(self):
        self.drawer_open = False
        try:
            self.backdrop_frame.place_forget()
            self.sidebar.place_forget()
        except Exception:
            pass

    def _on_sidebar_upload(self):
        if self.is_mobile:
            self.close_sidebar_drawer()
        self.trigger_file_upload()

    def _on_sidebar_mode_change(self, mode: str):
        if self.is_mobile:
            self.close_sidebar_drawer()
        self.on_mode_selected(mode)

    def _on_sidebar_theme_change(self, theme: str):
        if self.is_mobile:
            self.close_sidebar_drawer()
        self.on_theme_selected(theme)

    def _on_sidebar_stats_click(self):
        if self.is_mobile:
            self.close_sidebar_drawer()
        self.show_knowledge_stats()

    # ==========================================
    # BACKGROUND STARTUP INGESTION
    # ==========================================
    def _startup_init_worker(self):
        """Loads all existing documents in documents loaders/ folder."""
        self._set_progress(start=True)
        try:
            if not is_internet_available():
                self._safe_ui(lambda: self.status_pill.set_status("Offline Mode (No Internet)", "danger"))
                self._safe_ui(lambda: self.chat_view.add_system_notice("⚠️ System is running offline. Online AI embeddings are unavailable."))
                return

            # Check files in documents folder
            doc_files = [str(f) for f in DOCS_DIR.iterdir() if f.is_file()]
            if doc_files:
                chunks, meta, errors = self.doc_loader.process_and_chunk(doc_files)
                if chunks:
                    self.rag_engine.add_documents(chunks, meta)
                    self._safe_ui(lambda: self.sidebar.update_sources_list(self.rag_engine.active_sources_meta))
                    self._safe_ui(lambda: self.status_pill.set_status(f"🟢 Ready ({len(chunks)} Chunks)", "success"))
                    self._safe_ui(lambda: self.chat_view.add_system_notice(f"✅ Loaded {len(meta)} local files ({len(chunks)} total vector chunks ready)."))
                else:
                    self._safe_ui(lambda: self.status_pill.set_status("🟡 Web Search Ready", "warning"))
            else:
                self.rag_engine.init_vector_store()
                self._safe_ui(lambda: self.status_pill.set_status("🟡 Web Search Ready", "warning"))

        except Exception as e:
            self._safe_ui(lambda err=e: self.status_pill.set_status(f"🔴 DB Init: {str(err)[:20]}", "danger"))
        finally:
            self._set_progress(stop=True)

    # ==========================================
    # QUERY EXECUTION & STREAMING
    # ==========================================
    def send_user_query(self):
        """Processes user input from entry or triggers stop if already generating."""
        if self.is_processing:
            # User clicked button while generating -> Stop generation
            self.rag_engine.stop_generation()
            self.voice_service.stop_speaking()
            self._set_generating_state(False)
            return

        query = self.query_entry.get().strip()
        if not query:
            return

        self.query_entry.delete(0, "end")
        self.chat_view.add_user_message(query)
        self.voice_service.stop_speaking()

        # Handle Browsing & URL Navigation Intent (e.g. "open youtube", "youtube.com", "open github for langchain", "google quantum computing")
        nav_target = self.web_service.resolve_browsing_intent(query)
        if nav_target:
            target_url, display_title = nav_target
            self.chat_view.add_system_notice(f"🌐 Opening {display_title} in your browser...\n🔗 {target_url}")
            if self.auto_speak_enabled:
                self.voice_service.speak(f"Opening {display_title} in your browser.")
            threading.Thread(
                target=lambda: webbrowser.open(target_url),
                daemon=True
            ).start()
            return

        # Handle Image Search Intent
        lower_q = query.lower()
        img_triggers = ["picture of", "photo of", "image of", "show me", "diagram of", "draw ", "generate image"]
        if any(t in lower_q for t in img_triggers):
            threading.Thread(target=self._image_query_worker, args=(query,), daemon=True).start()
            return

        # Standard RAG & Knowledge Query with Live Streaming
        threading.Thread(target=self._stream_query_worker, args=(query,), daemon=True).start()

    def _stream_query_worker(self, query: str):
        self._set_generating_state(True)
        self._set_progress(start=True)

        # Create new AI chat message card in main thread
        card_event = threading.Event()
        ai_card_container = []
        def create_card():
            try:
                card = self.chat_view.add_ai_message("")
                ai_card_container.append(card)
            finally:
                card_event.set()
        self.after(0, create_card)

        # Cleanly wait without CPU spin-loop
        card_event.wait(timeout=5.0)
        if not ai_card_container:
            self._set_progress(stop=True)
            self._set_generating_state(False)
            return
        ai_card = ai_card_container[0]

        citations_received = []

        def on_token(token: str):
            self._safe_ui(lambda: ai_card.append_token(token))
            self._safe_ui(self.chat_view.scroll_to_bottom)

        def on_source(sources: List[str]):
            citations_received.extend(sources)

        def on_status(status_msg: str):
            self._safe_ui(lambda: self.status_pill.set_status(status_msg, "warning"))

        try:
            final_response = self.rag_engine.stream_query(
                query=query,
                token_callback=on_token,
                source_callback=on_source,
                status_callback=on_status
            )

            # Finalize formatting and citations
            self._safe_ui(lambda: self.chat_view.finalize_last_ai_message(final_response, citations_received))
            self._safe_ui(lambda: self.status_pill.set_status("🟢 Ready", "success"))

            # Auto TTS if enabled
            if self.auto_speak_enabled and final_response:
                self.voice_service.speak(final_response)

        except Exception as e:
            self._safe_ui(lambda err=e: self.chat_view.add_system_notice(f"❌ Error during response: {err}"))
        finally:
            self._set_progress(stop=True)
            self._set_generating_state(False)

    def _image_query_worker(self, query: str):
        self._set_generating_state(True)
        self._set_progress(start=True)
        self._safe_ui(lambda: self.status_pill.set_status("🎨 Searching Web Image...", "warning"))

        try:
            img, url, err = self.web_service.fetch_web_image(query)
            if img:
                def render_img():
                    card = self.chat_view.add_ai_message(f"Here is the image found for '{query}':")
                    card.attach_image(img, query)
                    card.set_citations([url] if url else ["Web Search"])
                self._safe_ui(render_img)
                self._safe_ui(lambda: self.status_pill.set_status("🟢 Ready", "success"))
            else:
                self._safe_ui(lambda: self.chat_view.add_system_notice(f"⚠️ {err or 'Could not fetch image.'}"))
                self._safe_ui(lambda: self.status_pill.set_status("🟢 Ready", "success"))
        except Exception as e:
            self._safe_ui(lambda err=e: self.chat_view.add_system_notice(f"❌ Image fetch error: {err}"))
        finally:
            self._set_progress(stop=True)
            self._set_generating_state(False)

    # ==========================================
    # QUICK AI TOOLS (Summary, Quiz, Insights)
    # ==========================================
    def run_quick_ai_tool(self, tool_type: str):
        if self.is_processing:
            return

        if not self.rag_engine.active_sources_meta:
            messagebox.showinfo("No Documents", "Please upload files (PDF, Word, TXT, etc.) to use this AI tool.")
            return

        if tool_type == "summary":
            query = "Generate a comprehensive executive summary of all uploaded documents."
        elif tool_type == "quiz":
            query = "Generate an interactive 5-question practice quiz with an Answer Key and Explanations based on the loaded documents."
        else: # insights
            query = "Extract key takeaways, insights, definitions, and action points from the documents."

        self.query_entry.delete(0, "end")
        self.query_entry.insert(0, query)
        self.send_user_query()

    # ==========================================
    # FILE UPLOADS & INDEXING
    # ==========================================
    def trigger_file_upload(self):
        file_paths = filedialog.askopenfilenames(
            title="Select Documents, Code, Data, or Images",
            filetypes=[
                ("All Supported Files", "*.pdf *.docx *.csv *.xlsx *.txt *.md *.py *.js *.json *.png *.jpg *.jpeg"),
                ("PDF Documents", "*.pdf"),
                ("Word Documents", "*.docx"),
                ("Spreadsheets & CSV", "*.csv *.xlsx *.xls"),
                ("Text & Markdown", "*.txt *.md"),
                ("Code Files", "*.py *.js *.ts *.html *.css *.json *.java *.cpp *.sql"),
                ("Images (OCR)", "*.png *.jpg *.jpeg")
            ]
        )
        if file_paths:
            threading.Thread(target=self._process_uploaded_files, args=(file_paths,), daemon=True).start()

    def _process_uploaded_files(self, file_paths):
        self._set_progress(start=True)
        self._safe_ui(lambda: self.status_pill.set_status("📥 Uploading & Indexing Files...", "warning"))

        try:
            chunks, meta, errors = self.doc_loader.process_and_chunk(file_paths)

            if errors:
                for err in errors:
                    self._safe_ui(lambda e=err: self.chat_view.add_system_notice(f"⚠️ {e}"))

            if chunks:
                self.rag_engine.add_documents(chunks, meta)
                self._safe_ui(lambda: self.sidebar.update_sources_list(self.rag_engine.active_sources_meta))
                self._safe_ui(lambda: self.status_pill.set_status(f"🟢 Ready ({sum(m['chunks'] for m in self.rag_engine.active_sources_meta)} Chunks)", "success"))
                self._safe_ui(lambda: self.chat_view.add_system_notice(f"✅ Successfully uploaded & indexed {len(meta)} files ({len(chunks)} new chunks in knowledge base)."))
            else:
                self._safe_ui(lambda: self.status_pill.set_status("🟢 Ready", "success"))

        except Exception as e:
            self._safe_ui(lambda err=e: self.chat_view.add_system_notice(f"❌ File upload & indexing failed: {err}"))
            self._safe_ui(lambda: self.status_pill.set_status("🔴 Upload Error", "danger"))
        finally:
            self._set_progress(stop=True)

    def trigger_delete_source(self, filename: str):
        threading.Thread(target=self._delete_source_worker, args=(filename,), daemon=True).start()

    def _delete_source_worker(self, filename: str):
        self._set_progress(start=True)
        try:
            success = self.rag_engine.delete_source(filename)
            if success:
                self._safe_ui(lambda: self.sidebar.update_sources_list(self.rag_engine.active_sources_meta))
                self._safe_ui(lambda: self.chat_view.add_system_notice(f"🗑️ Removed source '{filename}' and deleted its vectors."))
                total_chunks = sum(m['chunks'] for m in self.rag_engine.active_sources_meta)
                status_text = f"🟢 Ready ({total_chunks} Chunks)" if total_chunks else "🟡 Web Search Ready"
                self._safe_ui(lambda: self.status_pill.set_status(status_text, "success" if total_chunks else "warning"))
        except Exception as e:
            self._safe_ui(lambda err=e: self.chat_view.add_system_notice(f"❌ Delete source error: {err}"))
        finally:
            self._set_progress(stop=True)

    # ==========================================
    # TWO-WAY VOICE (STT & TTS)
    # ==========================================
    def toggle_voice_stt(self):
        if not self.voice_service.is_listening:
            self.mic_btn.configure(text="🔴", fg_color=self.colors["accent_danger"])
            self.query_entry.configure(placeholder_text="🎙️ Listening... Speak your question clearly.")

            def on_status(msg):
                self._safe_ui(lambda: self.status_pill.set_status(msg, "warning"))

            def on_result(text):
                self._safe_ui(lambda: self._apply_stt_result(text))

            def on_error(err):
                self._safe_ui(lambda: self.chat_view.add_system_notice(f"⚠️ {err}"))
                self._safe_ui(self._reset_mic_ui)

            self.voice_service.start_listening(on_status, on_result, on_error)
        else:
            self.voice_service.stop_listening()
            self._reset_mic_ui()

    def _apply_stt_result(self, text: str):
        self.query_entry.delete(0, "end")
        self.query_entry.insert(0, text)
        self._reset_mic_ui()
        # Automatically trigger search
        self.send_user_query()

    def _reset_mic_ui(self):
        self.mic_btn.configure(text="🎤", fg_color="transparent")
        placeholder = "Ask question or search web..." if self.is_mobile else "Ask any question about your documents, code, or search the web..."
        self.query_entry.configure(placeholder_text=placeholder)
        self.status_pill.set_status("🟢 Ready", "success")

    def speak_text(self, text: str):
        """Triggers audio playback of message."""
        if self.voice_service.is_speaking:
            self.voice_service.stop_speaking()
            self.status_pill.set_status("🟢 Ready", "success")
        else:
            self.status_pill.set_status("🔊 Speaking...", "success")
            self.voice_service.speak(text, callback_done=lambda: self._safe_ui(lambda: self.status_pill.set_status("🟢 Ready", "success")))

    # ==========================================
    # CONTROLS & SETTINGS CALLBACKS
    # ==========================================
    def on_mode_selected(self, mode: str):
        self.rag_engine.set_search_mode(mode)
        try:
            self.sidebar.mode_menu.set(mode)
        except Exception:
            pass

        # Trigger center HUD animation & neural female voice announcement
        try:
            self.mode_hud.trigger(mode, voice_callback=lambda _: self.voice_service.speak_mode(mode))
        except Exception as e:
            print(f"HUD Trigger Notice: {e}")

        self.chat_view.add_system_notice(f"🔄 Search engine mode switched to: **{mode}**")

    def on_model_selected(self, model: str):
        self.rag_engine.set_model(model)
        self.chat_view.add_system_notice(f"⚡ AI model switched to: **{model}**")

    def on_temp_changed(self, temp: float):
        self.rag_engine.set_temperature(temp)

    def on_depth_changed(self, depth: int):
        self.rag_engine.set_context_depth(depth)

    def on_tts_toggled(self, enabled: bool):
        self.auto_speak_enabled = enabled
        notice = "🔊 Auto-Read (TTS) Enabled" if enabled else "🔇 Auto-Read (TTS) Disabled"
        self.chat_view.add_system_notice(notice)

    def on_theme_selected(self, theme_name: str):
        # 1. Update appearance mode (Light vs Dark)
        ctk.set_appearance_mode("light" if "Light" in theme_name else "dark")

        # 2. Get new palette
        self.colors = get_theme_colors(theme_name)

        # 3. Re-color root & layout containers
        self.configure(fg_color=self.colors["bg_base"])
        self.header_bar.configure(
            fg_color=self.colors["bg_sidebar"],
            border_color=self.colors["border_color"]
        )
        self.export_btn.configure(
            fg_color=self.colors["chip_bg"],
            hover_color=self.colors["chip_hover"],
            text_color=self.colors["text_primary"]
        )
        self.clear_btn.configure(
            hover_color=self.colors["chip_hover"],
            text_color=self.colors["text_muted"]
        )

        # 4. Re-color status pill, sidebar, and chat view
        self.status_pill.apply_theme(self.colors)
        self.sidebar.apply_theme(self.colors, self.rag_engine.active_sources_meta)
        self.chat_view.apply_theme(self.colors)

        # 5. Re-color bottom input card & prompt chips
        self.progress_bar.configure(progress_color=self.colors["accent_primary"])
        self.input_card.configure(
            fg_color=self.colors["bg_input"],
            border_color=self.colors["border_color"]
        )
        self.attach_btn.configure(
            hover_color=self.colors["chip_hover"],
            text_color=self.colors["text_secondary"]
        )
        self.query_entry.apply_theme(self.colors)
        self.mic_btn.configure(
            hover_color=self.colors["chip_hover"],
            text_color=self.colors["text_secondary"]
        )
        if not self.is_processing:
            self.send_btn.configure(
                fg_color=self.colors["accent_primary"],
                hover_color=self.colors["accent_hover"]
            )

        if hasattr(self, "menu_btn"):
            self.menu_btn.configure(
                fg_color=self.colors["chip_bg"],
                hover_color=self.colors["chip_hover"],
                text_color=self.colors["text_primary"]
            )

        for chip in self.chips_scroll.winfo_children():
            if hasattr(chip, "apply_theme"):
                chip.apply_theme(self.colors)

        self.chat_view.add_system_notice(f"🎨 Theme instantly switched to: **{theme_name}**")

    def show_knowledge_stats(self):
        stats = self.rag_engine.get_knowledge_stats()
        KnowledgeStatsModal(self, stats)

    def open_image_viewer(self, img: Image.Image, query: str):
        ImageViewerModal(self, image=img, title_text=query)

    def trigger_export_chat(self):
        history = self.chat_view.get_conversation_history()
        ExportChatModal(self, history)

    def trigger_clear_chat(self):
        if messagebox.askyesno("Clear Chat", "Are you sure you want to clear the conversation history?"):
            self.voice_service.stop_speaking()
            self.chat_view.clear_chat()

    # ==========================================
    # THREAD-SAFE UI HELPERS
    # ==========================================
    def _safe_ui(self, fn):
        try:
            self.after(0, fn)
        except Exception:
            pass

    def _set_generating_state(self, is_generating: bool):
        self.is_processing = is_generating
        def action():
            try:
                if is_generating:
                    self.send_btn.configure(
                        text="🛑 Stop",
                        fg_color=self.colors["accent_danger"],
                        hover_color="#b91c1c"
                    )
                else:
                    self.send_btn.configure(
                        text="🔍 Search",
                        fg_color=self.colors["accent_primary"],
                        hover_color=self.colors["accent_hover"]
                    )
            except Exception:
                pass
        try:
            self.after(0, action)
        except Exception:
            pass

    def _set_progress(self, start=False, stop=False, val=None):
        def action():
            try:
                if start:
                    self.progress_bar.start()
                if stop:
                    self.progress_bar.stop()
                    self.progress_bar.set(0)
                if val is not None:
                    self.progress_bar.set(val)
            except Exception:
                pass
        try:
            self.after(0, action)
        except Exception:
            pass


# Backward compatibility alias
AIAyushStudioApp = AISearchStudioApp

if __name__ == "__main__":
    app = AISearchStudioApp()
    app.mainloop()
