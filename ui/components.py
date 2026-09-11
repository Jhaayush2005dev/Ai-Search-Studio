import time
import re
import tkinter as tk
import customtkinter as ctk
from datetime import datetime
from typing import Optional, Callable, List
from PIL import Image

from core.config import get_theme_colors

class StatusPill(ctk.CTkFrame):
    """Clean developer pill badge showing engine status with subtle indicator dot."""
    def __init__(self, master, text="Syncing...", status_type="warning", **kwargs):
        self.colors = get_theme_colors()
        super().__init__(
            master,
            corner_radius=12,
            height=26,
            fg_color=self.colors["chip_bg"],
            border_width=1,
            border_color=self.colors["border_color"],
            **kwargs
        )
        self.current_text = text
        self.current_status_type = status_type
        self.compact_mode = False

        self.dot = ctk.CTkLabel(self, text="●", font=("Segoe UI", 11, "bold"), width=12)
        self.dot.pack(side="left", padx=(8, 4))

        self.label = ctk.CTkLabel(
            self,
            text=text,
            font=("Segoe UI", 11),
            text_color=self.colors["text_secondary"]
        )
        self.label.pack(side="left", padx=(0, 10))

        self.set_status(text, status_type)

    def set_compact(self, compact: bool):
        self.compact_mode = compact
        self._render_text()

    def _render_text(self):
        txt = self.current_text
        if self.compact_mode and len(txt) > 18:
            txt = txt[:16] + ".."
        self.label.configure(text=txt)

    def set_status(self, text: str, status_type: str = "success"):
        self.current_text = text
        self.current_status_type = status_type
        self.colors = get_theme_colors()

        if status_type == "success":
            dot_color = self.colors["accent_success"]
        elif status_type == "warning":
            dot_color = self.colors["accent_warning"]
        elif status_type == "danger":
            dot_color = self.colors["accent_danger"]
        else:
            dot_color = self.colors["accent_primary"]

        self.configure(
            fg_color=self.colors["chip_bg"],
            border_color=self.colors["border_color"]
        )
        self.dot.configure(text_color=dot_color)
        self.label.configure(text_color=self.colors["text_secondary"])
        self._render_text()

    def apply_theme(self, colors):
        self.colors = colors
        self.set_status(self.current_text, self.current_status_type)


class PromptChip(ctk.CTkButton):
    """Subtle developer prompt chip button."""
    def __init__(self, master, text: str, icon: str = "", command: Optional[Callable] = None, **kwargs):
        colors = get_theme_colors()
        display_text = f"{icon} {text}".strip()
        super().__init__(
            master,
            text=display_text,
            command=command,
            font=("Segoe UI", 11),
            height=28,
            corner_radius=14,
            fg_color=colors["chip_bg"],
            hover_color=colors["chip_hover"],
            text_color=colors["text_secondary"],
            border_width=1,
            border_color=colors["border_color"],
            **kwargs
        )

    def apply_theme(self, colors):
        self.configure(
            fg_color=colors["chip_bg"],
            hover_color=colors["chip_hover"],
            text_color=colors["text_secondary"],
            border_color=colors["border_color"]
        )


class ModeActivationHUD(ctk.CTkFrame):
    """Full-screen centered HUD card with glow animation and voice announcement when switching search modes."""

    MODE_CONFIGS = {
        "Auto (Hybrid)": {
            "title": "HYBRID INTELLIGENCE",
            "tagline": "Local Knowledge Base + Live Web Fallback Active",
            "icon": "🔄",
            "color": "#6366f1",
            "voice": "Hybrid search mode activated."
        },
        "Docs Only": {
            "title": "DOCUMENTS ONLY",
            "tagline": "Strict Local Knowledge Base Retrieval Active",
            "icon": "📄",
            "color": "#10b981",
            "voice": "Document search mode activated."
        },
        "Web Only": {
            "title": "LIVE WEB RESEARCH",
            "tagline": "Real-time Online Search Engine Active",
            "icon": "🌐",
            "color": "#0ea5e9",
            "voice": "Web search mode activated."
        }
    }

    def __init__(self, master, **kwargs):
        colors = get_theme_colors()
        super().__init__(
            master,
            corner_radius=18,
            border_width=2,
            fg_color=colors["bg_card_ai"],
            border_color=colors["accent_primary"],
            **kwargs
        )
        self.colors = colors
        self._anim_job = None

        inner = ctk.CTkFrame(self, fg_color="transparent")
        inner.pack(padx=24, pady=20)

        # Glowing Icon Box
        self.icon_box = ctk.CTkFrame(inner, width=56, height=56, corner_radius=28, fg_color=self.colors["chip_bg"])
        self.icon_box.pack(pady=(0, 8))
        self.icon_box.pack_propagate(False)

        self.icon_lbl = ctk.CTkLabel(self.icon_box, text="🔄", font=("Segoe UI", 26))
        self.icon_lbl.place(relx=0.5, rely=0.5, anchor="center")

        # Badge
        self.badge_lbl = ctk.CTkLabel(
            inner,
            text="● MODE ENGAGED",
            font=("Segoe UI", 9, "bold"),
            text_color="#ffffff",
            fg_color=self.colors["accent_primary"],
            corner_radius=6,
            padx=8,
            pady=2
        )
        self.badge_lbl.pack(pady=(0, 6))

        # Title
        self.title_lbl = ctk.CTkLabel(
            inner,
            text="HYBRID MODE",
            font=("Segoe UI", 15, "bold"),
            text_color="#ffffff"
        )
        self.title_lbl.pack(pady=(0, 3))

        # Tagline
        self.tagline_lbl = ctk.CTkLabel(
            inner,
            text="Intelligent Local + Web Fallback",
            font=("Segoe UI", 11),
            text_color=self.colors["text_secondary"]
        )
        self.tagline_lbl.pack(pady=(0, 10))

        # Animated Progress Line
        self.progress = ctk.CTkProgressBar(inner, height=3, width=220, progress_color=self.colors["accent_primary"])
        self.progress.pack()
        self.progress.set(0)

    def trigger(self, mode_name: str, voice_callback: Optional[Callable[[str], None]] = None):
        """Displays the animated HUD card and triggers voice."""
        if self._anim_job:
            try:
                self.after_cancel(self._anim_job)
            except Exception:
                pass

        cfg = self.MODE_CONFIGS.get(mode_name, self.MODE_CONFIGS["Auto (Hybrid)"])
        accent = cfg["color"]

        self.colors = get_theme_colors()
        self.configure(
            fg_color=self.colors["bg_card_ai"],
            border_color=accent
        )
        self.icon_box.configure(fg_color=self.colors["chip_bg"])
        self.icon_lbl.configure(text=cfg["icon"])
        self.badge_lbl.configure(fg_color=accent)
        self.title_lbl.configure(text=cfg["title"])
        self.tagline_lbl.configure(text=cfg["tagline"], text_color=self.colors["text_secondary"])
        self.progress.configure(progress_color=accent)
        self.progress.set(0)

        # Responsive progress bar width
        try:
            w = self.master.winfo_width()
            if w > 50:
                pb_w = min(240, max(160, w - 80))
                self.progress.configure(width=pb_w)
        except Exception:
            pass

        # Trigger voice announcement
        if voice_callback and cfg.get("voice"):
            voice_callback(cfg["voice"])

        # Animate Slide-in
        self.place(relx=0.5, rely=0.56, anchor="center")
        self.lift()
        self._animate_slide(current_rely=0.56, target_rely=0.50, step=0)

    def _animate_slide(self, current_rely: float, target_rely: float, step: int):
        if step < 12:
            new_rely = current_rely - ((current_rely - target_rely) / (12 - step))
            self.place(relx=0.5, rely=new_rely, anchor="center")
            self.progress.set((step + 1) / 12 * 0.15)
            self._anim_job = self.after(18, lambda: self._animate_slide(new_rely, target_rely, step + 1))
        else:
            self.place(relx=0.5, rely=target_rely, anchor="center")
            self._animate_progress(0.15, 0)

    def _animate_progress(self, val: float, step: int):
        # 50 steps * 48ms = 2.4 seconds hold duration
        if step < 50:
            new_val = val + (0.85 / 50)
            self.progress.set(min(new_val, 1.0))
            self._anim_job = self.after(48, lambda: self._animate_progress(new_val, step + 1))
        else:
            self._animate_slide_out(0.50, 0.44, 0)

    def _animate_slide_out(self, current_rely: float, target_rely: float, step: int):
        if step < 10:
            new_rely = current_rely - ((current_rely - target_rely) / (10 - step))
            self.place(relx=0.5, rely=new_rely, anchor="center")
            self._anim_job = self.after(18, lambda: self._animate_slide_out(new_rely, target_rely, step + 1))
        else:
            self.place_forget()


class CodeBlockCard(ctk.CTkFrame):
    """Refined code card with editor theme, language tag, and copy button."""
    def __init__(self, master, code_text: str, language: str = "", **kwargs):
        colors = get_theme_colors()
        super().__init__(
            master,
            corner_radius=8,
            fg_color=colors["bg_code"],
            border_width=1,
            border_color=colors["border_color"],
            **kwargs
        )
        self.code_text = code_text

        # Header Bar
        self.header = ctk.CTkFrame(self, fg_color="transparent", height=24)
        self.header.pack(fill="x", padx=10, pady=(6, 2))

        self.lang_label = ctk.CTkLabel(
            self.header,
            text=(language or "code").lower(),
            font=("Consolas", 10, "bold"),
            text_color=colors["text_muted"]
        )
        self.lang_label.pack(side="left")

        self.copy_btn = ctk.CTkButton(
            self.header,
            text="📋 Copy",
            font=("Segoe UI", 10),
            width=50,
            height=20,
            corner_radius=4,
            fg_color="transparent",
            hover_color=colors["chip_hover"],
            text_color=colors["text_secondary"],
            command=self._copy_code
        )
        self.copy_btn.pack(side="right")

        # Code display
        self.textbox = ctk.CTkTextbox(
            self,
            font=("Consolas", 11),
            wrap="none",
            fg_color="transparent",
            text_color="#93c5fd" if "Dark" in str(colors.get("bg_base")) or "#1" in str(colors.get("bg_base")) else "#1e40af",
            activate_scrollbars=True
        )
        self.textbox.pack(fill="both", expand=True, padx=8, pady=(0, 6))
        self.textbox.insert("1.0", code_text)
        self.textbox.configure(state="disabled")

        lines = min(max(len(code_text.splitlines()), 3), 15)
        self.textbox.configure(height=lines * 20)

        # Mousewheel scroll propagation to parent chat view
        self._bind_wheel_propagation()

    def _bind_wheel_propagation(self):
        def _propagate_wheel(e):
            w = self.master
            while w:
                if hasattr(w, "_scroll_canvas"):
                    w._scroll_canvas(e)
                    return "break"
                w = getattr(w, "master", None)
            return None

        for target in [self, self.header, self.lang_label, self.copy_btn, self.textbox, getattr(self.textbox, "_textbox", None)]:
            if target and hasattr(target, "bind"):
                for evt in ["<MouseWheel>", "<Button-4>", "<Button-5>"]:
                    try:
                        target.bind(evt, _propagate_wheel, add=True)
                    except Exception:
                        pass

    def _copy_code(self):
        self.clipboard_clear()
        self.clipboard_append(self.code_text)
        self.copy_btn.configure(text="✅ Copied!", text_color="#10b981")
        self.after(2000, lambda: self.copy_btn.configure(text="📋 Copy", text_color=get_theme_colors()["text_secondary"]))

    def apply_theme(self, colors):
        self.configure(fg_color=colors["bg_code"], border_color=colors["border_color"])
        self.lang_label.configure(text_color=colors["text_muted"])
        self.copy_btn.configure(hover_color=colors["chip_hover"], text_color=colors["text_secondary"])
        is_dark = "Dark" in str(colors.get("bg_base")) or "#1" in str(colors.get("bg_base"))
        txt_col = "#93c5fd" if is_dark else "#1e40af"
        self.textbox.configure(text_color=txt_col)


class SelectableMessageText(tk.Text):
    """
    Selectable, copyable, markdown-aware text widget that seamlessly fits
    inside chat cards without inner scrollbars and allows direct click-and-drag
    text selection, Ctrl+C copying, and right-click context menu.
    """
    def __init__(self, master, initial_text: str = "", role: str = "ai", bg_color: str = "#1e222b", fg_color: str = "#f1f5f9", **kwargs):
        self.colors = get_theme_colors()
        self.role = role
        lines = initial_text.split("\n") if initial_text else [""]
        calc_h = max(len(lines), 1)
        max_line_len = max(len(l) for l in lines) if lines else 20
        calc_w = min(max(max_line_len + 4, 16), 72) if role == "user" else 1

        super().__init__(
            master,
            font=("Segoe UI", 12),
            wrap="word",
            width=calc_w,
            height=calc_h,
            bg=bg_color,
            fg=fg_color,
            bd=0,
            highlightthickness=0,
            padx=0,
            pady=0,
            selectbackground="#3b82f6",
            selectforeground="#ffffff",
            insertbackground=fg_color,
            cursor="xterm",
            exportselection=True,
            **kwargs
        )
        self._bg_color = bg_color
        self._fg_color = fg_color
        self._current_height = calc_h
        self._configure_tags()
        self._setup_context_menu()
        self._setup_keybindings()

        if initial_text:
            self.set_markdown_text(initial_text)

    def _configure_tags(self):
        colors = self.colors or get_theme_colors()
        accent = colors.get("accent_primary", "#3b82f6")
        text_muted = colors.get("text_muted", "#94a3b8")
        chip_bg = colors.get("chip_bg", "#272f3d")
        is_dark = "Dark" in str(colors.get("bg_base")) or "#1" in str(colors.get("bg_base"))
        code_fg = "#93c5fd" if is_dark else "#1e40af"

        self.tag_configure("h1", font=("Segoe UI", 15, "bold"), foreground=accent, spacing1=8, spacing3=4)
        self.tag_configure("h2", font=("Segoe UI", 13, "bold"), foreground=accent, spacing1=6, spacing3=3)
        self.tag_configure("h3", font=("Segoe UI", 12, "bold"), foreground=colors.get("text_primary", "#ffffff"), spacing1=4, spacing3=2)
        self.tag_configure("bold", font=("Segoe UI", 12, "bold"))
        self.tag_configure("italic", font=("Segoe UI", 12, "italic"), foreground=text_muted)
        self.tag_configure("code_inline", font=("Consolas", 11), background=chip_bg, foreground=code_fg)
        self.tag_configure("bullet", lmargin1=8, lmargin2=22)
        self.tag_configure("link", foreground=accent, underline=True)

    def _setup_context_menu(self):
        self.menu = tk.Menu(self, tearoff=0, bg="#1e222b", fg="#f1f5f9", activebackground="#3b82f6", activeforeground="#ffffff", font=("Segoe UI", 10))
        self.menu.add_command(label="📋 Copy Selection (Ctrl+C)", command=self.copy_selection)
        self.menu.add_command(label="📄 Copy Entire Text", command=self.copy_all)
        self.menu.add_separator()
        self.menu.add_command(label="✨ Select All (Ctrl+A)", command=self.select_all)

        def _popup(e):
            try:
                has_sel = bool(self.tag_ranges("sel"))
                self.menu.entryconfigure(0, state="normal" if has_sel else "disabled")
                self.menu.tk_popup(e.x_root, e.y_root)
            finally:
                self.menu.grab_release()

        self.bind("<Button-3>", _popup)

    def _setup_keybindings(self):
        self.bind("<Control-c>", lambda e: self.copy_selection())
        self.bind("<Control-C>", lambda e: self.copy_selection())
        self.bind("<Control-a>", lambda e: (self.select_all(), "break"))
        self.bind("<Control-A>", lambda e: (self.select_all(), "break"))

    def copy_selection(self):
        try:
            sel = self.get("sel.first", "sel.last")
            if sel:
                self.clipboard_clear()
                self.clipboard_append(sel)
        except Exception:
            pass

    def copy_all(self):
        content = self.get("1.0", "end-1c")
        if content:
            self.clipboard_clear()
            self.clipboard_append(content)

    def select_all(self):
        self.tag_add("sel", "1.0", "end-1c")

    def append_text(self, text: str):
        self.configure(state="normal")
        self.insert("end", text)
        self.configure(state="disabled")
        self.auto_fit_height(fast=True)

    def set_markdown_text(self, markdown_text: str):
        self.configure(state="normal")
        self.delete("1.0", "end")
        self._parse_and_insert_markdown(markdown_text)
        self.configure(state="disabled")
        self.auto_fit_height(fast=False)

    def _parse_and_insert_markdown(self, text: str):
        lines = text.split("\n")
        for idx, line in enumerate(lines):
            stripped = line.strip()
            # Headers
            if stripped.startswith("### "):
                self.insert("end", stripped[4:], "h3")
            elif stripped.startswith("## "):
                self.insert("end", stripped[3:], "h2")
            elif stripped.startswith("# "):
                self.insert("end", stripped[2:], "h1")
            elif stripped.startswith(("- ", "* ", "• ")):
                self.insert("end", "• ", "bold")
                self._insert_inline_formatted(stripped[2:])
            elif re.match(r"^\d+\.\s", stripped):
                match = re.match(r"^(\d+\.\s)(.*)", stripped)
                if match:
                    self.insert("end", match.group(1), "bold")
                    self._insert_inline_formatted(match.group(2))
                else:
                    self._insert_inline_formatted(line)
            else:
                self._insert_inline_formatted(line)

            if idx < len(lines) - 1:
                self.insert("end", "\n")

    def _insert_inline_formatted(self, line: str):
        pattern = r"(\*\*[^*]+?\*\*|\*[^*]+?\*|`[^`]+?`|\[[^\]]+?\]\([^)]+?\))"
        parts = re.split(pattern, line)
        for part in parts:
            if not part:
                continue
            if part.startswith("**") and part.endswith("**") and len(part) >= 4:
                self.insert("end", part[2:-2], "bold")
            elif part.startswith("*") and part.endswith("*") and len(part) >= 2:
                self.insert("end", part[1:-1], "italic")
            elif part.startswith("`") and part.endswith("`") and len(part) >= 2:
                self.insert("end", f" {part[1:-1]} ", "code_inline")
            elif part.startswith("[") and "](" in part and part.endswith(")"):
                m = re.match(r"\[([^\]]+)\]\(([^)]+)\)", part)
                if m:
                    label, url = m.groups()
                    self.insert("end", label, "link")
                else:
                    self.insert("end", part)
            else:
                self.insert("end", part)

    def auto_fit_height(self, fast: bool = False):
        try:
            if fast or not self.winfo_ismapped():
                line_count = int(self.index("end-1c").split(".")[0])
            else:
                dlines = self.count("1.0", "end", "displaylines")
                line_count = dlines[0] if (dlines and dlines[0] > 0) else int(self.index("end-1c").split(".")[0])

            target_h = max(line_count, 1)
            if getattr(self, "_current_height", None) != target_h:
                self._current_height = target_h
                self.configure(height=target_h)
        except Exception:
            pass

    def apply_theme(self, colors, bg_color: str):
        self.colors = colors
        self._bg_color = bg_color
        self._fg_color = colors.get("text_primary", "#f1f5f9")
        self.configure(
            bg=bg_color,
            fg=self._fg_color,
            selectbackground=colors.get("accent_primary", "#3b82f6"),
            insertbackground=self._fg_color
        )
        self.menu.configure(
            bg=colors.get("bg_sidebar", "#1e222b"),
            fg=self._fg_color,
            activebackground=colors.get("accent_primary", "#3b82f6")
        )
        self._configure_tags()


class ChatMessageCard(ctk.CTkFrame):
    """Sleek developer message card with direct click-and-drag text selection and copy support."""

    def __init__(
        self,
        master,
        role: str, # "user" or "ai" or "system"
        initial_text: str = "",
        timestamp: Optional[str] = None,
        on_tts_click: Optional[Callable[[str], None]] = None,
        on_view_image: Optional[Callable[[Image.Image, str], None]] = None,
        **kwargs
    ):
        self.colors = get_theme_colors()
        self.role = role
        self.full_content = initial_text
        self.on_tts_click = on_tts_click
        self.on_view_image = on_view_image
        self.time_str = timestamp or datetime.now().strftime("%I:%M %p")
        self._child_code_cards: List[CodeBlockCard] = []
        self._child_text_widgets: List[SelectableMessageText] = []
        self._child_text_labels = self._child_text_widgets # Compatibility alias

        if role == "user":
            bg_color = self.colors["bg_card_user"]
            border_color = self.colors["border_color"]
            avatar = "👤 You"
            avatar_color = self.colors["text_secondary"]
        elif role == "ai":
            bg_color = self.colors["bg_card_ai"]
            border_color = self.colors["border_color"]
            avatar = "⚡ Assistant"
            avatar_color = self.colors["accent_primary"]
        else: # system
            bg_color = self.colors["chip_bg"]
            border_color = self.colors["border_color"]
            avatar = "ℹ️ System"
            avatar_color = self.colors["text_muted"]

        super().__init__(
            master,
            corner_radius=10,
            fg_color=bg_color,
            border_width=1,
            border_color=border_color,
            **kwargs
        )

        # Responsive padding based on role
        if role == "user":
            pad_x = 12
            pad_top_y = (6, 2)
            pad_bot_y = (0, 6)
            top_bar_h = 20
        elif role == "system":
            pad_x = 12
            pad_top_y = (4, 2)
            pad_bot_y = (0, 4)
            top_bar_h = 20
        else: # ai
            pad_x = 14
            pad_top_y = (8, 4)
            pad_bot_y = (2, 10)
            top_bar_h = 22

        # TOP BAR
        top_bar = ctk.CTkFrame(self, fg_color="transparent", height=top_bar_h)
        top_bar.pack(fill="x", padx=pad_x, pady=pad_top_y)

        self.avatar_lbl = ctk.CTkLabel(
            top_bar,
            text=avatar,
            font=("Segoe UI", 11, "bold"),
            text_color=avatar_color
        )
        self.avatar_lbl.pack(side="left")

        self.time_lbl = ctk.CTkLabel(
            top_bar,
            text=self.time_str,
            font=("Segoe UI", 10),
            text_color=self.colors["text_muted"]
        )
        self.time_lbl.pack(side="left", padx=8)

        # Action Buttons on Right
        if role == "ai":
            self.tts_btn = ctk.CTkButton(
                top_bar,
                text="🔊 Speak",
                font=("Segoe UI", 10),
                width=55,
                height=20,
                corner_radius=4,
                fg_color="transparent",
                hover_color=self.colors["chip_hover"],
                text_color=self.colors["text_muted"],
                command=self._handle_tts
            )
            self.tts_btn.pack(side="right", padx=(4, 0))

            self.copy_btn = ctk.CTkButton(
                top_bar,
                text="📋 Copy All",
                font=("Segoe UI", 10),
                width=65,
                height=20,
                corner_radius=4,
                fg_color="transparent",
                hover_color=self.colors["chip_hover"],
                text_color=self.colors["text_muted"],
                command=self._handle_copy
            )
            self.copy_btn.pack(side="right")

        # CONTENT FRAME
        self.content_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.content_frame.pack(fill="both", expand=True, padx=pad_x, pady=pad_bot_y)

        # Selectable Text Widget (Supports direct click-drag selection, Ctrl+C, Context Menu)
        self.text_widget = SelectableMessageText(
            self.content_frame,
            initial_text=initial_text,
            role=role,
            bg_color=bg_color,
            fg_color=self.colors["text_primary"]
        )
        self.text_widget.pack(fill="both", expand=True, anchor="w")
        self._child_text_widgets.append(self.text_widget)
        self.text_label = self.text_widget # Backwards compatibility

        # Citations Frame
        self.sources_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.sources_frame.pack(fill="x", padx=14, pady=(0, 8))
        self.sources_frame.pack_forget()

        self.bind("<Configure>", self._on_resize)
        self._bind_wheel_propagation()

    def _bind_wheel_propagation(self):
        """Propagates mouse wheel events from the card and all child labels/code to the ChatView canvas."""
        def _propagate_wheel(e):
            w = self.master
            while w:
                if hasattr(w, "_scroll_canvas"):
                    w._scroll_canvas(e)
                    return "break"
                w = getattr(w, "master", None)
            return None

        def _bind_sub(w):
            if not w:
                return
            for evt in ["<MouseWheel>", "<Button-4>", "<Button-5>"]:
                try:
                    w.bind(evt, _propagate_wheel, add=True)
                except Exception:
                    pass
                for attr in ["_textbox", "_label", "_canvas", "_parent_frame", "_frame"]:
                    if hasattr(w, attr):
                        sub = getattr(w, attr)
                        if sub and hasattr(sub, "bind"):
                            try:
                                sub.bind(evt, _propagate_wheel, add=True)
                            except Exception:
                                pass
            try:
                for child in w.winfo_children():
                    _bind_sub(child)
            except Exception:
                pass

        _bind_sub(self)

    def _on_resize(self, event):
        try:
            if not hasattr(self, "_last_width"):
                self._last_width = event.width
                return
            if event.width == self._last_width or event.width < 20:
                return
            self._last_width = event.width
            for txt in self._child_text_widgets:
                if txt and txt.winfo_exists():
                    txt.auto_fit_height(fast=False)
        except Exception:
            pass

    def append_token(self, token: str):
        self.full_content += token
        self.text_widget.append_text(token)

    def finalize_content(self, full_text: str = None):
        if full_text:
            self.full_content = full_text
            self.text_widget.set_markdown_text(full_text)

        if "```" in self.full_content and self.role == "ai":
            self._render_rich_content()

    def _render_rich_content(self):
        self.text_widget.pack_forget()
        for w in self.content_frame.winfo_children():
            if w != self.text_widget:
                try:
                    w.destroy()
                except Exception:
                    pass
        self._child_code_cards = []
        self._child_text_widgets = []
        self._child_text_labels = self._child_text_widgets

        pattern = r"```([a-zA-Z0-9_\-]*)\n([\s\S]*?)```"
        parts = re.split(pattern, self.full_content)

        bg_col = self.cget("fg_color")

        i = 0
        while i < len(parts):
            text_part = parts[i].strip()
            if text_part:
                txt_widget = SelectableMessageText(
                    self.content_frame,
                    initial_text=text_part,
                    bg_color=bg_col,
                    fg_color=self.colors["text_primary"]
                )
                txt_widget.pack(fill="x", expand=True, anchor="w", pady=4)
                self._child_text_widgets.append(txt_widget)

            if i + 2 < len(parts):
                lang = parts[i+1].strip()
                code_text = parts[i+2].strip()
                if code_text:
                    code_card = CodeBlockCard(self.content_frame, code_text=code_text, language=lang)
                    code_card.pack(fill="x", expand=True, pady=6)
                    self._child_code_cards.append(code_card)
                i += 3
            else:
                i += 1

        self._bind_wheel_propagation()

    def set_citations(self, citations: List[str]):
        if not citations:
            return
        self.sources_frame.pack(fill="x", padx=14, pady=(0, 8))
        for w in self.sources_frame.winfo_children():
            w.destroy()

        header = ctk.CTkLabel(
            self.sources_frame,
            text="📑 Sources:",
            font=("Segoe UI", 9, "bold"),
            text_color=self.colors["text_muted"]
        )
        header.pack(side="left", padx=(0, 6))

        for src in citations[:3]:
            short_src = src.split("\\")[-1].split("/")[-1]
            if len(short_src) > 16:
                short_src = short_src[:14] + ".."
            badge = ctk.CTkLabel(
                self.sources_frame,
                text=f"📌 {short_src}",
                font=("Segoe UI", 9),
                text_color=self.colors["text_secondary"],
                fg_color=self.colors["chip_bg"],
                corner_radius=4,
                padx=6,
                pady=1
            )
            badge.pack(side="left", padx=3)

        self._bind_wheel_propagation()

    def attach_image(self, img: Image.Image, query: str):
        preview_img = img.copy()
        preview_img.thumbnail((320, 220), Image.Resampling.LANCZOS)
        ctk_img = ctk.CTkImage(light_image=preview_img, dark_image=preview_img, size=preview_img.size)

        img_btn = ctk.CTkButton(
            self.content_frame,
            image=ctk_img,
            text="",
            fg_color="transparent",
            hover_color=self.colors["chip_hover"],
            command=lambda: self.on_view_image(img, query) if self.on_view_image else None
        )
        img_btn.pack(pady=8, anchor="w")

        hint = ctk.CTkLabel(
            self.content_frame,
            text="🔍 Click image to enlarge & save",
            font=("Segoe UI", 10, "italic"),
            text_color=self.colors["text_muted"]
        )
        hint.pack(anchor="w")
        self._bind_wheel_propagation()

    def _handle_copy(self):
        self.clipboard_clear()
        self.clipboard_append(self.full_content)
        if hasattr(self, "copy_btn"):
            self.copy_btn.configure(text="✅ Copied!", text_color="#10b981")
            self.after(2000, lambda: self.copy_btn.configure(text="📋 Copy All", text_color=get_theme_colors()["text_muted"]))

    def _handle_tts(self):
        if self.on_tts_click:
            self.on_tts_click(self.full_content)

    def apply_theme(self, colors):
        self.colors = colors
        if self.role == "user":
            bg_color = colors["bg_card_user"]
            border_color = colors["border_color"]
            avatar_color = colors["text_secondary"]
        elif self.role == "ai":
            bg_color = colors["bg_card_ai"]
            border_color = colors["border_color"]
            avatar_color = colors["accent_primary"]
        else:
            bg_color = colors["chip_bg"]
            border_color = colors["border_color"]
            avatar_color = colors["text_muted"]

        self.configure(fg_color=bg_color, border_color=border_color)
        self.avatar_lbl.configure(text_color=avatar_color)
        self.time_lbl.configure(text_color=colors["text_muted"])

        for txt in self._child_text_widgets:
            txt.apply_theme(colors, bg_color)

        if hasattr(self, "tts_btn"):
            self.tts_btn.configure(hover_color=colors["chip_hover"], text_color=colors["text_muted"])
        if hasattr(self, "copy_btn"):
            self.copy_btn.configure(hover_color=colors["chip_hover"], text_color=colors["text_muted"])

        for code_card in self._child_code_cards:
            code_card.apply_theme(colors)


class SearchInputBox(ctk.CTkFrame):
    """
    Intelligent multi-line search input box supporting:
    - Shift + Enter: Inserts a newline and expands input box height smoothly.
    - Enter: Submits and searches the query.
    - Ctrl + Enter: Submits and searches the query.
    - Automatic height expansion & auto-reset when query is submitted or cleared.
    - Clean placeholder text management.
    """
    def __init__(self, master, placeholder_text: str = "Ask any question about your documents, code, or search the web...", on_submit=None, **kwargs):
        self.colors = get_theme_colors()
        super().__init__(master, fg_color="transparent", **kwargs)
        self.placeholder_text = placeholder_text
        self.on_submit = on_submit
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.textbox = ctk.CTkTextbox(
            self,
            font=("Segoe UI", 13),
            fg_color="transparent",
            border_width=0,
            activate_scrollbars=False,
            height=38,
            wrap="word"
        )
        self.textbox.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        self._is_placeholder = False

        self._show_placeholder()

        self.textbox.bind("<FocusIn>", self._on_focus_in)
        self.textbox.bind("<FocusOut>", self._on_focus_out)
        self.textbox.bind("<Return>", self._on_return)
        self.textbox.bind("<KP_Enter>", self._on_return)
        self.textbox.bind("<KeyRelease>", self._on_key_release)
        self.textbox.bind("<Control-Return>", lambda e: self._trigger_submit())
        self.textbox.bind("<Control-KP_Enter>", lambda e: self._trigger_submit())

    def _show_placeholder(self):
        self._is_placeholder = True
        self.textbox.delete("1.0", "end")
        self.textbox.insert("1.0", self.placeholder_text)
        self.textbox.configure(text_color=self.colors.get("text_muted", "#64748b"))

    def _hide_placeholder(self):
        if self._is_placeholder:
            self._is_placeholder = False
            self.textbox.delete("1.0", "end")
            self.textbox.configure(text_color=self.colors.get("text_primary", "#f1f5f9"))

    def _on_focus_in(self, e):
        if self._is_placeholder:
            self._hide_placeholder()

    def _on_focus_out(self, e):
        content = self.textbox.get("1.0", "end-1c").strip()
        if not content:
            self._show_placeholder()
            self._adjust_height()

    def _trigger_submit(self):
        if self._is_placeholder:
            return "break"
        if self.on_submit:
            self.on_submit()
        return "break"

    def _on_return(self, e):
        if e.state & 0x0001:  # Shift key is pressed -> insert newline
            if self._is_placeholder:
                self._hide_placeholder()
            self.textbox.insert("insert", "\n")
            self._adjust_height()
            return "break"
        else:  # Normal Enter -> submit
            return self._trigger_submit()

    def _on_key_release(self, e):
        if not self._is_placeholder:
            self._adjust_height()

    def _adjust_height(self):
        if self._is_placeholder:
            target_h = 38
        else:
            content = self.textbox.get("1.0", "end-1c")
            lines = len(content.split("\n"))
            target_h = min(max(lines * 22 + 16, 38), 120)

        if getattr(self, "_current_h", None) != target_h:
            self._current_h = target_h
            self.textbox.configure(height=target_h)

    def get(self, *args):
        if self._is_placeholder:
            return ""
        return self.textbox.get("1.0", "end-1c")

    def delete(self, *args):
        self.textbox.delete("1.0", "end")
        self._show_placeholder()
        self._adjust_height()

    def insert(self, idx, text):
        if self._is_placeholder:
            self._hide_placeholder()
        self.textbox.delete("1.0", "end")
        self.textbox.insert("1.0", text)
        self.textbox.configure(text_color=self.colors.get("text_primary", "#f1f5f9"))
        self._adjust_height()

    def configure(self, **kwargs):
        if "placeholder_text" in kwargs:
            self.placeholder_text = kwargs.pop("placeholder_text")
            if self._is_placeholder:
                self._show_placeholder()
        if kwargs:
            self.textbox.configure(**kwargs)

    def apply_theme(self, colors):
        self.colors = colors
        if self._is_placeholder:
            self.textbox.configure(text_color=colors.get("text_muted", "#64748b"))
        else:
            self.textbox.configure(text_color=colors.get("text_primary", "#f1f5f9"))
