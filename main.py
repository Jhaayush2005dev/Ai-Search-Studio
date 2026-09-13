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
    DOCS_DIR, MISTRAL_API_KEY, get_theme_colors, set_current_theme,
    is_internet_available, THEMES, SUPPORTED_EXTENSIONS
)
from core.doc_loader import UniversalDocumentLoader
from core.rag_engine import RAGEngine
from core.session_manager import SessionManager
from core.vision_service import VisionService
from core.voice_service import VoiceService
from core.web_service import WebService

# UI Components & Modals
from ui.sidebar import Sidebar
from ui.chat_view import ChatView
from ui.components import StatusPill, PromptChip, ChatMessageCard, ModeActivationHUD, SearchInputBox, AttachmentMenuPopup, get_mic_icon
from ui.modals import ImageViewerModal, KnowledgeStatsModal, ExportChatModal, ChatHistoryModal

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
        self.vision_service = VisionService(api_key=MISTRAL_API_KEY)
        self.voice_service = VoiceService()
        self.web_service = WebService()
        self.session_manager = SessionManager()
        self.current_session_id: Optional[str] = None
        self.attached_image_path: Optional[str] = None
        self.attached_image: Optional[Image.Image] = None
        self.auto_speak_enabled = False
        self.is_processing = False

        # Build Main UI Layout
        self._setup_layout()
        self._build_header()
        self._build_chat_area()
        self._build_input_area()

        # Bind responsive layout resize & popup dismiss
        self.bind("<Configure>", self._on_window_configure)
        self.bind("<ButtonPress-1>", self._on_global_click, add=True)

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

        self.history_btn = ctk.CTkButton(
            self.header_bar,
            text="🕒 History",
            font=("Segoe UI", 11, "bold"),
            height=30,
            width=90,
            fg_color=self.colors["chip_bg"],
            hover_color=self.colors["chip_hover"],
            text_color=self.colors["text_primary"],
            command=self.trigger_history_modal
        )
        self.history_btn.pack(side="right", padx=(0, 8), pady=10)

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

        # 3. Attached Photo Preview Bar (Shown when an image is selected for Pixtral analysis)
        self.image_preview_bar = ctk.CTkFrame(
            self.bottom_panel,
            fg_color=self.colors["chip_bg"],
            corner_radius=8,
            border_width=1,
            border_color=self.colors["accent_primary"],
            height=32
        )
        self.img_preview_thumb = ctk.CTkLabel(self.image_preview_bar, text="🖼️", font=("Segoe UI", 12))
        self.img_preview_thumb.pack(side="left", padx=(8, 4), pady=4)

        self.img_preview_label = ctk.CTkLabel(
            self.image_preview_bar,
            text="",
            font=("Segoe UI", 11, "bold"),
            text_color=self.colors["text_primary"]
        )
        self.img_preview_label.pack(side="left", padx=4, pady=4)

        self.img_remove_btn = ctk.CTkButton(
            self.image_preview_bar,
            text="✕ Remove Photo",
            font=("Segoe UI", 10),
            height=22,
            width=85,
            corner_radius=4,
            fg_color="transparent",
            hover_color=self.colors["chip_hover"],
            text_color=self.colors["accent_danger"],
            command=self.clear_attached_image
        )
        self.img_remove_btn.pack(side="right", padx=6, pady=4)

        # 4. Input Controls Bar
        self.input_card = ctk.CTkFrame(
            self.bottom_panel,
            fg_color=self.colors["bg_input"],
            corner_radius=12,
            border_width=1,
            border_color=self.colors["border_color"]
        )
        self.input_card.pack(fill="x")
        self.input_card.grid_columnconfigure(1, weight=1)

        # Attach / Menu Button (+) -> Opens Gemini & ChatGPT style attachment menu
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
            command=self.show_attachment_menu
        )
        self.attach_btn.grid(row=0, column=0, padx=(6, 2), pady=6)

        # Text Entry (Supports Shift+Enter for multiline, Enter for search)
        self.query_entry = SearchInputBox(
            self.input_card,
            placeholder_text="Ask any question about your documents, code, or search the web...",
            on_submit=self.send_user_query
        )
        self.query_entry.grid(row=0, column=1, padx=6, pady=6, sticky="ew")

        # Microphone STT Button (Modern Studio / Voice Search Icon)
        self.mic_icon = get_mic_icon(self.colors["text_secondary"], size=(20, 20))
        self.mic_btn = ctk.CTkButton(
            self.input_card,
            image=self.mic_icon,
            text="",
            width=40,
            height=40,
            corner_radius=8,
            fg_color="transparent",
            hover_color=self.colors["chip_hover"],
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

        # 5. Floating Attachment Menu Card (Gemini / ChatGPT Style)
        self.attachment_popup = AttachmentMenuPopup(
            self.main_container,
            on_upload_photo=self.trigger_image_upload,
            on_upload_files=self.trigger_file_upload,
            on_search_image=self._quick_image_search_prompt,
            on_summarize=lambda: self.run_quick_ai_tool("summary"),
            on_quiz=lambda: self.run_quick_ai_tool("quiz"),
            on_state_change=self._on_attachment_menu_state_change
        )

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
                    self.history_btn.configure(text="🕒", width=34)
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
                    self.history_btn.configure(text="🕒 History", width=90)
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

        # Handle Attached Image for Pixtral Multimodal Analysis
        if self.attached_image is not None:
            img_to_analyze = self.attached_image
            display_query = query if query else "Answer and explain this photo in detail."
            self.query_entry.delete(0, "end")
            self.chat_view.add_user_message(display_query, image=img_to_analyze)
            self.voice_service.stop_speaking()
            self.clear_attached_image()
            self._auto_save_current_session()
            threading.Thread(target=self._pixtral_query_worker, args=(img_to_analyze, display_query), daemon=True).start()
            return

        if not query:
            return

        self.query_entry.delete(0, "end")
        self.chat_view.add_user_message(query)
        self.voice_service.stop_speaking()
        self._auto_save_current_session()

        # Handle Browsing & URL Navigation Intent (e.g. "open youtube", "youtube.com", "open github for langchain", "google quantum computing")
        nav_target = self.web_service.resolve_browsing_intent(query)
        if nav_target:
            target_url, display_title = nav_target
            self.chat_view.add_system_notice(f"🌐 Opening {display_title} in your browser...\n🔗 {target_url}")
            self._auto_save_current_session()
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
            self._safe_ui(self._auto_save_current_session)
            self._safe_ui(lambda: self.status_pill.set_status("🟢 Ready", "success"))

            # Auto TTS if enabled
            if self.auto_speak_enabled and final_response:
                self._safe_ui(lambda: self.speak_text(final_response, ai_card))

        except Exception as e:
            self._safe_ui(lambda err=e: self.chat_view.add_system_notice(f"❌ Error during response: {err}"))
            self._safe_ui(self._auto_save_current_session)
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
                    self._auto_save_current_session()
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

    def _pixtral_query_worker(self, image_input, prompt: str):
        self._set_generating_state(True)
        self._set_progress(start=True)
        self._safe_ui(lambda: self.status_pill.set_status("🖼️ Analyzing Image & Solving...", "warning"))

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

        card_event.wait(timeout=5.0)
        if not ai_card_container:
            self._set_progress(stop=True)
            self._set_generating_state(False)
            return
        ai_card = ai_card_container[0]

        def on_token(token: str):
            self._safe_ui(lambda: ai_card.append_token(token))
            self._safe_ui(self.chat_view.scroll_to_bottom)

        def on_status(status_msg: str):
            self._safe_ui(lambda: self.status_pill.set_status(status_msg, "warning"))

        try:
            search_context = ""
            citations = ["Mistral Pixtral Vision (pixtral-12b-2409)"]

            clean_p = prompt.strip() if prompt else ""
            default_prompts = [
                "analyze and describe this photo in detail.",
                "answer and explain this photo in detail.",
                "analyze this photo",
                "describe this photo"
            ]
            if clean_p and clean_p.lower() not in default_prompts:
                retrieved_text, src_citations = self.rag_engine.retrieve_context_for_query(clean_p, status_callback=on_status)
                if retrieved_text:
                    search_context = retrieved_text
                    citations.extend(src_citations)

            final_response = self.vision_service.analyze_image_stream(
                image_input=image_input,
                prompt=prompt,
                token_callback=on_token,
                status_callback=on_status,
                stop_check=lambda: self.rag_engine._abort_generation,
                search_context=search_context
            )

            # Finalize formatting and citations
            citations = list(dict.fromkeys(citations))
            self._safe_ui(lambda: self.chat_view.finalize_last_ai_message(final_response, citations))
            self._safe_ui(self._auto_save_current_session)
            self._safe_ui(lambda: self.status_pill.set_status("🟢 Ready", "success"))

            # Auto TTS if enabled
            if self.auto_speak_enabled and final_response:
                self.voice_service.speak(final_response)

        except Exception as e:
            self._safe_ui(lambda err=e: self.chat_view.add_system_notice(f"❌ Vision Analysis Error: {err}"))
            self._safe_ui(self._auto_save_current_session)
        finally:
            self._set_progress(stop=True)
            self._set_generating_state(False)

    def trigger_image_upload(self):
        """Allows user to upload a photo (JPEG/PNG/WEBP) for Pixtral image analysis."""
        file_path = filedialog.askopenfilename(
            title="Select Photo for AI Vision Analysis",
            filetypes=[
                ("Image Files", "*.png *.jpg *.jpeg *.webp *.bmp"),
                ("PNG Images", "*.png"),
                ("JPEG Images", "*.jpg *.jpeg"),
                ("All Files", "*.*")
            ]
        )
        if not file_path:
            return

        try:
            img = Image.open(file_path)
            self.attached_image_path = file_path
            self.attached_image = img

            fname = Path(file_path).name
            sz_kb = round(os.path.getsize(file_path) / 1024, 1)

            self.img_preview_label.configure(text=f"{fname} ({sz_kb} KB)")
            self.image_preview_bar.pack(fill="x", pady=(0, 6), before=self.input_card)
            self.query_entry.configure(placeholder_text="Ask a question about this image (or click Search to analyze)...")
            try:
                self.query_entry.textbox.focus_set()
            except Exception:
                pass
        except Exception as e:
            messagebox.showerror("Image Load Error", f"Failed to open image file:\n{e}")

    def clear_attached_image(self):
        """Clears the currently attached photo."""
        self.attached_image_path = None
        self.attached_image = None
        try:
            self.image_preview_bar.pack_forget()
        except Exception:
            pass
        placeholder = "Ask question or search web..." if self.is_mobile else "Ask any question about your documents, code, or search the web..."
        self.query_entry.configure(placeholder_text=placeholder)

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
    # FILE & PHOTO ATTACHMENTS (Gemini / ChatGPT Style)
    # ==========================================
    def show_attachment_menu(self):
        """Displays / toggles Gemini/ChatGPT-style attachment popup menu on clicking '+'."""
        if hasattr(self, "attachment_popup"):
            self.attachment_popup.toggle(self.attach_btn)

    def _on_attachment_menu_state_change(self, is_open: bool):
        """Switches the attachment button symbol between '+' and '✕' smoothly."""
        try:
            if is_open:
                self.attach_btn.configure(
                    text="✕",
                    font=("Segoe UI", 13, "bold"),
                    text_color=self.colors.get("text_primary", "#f1f5f9")
                )
            else:
                self.attach_btn.configure(
                    text="+",
                    font=("Segoe UI", 18, "bold"),
                    text_color=self.colors.get("text_secondary", "#94a3b8")
                )
        except Exception:
            pass

    def _on_global_click(self, event):
        """Dismisses attachment popup when clicking anywhere outside."""
        try:
            if hasattr(self, "attachment_popup") and self.attachment_popup.is_visible():
                widget = event.widget
                is_on_btn = (widget == self.attach_btn or str(widget).startswith(str(self.attach_btn)))
                is_on_popup = (widget == self.attachment_popup or str(widget).startswith(str(self.attachment_popup)))
                if not is_on_btn and not is_on_popup:
                    self.attachment_popup.hide()
        except Exception:
            pass

    def _quick_image_search_prompt(self):
        self.query_entry.delete(0, "end")
        self.query_entry.insert(0, "Show me a picture of ")
        try:
            self.query_entry.textbox.focus_set()
        except Exception:
            pass

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
            self.voice_service.stop_speaking()
            self.chat_view.reset_all_tts_buttons()
            rec_icon = get_mic_icon("#ffffff", size=(20, 20))
            self.mic_btn.configure(image=rec_icon, text="", fg_color=self.colors["accent_danger"])
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
        self.mic_icon = get_mic_icon(self.colors["text_secondary"], size=(20, 20))
        self.mic_btn.configure(image=self.mic_icon, text="", fg_color="transparent")
        placeholder = "Ask question or search web..." if self.is_mobile else "Ask any question about your documents, code, or search the web..."
        self.query_entry.configure(placeholder_text=placeholder)
        self.status_pill.set_status("🟢 Ready", "success")

    def speak_text(self, text: str, card: Optional[ChatMessageCard] = None):
        """Triggers audio playback of message with dynamic Speak / Stop toggle."""
        # Check if this specific card (or global TTS) is already speaking
        is_this_card_speaking = getattr(card, "_is_speaking_card", False)

        if is_this_card_speaking or (card is None and self.voice_service.is_speaking):
            self.voice_service.stop_speaking()
            self.chat_view.reset_all_tts_buttons()
            self.status_pill.set_status("🟢 Ready", "success")
            return

        # Stop any active voice narration and reset other cards
        self.voice_service.stop_speaking()
        self.chat_view.reset_all_tts_buttons()

        if not text or not text.strip():
            return

        # Set active speaking state on card & status pill
        if card:
            card.set_speaking_state(True)
        self.status_pill.set_status("🔊 Speaking...", "success")

        def on_done():
            def ui_reset():
                if card:
                    card.set_speaking_state(False)
                self.status_pill.set_status("🟢 Ready", "success")
            self._safe_ui(ui_reset)

        self.voice_service.speak(text, callback_done=on_done)

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
            pass

    def on_model_selected(self, model: str):
        self.rag_engine.set_model(model)
        try:
            self.sidebar.model_menu.set(model)
        except Exception:
            pass

    def on_temp_changed(self, temp: float):
        self.rag_engine.set_temperature(temp)

    def on_depth_changed(self, depth: int):
        self.rag_engine.set_context_depth(depth)

    def on_tts_toggled(self, enabled: bool):
        self.auto_speak_enabled = enabled

    def on_theme_selected(self, theme_name: str):
        # 1. Update active theme in core config
        set_current_theme(theme_name)

        # 2. Update appearance mode (Light vs Dark)
        ctk.set_appearance_mode("light" if "Light" in theme_name else "dark")

        # 3. Get new palette
        self.colors = get_theme_colors(theme_name)

        # 4. Re-color root & layout containers
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
        self.history_btn.configure(
            fg_color=self.colors["chip_bg"],
            hover_color=self.colors["chip_hover"],
            text_color=self.colors["text_primary"]
        )
        self.clear_btn.configure(
            hover_color=self.colors["chip_hover"],
            text_color=self.colors["text_muted"]
        )

        # 5. Re-color status pill, sidebar, and chat view
        self.status_pill.apply_theme(self.colors)
        self.sidebar.apply_theme(self.colors, self.rag_engine.active_sources_meta)
        self.chat_view.apply_theme(self.colors)

        # 6. Re-color bottom input card & prompt chips
        self.progress_bar.configure(progress_color=self.colors["accent_primary"])
        self.input_card.configure(
            fg_color=self.colors["bg_input"],
            border_color=self.colors["border_color"]
        )
        if hasattr(self, "attachment_popup"):
            self.attachment_popup.apply_theme(self.colors)
            is_open = self.attachment_popup.is_visible()
            self.attach_btn.configure(
                hover_color=self.colors["chip_hover"],
                text_color=self.colors["text_primary"] if is_open else self.colors["text_secondary"]
            )
        else:
            self.attach_btn.configure(
                hover_color=self.colors["chip_hover"],
                text_color=self.colors["text_secondary"]
            )
        if hasattr(self, "image_preview_bar"):
            self.image_preview_bar.configure(
                fg_color=self.colors["chip_bg"],
                border_color=self.colors["accent_primary"]
            )
            self.img_preview_label.configure(text_color=self.colors["text_primary"])
            self.img_remove_btn.configure(
                hover_color=self.colors["chip_hover"],
                text_color=self.colors["accent_danger"]
            )
        self.query_entry.apply_theme(self.colors)
        self.mic_icon = get_mic_icon(self.colors["text_secondary"], size=(20, 20))
        self.mic_btn.configure(
            image=self.mic_icon,
            hover_color=self.colors["chip_hover"]
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

        if hasattr(self, "attachment_popup"):
            self.attachment_popup.apply_theme(self.colors)

    def _ensure_current_session(self) -> str:
        """Returns active session ID or creates a new one."""
        if not self.current_session_id:
            new_sess = self.session_manager.create_session()
            self.current_session_id = new_sess["id"]
        return self.current_session_id

    def _auto_save_current_session(self):
        """Auto-saves the live chat feed to the active session file."""
        try:
            sess_id = self._ensure_current_session()
            history = self.chat_view.get_conversation_history()
            if history:
                self.session_manager.save_session(sess_id, history)
        except Exception as e:
            print(f"Auto-save warning: {e}")

    def trigger_history_modal(self):
        """Opens the interactive Chat History & Session Activation modal."""
        if self.current_session_id:
            self._auto_save_current_session()

        ChatHistoryModal(
            self,
            session_manager=self.session_manager,
            current_session_id=self.current_session_id,
            on_activate_session=self.activate_session,
            on_new_chat=self.start_new_chat
        )

    def activate_session(self, session_id: str):
        """Restores a selected past session into the live screen and syncs conversational memory."""
        self.voice_service.stop_speaking()

        sess_data = self.session_manager.get_session(session_id)
        if not sess_data:
            messagebox.showerror("Error", f"Could not find chat session with ID: {session_id}")
            return

        messages = sess_data.get("messages", [])
        self.chat_view.load_messages(messages)
        self.current_session_id = session_id

        # Sync RAG Engine's conversational history memory so AI retains context
        from langchain_core.messages import HumanMessage, AIMessage
        self.rag_engine.chat_history = []
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "")
            if role == "user" and content:
                self.rag_engine.chat_history.append(HumanMessage(content=content))
            elif role == "ai" and content:
                self.rag_engine.chat_history.append(AIMessage(content=content))

        sess_title = sess_data.get("title", "Past Session")
        self.status_pill.set_status(f"🟢 Activated: {sess_title[:16]}..", "success")

    def start_new_chat(self):
        """Starts a clean, new chat conversation."""
        self.voice_service.stop_speaking()
        if self.current_session_id:
            self._auto_save_current_session()
        self.chat_view.clear_chat()
        self.rag_engine.chat_history = []
        self.current_session_id = None
        self.status_pill.set_status("🟢 Ready", "success")

    def show_knowledge_stats(self):
        stats = self.rag_engine.get_knowledge_stats()
        KnowledgeStatsModal(self, stats)

    def open_image_viewer(self, img: Image.Image, query: str):
        ImageViewerModal(self, image=img, title_text=query)

    def trigger_export_chat(self):
        history = self.chat_view.get_conversation_history()
        ExportChatModal(self, history)

    def trigger_clear_chat(self):
        if messagebox.askyesno("Clear Chat", "Are you sure you want to clear the conversation and start a new chat?"):
            self.start_new_chat()

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
