import time
import re
import os
import webbrowser
import tkinter as tk
import customtkinter as ctk
from datetime import datetime
from typing import Optional, Callable, List
from PIL import Image, ImageDraw

from core.config import get_theme_colors, DOCS_DIR

_MIC_ICON_CACHE = {}

def get_mic_icon(color: str = "#94a3b8", size: tuple = (20, 20)) -> ctk.CTkImage:
    """
    Renders and returns a crisp, anti-aliased modern studio/voice search microphone CTkImage
    matching Google/Material voice search design (vertical capsule, U-cradle, stem).
    """
    cache_key = (color, size)
    if cache_key in _MIC_ICON_CACHE:
        return _MIC_ICON_CACHE[cache_key]

    scale = 8
    tw, th = size
    w, h = tw * scale, th * scale
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    cx = tw / 2.0 * scale
    stroke = max(2.0 * scale * (tw / 24.0), 1.8 * scale)

    # 1. Hollow Capsule
    cap_w = 7.5 * scale * (tw / 24.0)
    cap_top = 2.0 * scale * (th / 24.0)
    cap_bot = 12.5 * scale * (th / 24.0)
    cap_left = cx - cap_w / 2.0
    cap_right = cx + cap_w / 2.0
    cap_r = cap_w / 2.0

    draw.rounded_rectangle(
        [cap_left, cap_top, cap_right, cap_bot],
        radius=cap_r,
        outline=color,
        width=int(round(stroke))
    )

    # 2. U-Cradle Arc
    crad_w = 15.0 * scale * (tw / 24.0)
    crad_top = 7.0 * scale * (th / 24.0)
    crad_bot = 16.5 * scale * (th / 24.0)
    crad_left = cx - crad_w / 2.0
    crad_right = cx + crad_w / 2.0

    arc_box = [crad_left, 2 * crad_top - crad_bot, crad_right, crad_bot]
    draw.arc(arc_box, start=0, end=180, fill=color, width=int(round(stroke)))

    # Rounded end caps for cradle
    r_cap = stroke / 2.0
    draw.ellipse([crad_right - stroke, crad_top - r_cap, crad_right, crad_top + r_cap], fill=color)
    draw.ellipse([crad_left, crad_top - r_cap, crad_left + stroke, crad_top + r_cap], fill=color)

    # 3. Stem
    stem_top = crad_bot
    stem_bot = 21.0 * scale * (th / 24.0)
    draw.line([cx, stem_top, cx, stem_bot], fill=color, width=int(round(stroke)))
    draw.ellipse([cx - r_cap, stem_bot - r_cap, cx + r_cap, stem_bot + r_cap], fill=color)

    pil_img = img.resize(size, Image.Resampling.LANCZOS)
    ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=size)
    _MIC_ICON_CACHE[cache_key] = ctk_img
    return ctk_img

def is_dark_palette(colors: dict) -> bool:
    """Accurately determines if the current color palette is dark mode using luminance."""
    bg = colors.get("bg_base", "#131316")
    try:
        hex_clean = bg.lstrip("#")
        if len(hex_clean) == 6:
            r, g, b = (int(hex_clean[i:i+2], 16) for i in (0, 2, 4))
            return (0.299 * r + 0.587 * g + 0.114 * b) < 128
    except Exception:
        pass
    return "light" not in str(bg).lower()

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
        is_dark = is_dark_palette(colors)
        self.textbox = ctk.CTkTextbox(
            self,
            font=("Consolas", 11),
            wrap="none",
            fg_color="transparent",
            text_color="#93c5fd" if is_dark else "#1e40af",
            activate_scrollbars=True
        )
        self.textbox.pack(fill="both", expand=True, padx=8, pady=(0, 6))
        self.textbox.insert("1.0", code_text)
        self.textbox.configure(state="disabled")

        lines = min(max(len(code_text.splitlines()), 3), 15)
        self.textbox.configure(height=lines * 20)

    def _copy_code(self):
        self.clipboard_clear()
        self.clipboard_append(self.code_text)
        self.copy_btn.configure(text="✅ Copied!", text_color="#10b981")
        self.after(2000, lambda: self.copy_btn.configure(text="📋 Copy", text_color=get_theme_colors()["text_secondary"]))

    def apply_theme(self, colors):
        self.configure(fg_color=colors["bg_code"], border_color=colors["border_color"])
        self.lang_label.configure(text_color=colors["text_muted"])
        self.copy_btn.configure(hover_color=colors["chip_hover"], text_color=colors["text_secondary"])
        is_dark = is_dark_palette(colors)
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
        self._link_urls = {} # tag_name -> target url
        self._link_counter = 0

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
        is_dark = is_dark_palette(colors)
        code_fg = "#93c5fd" if is_dark else "#1e40af"

        # Balanced heading margins and readable line height
        self.tag_configure("h1", font=("Segoe UI", 15, "bold"), foreground=accent, spacing1=6, spacing3=2)
        self.tag_configure("h2", font=("Segoe UI", 13, "bold"), foreground=accent, spacing1=4, spacing3=2)
        self.tag_configure("h3", font=("Segoe UI", 12, "bold"), foreground=colors.get("text_primary", "#ffffff"), spacing1=3, spacing3=1)
        self.tag_configure("bold", font=("Segoe UI", 12, "bold"))
        self.tag_configure("italic", font=("Segoe UI", 12, "italic"), foreground=text_muted)
        self.tag_configure("code_inline", font=("Consolas", 11), background=chip_bg, foreground=code_fg)
        self.tag_configure("bullet", lmargin1=6, lmargin2=20)
        self.tag_configure("link", foreground=accent, underline=True)
        self.configure(spacing2=2)

    def _setup_context_menu(self):
        self.menu = tk.Menu(self, tearoff=0, bg="#1e222b", fg="#f1f5f9", activebackground="#3b82f6", activeforeground="#ffffff", font=("Segoe UI", 10))

        def _popup(e):
            try:
                self.menu.delete(0, "end")

                # Detect if right-click was on an active hyperlink
                clicked_idx = self.index(f"@{e.x},{e.y}")
                tags = self.tag_names(clicked_idx)
                link_url = None
                for t in tags:
                    if t in self._link_urls:
                        link_url = self._link_urls[t]
                        break

                if link_url:
                    self.menu.add_command(label="🌐 Open Link in Browser", command=lambda u=link_url: webbrowser.open(u))
                    self.menu.add_command(label="🔗 Copy Link Address", command=lambda u=link_url: self._copy_text(u))
                    self.menu.add_separator()

                has_sel = bool(self.tag_ranges("sel"))
                self.menu.add_command(label="📋 Copy Selection (Ctrl+C)", command=self.copy_selection, state="normal" if has_sel else "disabled")
                self.menu.add_command(label="📄 Copy Entire Text", command=self.copy_all)
                self.menu.add_separator()
                self.menu.add_command(label="✨ Select All (Ctrl+A)", command=self.select_all)

                self.menu.tk_popup(e.x_root, e.y_root)
            finally:
                self.menu.grab_release()

        self.bind("<Button-3>", _popup)

    def _setup_keybindings(self):
        self.bind("<Control-c>", lambda e: self.copy_selection())
        self.bind("<Control-C>", lambda e: self.copy_selection())
        self.bind("<Control-a>", lambda e: (self.select_all(), "break"))
        self.bind("<Control-A>", lambda e: (self.select_all(), "break"))

    def _copy_text(self, text: str):
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
        except Exception:
            pass

    def copy_selection(self):
        try:
            sel = self.get("sel.first", "sel.last")
            if sel:
                self._copy_text(sel)
        except Exception:
            pass

    def copy_all(self):
        content = self.get("1.0", "end-1c")
        if content:
            self._copy_text(content)

    def select_all(self):
        self.tag_add("sel", "1.0", "end-1c")

    def append_text(self, text: str):
        try:
            self.configure(state="normal")
            self.insert("end", text)
            self.configure(state="disabled")
            # Quick height update during token streaming
            line_count = int(self.index("end-1c").split(".")[0])
            if getattr(self, "_current_height", None) != line_count:
                self._current_height = line_count
                self.configure(height=max(line_count, 1))
        except Exception:
            pass

    def set_markdown_text(self, markdown_text: str):
        try:
            self.configure(state="normal")
            self.delete("1.0", "end")
            self._link_urls = {}
            self._link_counter = 0
            self._parse_and_insert_markdown(markdown_text)
            self.configure(state="disabled")

            # Recalculate width for user cards
            if self.role == "user":
                raw_lines = markdown_text.split("\n") if markdown_text else [""]
                max_l = max(len(l) for l in raw_lines) if raw_lines else 14
                target_w = min(max(max_l + 3, 14), 65)
                self.configure(width=target_w)

            self.auto_fit_height(fast=False)
        except Exception:
            pass

    def _insert_link(self, label: str, url: str):
        """Inserts an interactive clickable hyperlink with hand cursor and browser launch."""
        clean_url = url.strip()
        if not clean_url.startswith(("http://", "https://", "ftp://", "mailto:", "file://")):
            clean_url = "https://" + clean_url

        self._link_counter += 1
        tag_name = f"link_tag_{self._link_counter}"
        self._link_urls[tag_name] = clean_url

        colors = self.colors or get_theme_colors()
        accent = colors.get("accent_primary", "#3b82f6")

        self.tag_configure(tag_name, foreground=accent, underline=True)
        self.tag_bind(tag_name, "<Enter>", lambda e: self.configure(cursor="hand2"))
        self.tag_bind(tag_name, "<Leave>", lambda e: self.configure(cursor="xterm"))

        def _open_url_event(event, u=clean_url):
            try:
                webbrowser.open(u)
            except Exception as ex:
                print(f"Failed opening URL {u}: {ex}")
            return "break"

        self.tag_bind(tag_name, "<Button-1>", _open_url_event)
        self.insert("end", label, (tag_name, "link"))

    def _parse_and_insert_markdown(self, text: str):
        clean_text = text.strip().replace("\r\n", "\n")
        # Collapse 3+ consecutive newlines down to 2
        clean_text = re.sub(r'\n{3,}', '\n\n', clean_text)
        lines = clean_text.split("\n")
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
        pattern = r"(\*\*[^*]+?\*\*|\*[^*]+?\*|`[^`]+?`|\[[^\]]+?\]\([^)]+?\)|https?://[^\s<>,;:\"'()\[\]]+|www\.[^\s<>,;:\"'()\[\]]+|\b[a-zA-Z0-9_\-]+\.(?:com|org|net|io|edu|gov|app|dev|ai|me)(?:/[^\s<>,;:\"'()\[\]]*)?)"
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
                    self._insert_link(label, url)
                else:
                    self.insert("end", part)
            elif part.startswith(("http://", "https://", "www.")) or re.match(r"^[a-zA-Z0-9_\-]+\.(?:com|org|net|io|edu|gov|app|dev|ai|me)", part):
                self._insert_link(part, part)
            else:
                self.insert("end", part)

    def auto_fit_height(self, fast: bool = False):
        """Dynamically calculates exact line height so all content fits perfectly with zero extra space."""
        try:
            if not self.winfo_exists():
                return
            if not fast and self.winfo_ismapped() and self.winfo_width() > 30:
                dlines = self.count("1.0", "end-1c", "displaylines")
                if dlines and dlines[0] > 0:
                    target_h = max(dlines[0], 1)
                else:
                    idx_lines = int(self.index("end-1c").split(".")[0])
                    target_h = max(idx_lines, 1)
            else:
                content = self.get("1.0", "end-1c")
                raw_lines = content.split("\n") if content else [""]
                if self.role == "user":
                    max_l = max(len(l) for l in raw_lines) if raw_lines else 14
                    w = min(max(max_l + 3, 14), 65)
                else:
                    w = 75

                est_lines = 0
                char_per_line = max(w - 2, 20)
                for l in raw_lines:
                    if not l:
                        est_lines += 1
                    else:
                        import math
                        est_lines += max(1, math.ceil(len(l) / char_per_line))
                target_h = max(est_lines, 1)

            if getattr(self, "_current_height", None) != target_h:
                self._current_height = target_h
                self.configure(height=target_h)
        except Exception:
            pass

    def apply_theme(self, colors, bg_color: str):
        self.colors = colors
        self._bg_color = bg_color
        self._fg_color = colors.get("text_primary", "#f1f5f9")
        accent = colors.get("accent_primary", "#3b82f6")
        self.configure(
            bg=bg_color,
            fg=self._fg_color,
            selectbackground=accent,
            insertbackground=self._fg_color
        )
        self.menu.configure(
            bg=colors.get("bg_sidebar", "#1e222b"),
            fg=self._fg_color,
            activebackground=accent
        )
        self._configure_tags()
        # Re-color active link tags
        for tag_name in self._link_urls.keys():
            self.tag_configure(tag_name, foreground=accent, underline=True)


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
        self._is_speaking_card = False

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

        # Selectable Text Widget (Supports direct click-drag selection, Ctrl+C, Context Menu, Active Links)
        self.text_widget = SelectableMessageText(
            self.content_frame,
            initial_text=initial_text,
            role=role,
            bg_color=bg_color,
            fg_color=self.colors["text_primary"]
        )
        self.text_widget.pack(fill="x", expand=True, anchor="w")
        self._child_text_widgets.append(self.text_widget)
        self.text_label = self.text_widget # Backwards compatibility

        # Citations Frame
        self.sources_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.sources_frame.pack(fill="x", padx=14, pady=(0, 8))
        self.sources_frame.pack_forget()

        self.bind("<Configure>", self._on_resize)

    def _on_resize(self, event):
        try:
            if not hasattr(self, "_last_width"):
                self._last_width = event.width
                return
            if abs(event.width - self._last_width) < 12:
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
        else:
            self.text_widget.auto_fit_height(fast=False)

    def _render_rich_content(self):
        try:
            if hasattr(self, "text_widget") and self.text_widget.winfo_exists():
                self.text_widget.pack_forget()
            for w in self.content_frame.winfo_children():
                if w != getattr(self, "text_widget", None) and w != getattr(self, "sources_frame", None):
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
                    txt_widget.pack(fill="x", expand=True, pady=4, anchor="w")
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
        except Exception as e:
            print(f"Error rendering rich content: {e}")

    def set_citations(self, citations: List[str]):
        """Avoids displaying sources row on response cards per user preference."""
        pass

    def _open_citation(self, src: str):
        """Opens citation web URL in browser or local document with default viewer."""
        if not src:
            return
        if src.startswith(("http://", "https://", "www.")):
            url = src if src.startswith(("http://", "https://")) else "https://" + src
            try:
                webbrowser.open(url)
            except Exception as e:
                print(f"Error opening citation link {url}: {e}")
        elif src == "DuckDuckGo Web Search" or "Web Search" in src:
            try:
                webbrowser.open("https://duckduckgo.com")
            except Exception:
                pass
        else:
            # Check local file in DOCS_DIR
            local_path = DOCS_DIR / src
            if local_path.exists():
                try:
                    os.startfile(str(local_path))
                except Exception:
                    pass
            elif os.path.exists(src):
                try:
                    os.startfile(src)
                except Exception:
                    pass

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

    def _handle_copy(self):
        self.clipboard_clear()
        self.clipboard_append(self.full_content)
        if hasattr(self, "copy_btn"):
            self.copy_btn.configure(text="✅ Copied!", text_color="#10b981")
            self.after(2000, lambda: self.copy_btn.configure(text="📋 Copy All", text_color=get_theme_colors()["text_muted"]))

    def _handle_tts(self):
        if self.on_tts_click:
            try:
                self.on_tts_click(self.full_content, self)
            except TypeError:
                self.on_tts_click(self.full_content)

    def set_speaking_state(self, is_speaking: bool):
        """Toggles the button between '🔊 Speak' and '⏹ Stop' with visual feedback."""
        self._is_speaking_card = is_speaking
        if hasattr(self, "tts_btn") and self.tts_btn.winfo_exists():
            if is_speaking:
                self.tts_btn.configure(
                    text="⏹ Stop",
                    text_color=self.colors.get("accent_danger", "#ef4444"),
                    hover_color=self.colors.get("chip_hover", "#292934")
                )
            else:
                self.tts_btn.configure(
                    text="🔊 Speak",
                    text_color=self.colors.get("text_muted", "#71717a"),
                    hover_color=self.colors.get("chip_hover", "#292934")
                )

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
            tts_color = colors.get("accent_danger", "#ef4444") if getattr(self, "_is_speaking_card", False) else colors["text_muted"]
            self.tts_btn.configure(hover_color=colors["chip_hover"], text_color=tts_color)
        if hasattr(self, "copy_btn"):
            self.copy_btn.configure(hover_color=colors["chip_hover"], text_color=colors["text_muted"])

        for code_card in self._child_code_cards:
            code_card.apply_theme(colors)

        # Update citations badges and headers in-place
        if hasattr(self, "sources_frame") and self.sources_frame.winfo_exists():
            for idx, child in enumerate(self.sources_frame.winfo_children()):
                if isinstance(child, ctk.CTkLabel):
                    child.configure(text_color=colors["text_muted"])
                elif isinstance(child, ctk.CTkButton):
                    child.configure(fg_color=colors["chip_bg"], hover_color=colors["chip_hover"], text_color=colors["text_secondary"])


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


class AttachmentMenuPopup(ctk.CTkFrame):
    """
    Modern Gemini / ChatGPT-style floating attachment menu card with rounded corners,
    icon options, and smooth hover highlights.
    """
    def __init__(self, master, on_upload_photo=None, on_upload_files=None, on_search_image=None, on_summarize=None, on_quiz=None, on_state_change=None, **kwargs):
        self.colors = get_theme_colors()
        super().__init__(
            master,
            width=230,
            fg_color=self.colors["bg_sidebar"],
            corner_radius=12,
            border_width=1,
            border_color=self.colors["border_color"],
            **kwargs
        )
        self.on_upload_photo = on_upload_photo
        self.on_upload_files = on_upload_files
        self.on_search_image = on_search_image
        self.on_summarize = on_summarize
        self.on_quiz = on_quiz
        self.on_state_change = on_state_change
        self._item_buttons = []

        self._build_items()

    def _build_items(self):
        items = [
            ("📷  Photos (Image Analysis)", self.on_upload_photo),
            ("📄  Upload Files & Docs", self.on_upload_files),
            ("🎨  Search Web Images", self.on_search_image),
            ("📝  Summarize Knowledge", self.on_summarize),
            ("🎯  Practice Quiz", self.on_quiz),
        ]

        for text, cmd in items:
            def _make_cmd(action):
                return lambda: self._trigger_action(action)

            btn = ctk.CTkButton(
                self,
                text=text,
                anchor="w",
                font=("Segoe UI", 11, "bold"),
                fg_color="transparent",
                hover_color=self.colors["chip_hover"],
                text_color=self.colors["text_primary"],
                height=34,
                corner_radius=8,
                command=_make_cmd(cmd)
            )
            btn.pack(fill="x", padx=6, pady=2)
            self._item_buttons.append(btn)

    def _trigger_action(self, action):
        self.hide()
        if action:
            action()

    def show(self, anchor_widget, offset_y=None):
        """Displays the popup right above the anchor widget (the '+' button)."""
        self.lift()
        self.colors = get_theme_colors()
        self.apply_theme(self.colors)
        if offset_y is None:
            offset_y = -len(self._item_buttons) * 38 - 14
        self.place(in_=anchor_widget, x=0, y=offset_y)
        if self.on_state_change:
            try:
                self.on_state_change(True)
            except Exception:
                pass

    def hide(self):
        try:
            self.place_forget()
        except Exception:
            pass
        if self.on_state_change:
            try:
                self.on_state_change(False)
            except Exception:
                pass

    def is_visible(self) -> bool:
        return bool(self.winfo_ismapped())

    def toggle(self, anchor_widget, offset_y=None):
        if self.is_visible():
            self.hide()
        else:
            self.show(anchor_widget, offset_y)

    def apply_theme(self, colors):
        self.colors = colors
        self.configure(
            fg_color=colors["bg_sidebar"],
            border_color=colors["border_color"]
        )
        for btn in self._item_buttons:
            btn.configure(
                hover_color=colors["chip_hover"],
                text_color=colors["text_primary"]
            )
