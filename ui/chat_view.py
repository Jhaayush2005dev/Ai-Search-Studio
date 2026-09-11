import sys
import tkinter as tk
import customtkinter as ctk
from typing import Optional, Callable, List, Dict, Any
from datetime import datetime
from PIL import Image

from core.config import get_theme_colors
from ui.components import ChatMessageCard

class ChatView(ctk.CTkScrollableFrame):
    """Scrollable feed of chat cards with response display scrolling and streaming support."""

    def __init__(
        self,
        master,
        on_tts_click: Optional[Callable[[str], None]] = None,
        on_view_image: Optional[Callable[[Image.Image, str], None]] = None,
        **kwargs
    ):
        self.colors = get_theme_colors()
        super().__init__(
            master,
            fg_color=self.colors["bg_base"],
            corner_radius=0,
            **kwargs
        )
        self.on_tts_click = on_tts_click
        self.on_view_image = on_view_image

        self.grid_columnconfigure(0, weight=1)
        self.messages: List[Dict[str, Any]] = []
        self._cards: List[ChatMessageCard] = []
        self.is_mobile_mode = False

        # Touch & mouse drag scrolling state
        self._drag_y = 0
        self._is_dragging = False

        # Bind touch/mouse drag scrolling to canvas and self
        try:
            self._parent_canvas.bind("<ButtonPress-1>", self._on_drag_start, add=True)
            self._parent_canvas.bind("<B1-Motion>", self._on_drag_motion, add=True)
            self.bind("<ButtonPress-1>", self._on_drag_start, add=True)
            self.bind("<B1-Motion>", self._on_drag_motion, add=True)
        except Exception:
            pass

        self._show_welcome_hero()

    def _on_drag_start(self, event):
        self._drag_y = event.y_root
        self._is_dragging = False

    def _on_drag_motion(self, event):
        dy = event.y_root - self._drag_y
        if abs(dy) >= 2:
            self._is_dragging = True
            try:
                self._parent_canvas.yview_scroll(-int(dy), "units")
            except Exception:
                pass
            self._drag_y = event.y_root

    def _check_if_valid_scroll(self, widget):
        """Allows mouse wheel scrolling over any part of the chat view or its child response cards."""
        if widget == self._parent_canvas or widget == self:
            return True
        elif str(widget).startswith(str(self)) or str(widget).startswith(str(self._parent_canvas)) or str(widget).startswith(str(self._parent_frame)):
            return True
        elif widget.master is not None:
            return self._check_if_valid_scroll(widget.master)
        return False

    def _mouse_wheel_all(self, event):
        """Unified responsive mouse wheel handler for Windows, macOS, and Linux."""
        if self._check_if_valid_scroll(event.widget):
            self._scroll_canvas(event)

    def _scroll_canvas(self, event):
        """Scrolls the canvas with natural, responsive velocity."""
        try:
            if not hasattr(self, "_parent_canvas") or not self._parent_canvas.winfo_exists():
                return
            if sys.platform.startswith("win"):
                # On Windows with yscrollincrement=1, event.delta is 120 per notch.
                # delta / 2 gives 60px per notch (standard natural browser/editor scrolling speed).
                step = -int(event.delta / 2)
                if getattr(self, "_shift_pressed", False):
                    self._parent_canvas.xview("scroll", step, "units")
                else:
                    self._parent_canvas.yview("scroll", step, "units")
            elif sys.platform == "darwin":
                step = -int(event.delta * 2)
                if getattr(self, "_shift_pressed", False):
                    self._parent_canvas.xview("scroll", step, "units")
                else:
                    self._parent_canvas.yview("scroll", step, "units")
            else:
                # Linux (Button-4 / Button-5)
                step = -2 if (hasattr(event, "num") and event.num == 4) else 2
                if getattr(self, "_shift_pressed", False):
                    self._parent_canvas.xview_scroll(step, "units")
                else:
                    self._parent_canvas.yview_scroll(step, "units")
        except Exception:
            pass

    def bind_scroll_recursive(self, widget):
        """Recursively binds mouse wheel to all descendant widgets so hovering anywhere over response cards scrolls the feed."""
        if not widget:
            return

        def _on_wheel(e):
            self._scroll_canvas(e)
            return "break"

        for evt in ["<MouseWheel>", "<Button-4>", "<Button-5>"]:
            try:
                widget.bind(evt, _on_wheel, add=True)
            except Exception:
                pass
            for attr in ["_textbox", "_label", "_canvas", "_parent_frame", "_frame", "_entry"]:
                if hasattr(widget, attr):
                    target = getattr(widget, attr)
                    if target and hasattr(target, "bind"):
                        try:
                            target.bind(evt, _on_wheel, add=True)
                        except Exception:
                            pass

        try:
            for child in widget.winfo_children():
                self.bind_scroll_recursive(child)
        except Exception:
            pass

    def set_mobile_mode(self, is_mobile: bool):
        """Switches chat view layout padding and hero grid between mobile and desktop."""
        if self.is_mobile_mode == is_mobile:
            return
        self.is_mobile_mode = is_mobile

        side_pad = 8 if is_mobile else 25

        # Update existing message cards padding
        for idx, card in enumerate(self._cards):
            is_user = (getattr(card, "role", "") == "user")
            card.grid_configure(padx=side_pad, sticky="e" if is_user else "ew")

        # Update hero frame if present
        if hasattr(self, "hero_frame") and self.hero_frame:
            self.hero_frame.destroy()
            self._show_welcome_hero()

    def _show_welcome_hero(self):
        """Displays modern welcome banner and feature highlights when chat is empty."""
        side_pad = 8 if self.is_mobile_mode else 25
        vert_pad = 12 if self.is_mobile_mode else 30

        self.hero_frame = ctk.CTkFrame(
            self,
            fg_color=self.colors["bg_sidebar"],
            corner_radius=12,
            border_width=1,
            border_color=self.colors["border_color"]
        )
        self.hero_frame.grid(row=0, column=0, padx=side_pad, pady=vert_pad, sticky="ew")

        # Welcome Icon & Title
        title_font_size = 15 if self.is_mobile_mode else 20
        title = ctk.CTkLabel(
            self.hero_frame,
            text="✨ Welcome to Search Studio",
            font=("Segoe UI", title_font_size, "bold"),
            text_color=self.colors["accent_primary"]
        )
        title.pack(anchor="w", padx=16 if self.is_mobile_mode else 24, pady=(16 if self.is_mobile_mode else 20, 4))

        desc_text = (
            "Ask questions from your documents, code, or query live web intelligence."
            if self.is_mobile_mode else
            "Your multi-modal RAG knowledge engine. Ask questions from your PDFs, Word documents,\ncode, spreadsheets, or query live web intelligence with voice & image support."
        )
        desc = ctk.CTkLabel(
            self.hero_frame,
            text=desc_text,
            font=("Segoe UI", 11 if self.is_mobile_mode else 13),
            text_color=self.colors["text_secondary"],
            justify="left"
        )
        desc.pack(anchor="w", padx=16 if self.is_mobile_mode else 24, pady=(0, 12 if self.is_mobile_mode else 16))

        # Quick Highlights Grid
        grid_frame = ctk.CTkFrame(self.hero_frame, fg_color="transparent")
        grid_frame.pack(fill="x", padx=12 if self.is_mobile_mode else 24, pady=(0, 16 if self.is_mobile_mode else 20))

        if self.is_mobile_mode:
            grid_frame.grid_columnconfigure(0, weight=1)
        else:
            grid_frame.grid_columnconfigure((0, 1), weight=1)

        features = [
            ("📄 Multi-Format Uploads", "PDF, Word (DOCX), CSV, Excel, TXT, Code & OCR"),
            ("⚡ Real-Time Streaming", "Instant token generation powered by Mistral AI"),
            ("🎙️ Two-Way Voice", "Speech-to-text input and natural voice read-aloud"),
            ("🌐 Live Web & Images", "Automatic search fallbacks and inline image discovery")
        ]

        for idx, (f_title, f_sub) in enumerate(features):
            if self.is_mobile_mode:
                row = idx
                col = 0
            else:
                row = idx // 2
                col = idx % 2

            f_card = ctk.CTkFrame(
                grid_frame,
                fg_color=self.colors["chip_bg"],
                corner_radius=8,
                border_width=1,
                border_color=self.colors["border_color"]
            )
            f_card.grid(row=row, column=col, padx=4, pady=4, sticky="ew")

            f_t = ctk.CTkLabel(f_card, text=f_title, font=("Segoe UI", 11, "bold"), text_color=self.colors["text_primary"])
            f_t.pack(anchor="w", padx=10, pady=(6, 1))

            f_s = ctk.CTkLabel(f_card, text=f_sub, font=("Segoe UI", 9 if self.is_mobile_mode else 10), text_color=self.colors["text_muted"])
            f_s.pack(anchor="w", padx=10, pady=(0, 6))

        self.bind_scroll_recursive(self.hero_frame)

    def remove_hero_if_needed(self):
        if hasattr(self, "hero_frame") and self.hero_frame:
            try:
                self.hero_frame.grid_forget()
                self.hero_frame.destroy()
            except Exception:
                pass
            self.hero_frame = None

    def add_user_message(self, text: str) -> ChatMessageCard:
        """Adds user chat card to feed (compact and right-aligned to fit content)."""
        self.remove_hero_if_needed()
        time_str = datetime.now().strftime("%I:%M %p")
        side_pad = 8 if self.is_mobile_mode else 25

        card = ChatMessageCard(
            self,
            role="user",
            initial_text=text,
            timestamp=time_str
        )
        row_idx = len(self._cards)
        card.grid(row=row_idx, column=0, padx=side_pad, pady=(4, 4), sticky="e")
        self.bind_scroll_recursive(card)

        self._cards.append(card)
        self.messages.append({"role": "user", "content": text, "timestamp": time_str})
        self.scroll_to_bottom()
        return card

    def add_ai_message(self, initial_text: str = "") -> ChatMessageCard:
        """Adds AI response card to feed for streaming or direct text (full-width expanded)."""
        self.remove_hero_if_needed()
        time_str = datetime.now().strftime("%I:%M %p")
        side_pad = 8 if self.is_mobile_mode else 25

        card = ChatMessageCard(
            self,
            role="ai",
            initial_text=initial_text,
            timestamp=time_str,
            on_tts_click=self.on_tts_click,
            on_view_image=self.on_view_image
        )
        row_idx = len(self._cards)
        card.grid(row=row_idx, column=0, padx=side_pad, pady=(4, 8), sticky="ew")
        self.bind_scroll_recursive(card)

        self._cards.append(card)
        self.messages.append({"role": "ai", "content": initial_text, "timestamp": time_str})
        self.scroll_to_bottom()
        return card

    def add_system_notice(self, text: str):
        """Adds a subtle system status notice pill/card."""
        self.remove_hero_if_needed()
        time_str = datetime.now().strftime("%I:%M %p")
        side_pad = 8 if self.is_mobile_mode else 25

        card = ChatMessageCard(
            self,
            role="system",
            initial_text=text,
            timestamp=time_str
        )
        row_idx = len(self._cards)
        card.grid(row=row_idx, column=0, padx=side_pad, pady=(2, 4), sticky="ew")
        self.bind_scroll_recursive(card)
        self._cards.append(card)
        self.scroll_to_bottom()

    def finalize_last_ai_message(self, full_text: str, citations: Optional[List[str]] = None):
        """Finalizes the last message in memory and UI once generation ends."""
        if self._cards and self.messages:
            last_card = self._cards[-1]
            last_msg = self.messages[-1]
            if last_msg["role"] == "ai":
                last_msg["content"] = full_text
                if citations:
                    last_msg["citations"] = citations
                    last_card.set_citations(citations)
                last_card.finalize_content(full_text)
                self.bind_scroll_recursive(last_card)
        self.scroll_to_bottom()

    def clear_chat(self):
        """Clears all cards and resets to welcome hero."""
        for card in self._cards:
            card.destroy()
        self._cards = []
        self.messages = []
        self._show_welcome_hero()

    def get_conversation_history(self) -> List[Dict[str, Any]]:
        return self.messages

    def scroll_to_bottom(self):
        if getattr(self, "_scroll_pending", False):
            return
        self._scroll_pending = True
        def _do_scroll():
            self._scroll_pending = False
            try:
                if hasattr(self, "_parent_canvas") and self._parent_canvas.winfo_exists():
                    self._parent_canvas.yview_moveto(1.0)
            except Exception:
                pass
        self.after(30, _do_scroll)

    def apply_theme(self, colors):
        """Dynamically re-colors the chat view and all its active message cards."""
        self.colors = colors
        self.configure(fg_color=colors["bg_base"])

        if hasattr(self, "hero_frame") and self.hero_frame:
            self.hero_frame.configure(fg_color=colors["bg_sidebar"], border_color=colors["border_color"])

        for card in self._cards:
            card.apply_theme(colors)
