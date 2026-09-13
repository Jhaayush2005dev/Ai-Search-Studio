import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk
from typing import Callable, List, Dict, Any, Optional

from core.config import get_theme_colors, AVAILABLE_MODELS, THEMES

class Sidebar(ctk.CTkFrame):
    """Modern developer sidebar with file manager, model parameters, and knowledge controls."""

    def __init__(
        self,
        master,
        on_upload_click: Callable[[], None],
        on_delete_source: Callable[[str], None],
        on_mode_change: Callable[[str], None],
        on_model_change: Callable[[str], None],
        on_temp_change: Callable[[float], None],
        on_depth_change: Callable[[int], None],
        on_theme_change: Callable[[str], None],
        on_tts_toggle: Callable[[bool], None],
        on_stats_click: Callable[[], None],
        on_close: Optional[Callable[[], None]] = None,
        **kwargs
    ):
        self.colors = get_theme_colors()
        super().__init__(master, width=280, corner_radius=0, fg_color=self.colors["bg_sidebar"], **kwargs)

        self.on_upload_click = on_upload_click
        self.on_delete_source = on_delete_source
        self.on_mode_change = on_mode_change
        self.on_model_change = on_model_change
        self.on_temp_change = on_temp_change
        self.on_depth_change = on_depth_change
        self.on_theme_change = on_theme_change
        self.on_tts_toggle = on_tts_toggle
        self.on_stats_click = on_stats_click
        self.on_close = on_close
        self.is_mobile_mode = False

        self.grid_rowconfigure(3, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._build_widgets()

    def _build_widgets(self):
        # 1. BRAND HEADER
        self.brand_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.brand_frame.grid(row=0, column=0, padx=16, pady=(16, 8), sticky="ew")

        self.logo_label = ctk.CTkLabel(
            self.brand_frame,
            text="🧠 Search Studio",
            font=("Segoe UI", 16, "bold"),
            text_color=self.colors["text_primary"]
        )
        self.logo_label.pack(side="left")

        # Close button for mobile drawer
        self.close_btn = ctk.CTkButton(
            self.brand_frame,
            text="✕",
            font=("Segoe UI", 13, "bold"),
            width=28,
            height=28,
            corner_radius=6,
            fg_color=self.colors["chip_bg"],
            hover_color=self.colors["chip_hover"],
            text_color=self.colors["text_primary"],
            command=self._handle_close
        )
        # Hidden by default on desktop

        self.ver_badge = ctk.CTkLabel(
            self.brand_frame,
            text="v2.0",
            font=("Segoe UI", 9),
            text_color=self.colors["text_muted"],
            fg_color=self.colors["chip_bg"],
            corner_radius=4,
            padx=5,
            pady=1
        )
        self.ver_badge.pack(side="right")

        # 2. UPLOAD & STATS BUTTONS
        btn_box = ctk.CTkFrame(self, fg_color="transparent")
        btn_box.grid(row=1, column=0, padx=16, pady=(4, 8), sticky="ew")
        btn_box.grid_columnconfigure(0, weight=3)
        btn_box.grid_columnconfigure(1, weight=1)

        self.upload_btn = ctk.CTkButton(
            btn_box,
            text="📂 Upload Files",
            font=("Segoe UI", 11, "bold"),
            height=32,
            corner_radius=6,
            fg_color=self.colors["accent_primary"],
            hover_color=self.colors["accent_hover"],
            text_color="#ffffff",
            command=self.on_upload_click
        )
        self.upload_btn.grid(row=0, column=0, padx=(0, 5), sticky="ew")

        self.stats_btn = ctk.CTkButton(
            btn_box,
            text="📊",
            font=("Segoe UI", 13),
            width=32,
            height=32,
            corner_radius=6,
            fg_color=self.colors["chip_bg"],
            hover_color=self.colors["chip_hover"],
            text_color=self.colors["text_secondary"],
            border_width=1,
            border_color=self.colors["border_color"],
            command=self.on_stats_click
        )
        self.stats_btn.grid(row=0, column=1, sticky="ew")

        # 3. ACTIVE SOURCES SECTION HEADER
        src_header = ctk.CTkFrame(self, fg_color="transparent")
        src_header.grid(row=2, column=0, padx=16, pady=(6, 2), sticky="ew")

        self.src_title = ctk.CTkLabel(
            src_header,
            text="UPLOADED FILES & DOCS",
            font=("Segoe UI", 9, "bold"),
            text_color=self.colors["text_muted"]
        )
        self.src_title.pack(side="left")

        self.src_count_badge = ctk.CTkLabel(
            src_header,
            text="0 files",
            font=("Segoe UI", 9),
            text_color=self.colors["text_muted"]
        )
        self.src_count_badge.pack(side="right")

        # 4. ACTIVE SOURCES SCROLLABLE FRAME
        self.sources_scroll = ctk.CTkScrollableFrame(
            self,
            fg_color=self.colors["bg_base"],
            corner_radius=6,
            border_width=1,
            border_color=self.colors["border_color"]
        )
        self.sources_scroll.grid(row=3, column=0, padx=16, pady=4, sticky="nsew")
        self.sources_scroll.grid_columnconfigure(0, weight=1)

        self.empty_label = ctk.CTkLabel(
            self.sources_scroll,
            text="No documents loaded.\nClick 'Upload Files' to add PDF, Word, CSV, Images...",
            font=("Segoe UI", 11, "italic"),
            text_color=self.colors["text_muted"],
            justify="center"
        )
        self.empty_label.pack(pady=30)

        # 5. SEARCH MODE & MODEL CONTROLS
        ctrl_frame = ctk.CTkFrame(self, fg_color="transparent")
        ctrl_frame.grid(row=4, column=0, padx=16, pady=(6, 10), sticky="ew")

        # Search Mode
        self.mode_lbl = ctk.CTkLabel(ctrl_frame, text="Search Mode", font=("Segoe UI", 9, "bold"), text_color=self.colors["text_muted"])
        self.mode_lbl.pack(anchor="w", pady=(0, 2))

        self.mode_menu = ctk.CTkOptionMenu(
            ctrl_frame,
            values=["Auto (Hybrid)", "Docs Only", "Web Only"],
            command=self.on_mode_change,
            font=("Segoe UI", 11),
            height=28,
            corner_radius=6,
            fg_color=self.colors["chip_bg"],
            button_color=self.colors["chip_hover"],
            text_color=self.colors["text_primary"]
        )
        self.mode_menu.pack(fill="x", pady=(0, 6))

        # Model Selector
        self.model_lbl = ctk.CTkLabel(ctrl_frame, text="AI Model", font=("Segoe UI", 9, "bold"), text_color=self.colors["text_muted"])
        self.model_lbl.pack(anchor="w", pady=(0, 2))

        self.model_menu = ctk.CTkOptionMenu(
            ctrl_frame,
            values=AVAILABLE_MODELS,
            command=self.on_model_change,
            font=("Segoe UI", 11),
            height=28,
            corner_radius=6,
            fg_color=self.colors["chip_bg"],
            button_color=self.colors["chip_hover"],
            text_color=self.colors["text_primary"]
        )
        self.model_menu.pack(fill="x", pady=(0, 6))

        # Retrieval Depth Slider
        slider_box = ctk.CTkFrame(ctrl_frame, fg_color="transparent")
        slider_box.pack(fill="x", pady=(0, 1))

        self.depth_lbl = ctk.CTkLabel(slider_box, text="Retrieval Depth", font=("Segoe UI", 9, "bold"), text_color=self.colors["text_muted"])
        self.depth_lbl.pack(side="left")

        self.depth_val_lbl = ctk.CTkLabel(slider_box, text="4", font=("Segoe UI", 9, "bold"), text_color=self.colors["accent_primary"])
        self.depth_val_lbl.pack(side="right")

        self.depth_slider = ctk.CTkSlider(
            ctrl_frame,
            from_=1,
            to=10,
            number_of_steps=9,
            height=12,
            progress_color=self.colors["accent_primary"],
            command=self._on_slider_depth
        )
        self.depth_slider.set(4)
        self.depth_slider.pack(fill="x", pady=(0, 6))

        # Auto Voice TTS Switch
        self.tts_switch = ctk.CTkSwitch(
            ctrl_frame,
            text="Auto-Read Aloud (TTS)",
            font=("Segoe UI", 10),
            text_color=self.colors["text_secondary"],
            progress_color=self.colors["accent_primary"],
            command=lambda: self.on_tts_toggle(self.tts_switch.get() == 1)
        )
        self.tts_switch.pack(anchor="w", pady=(2, 6))

        # Theme Selector
        self.theme_lbl = ctk.CTkLabel(ctrl_frame, text="Interface Theme", font=("Segoe UI", 9, "bold"), text_color=self.colors["text_muted"])
        self.theme_lbl.pack(anchor="w", pady=(0, 2))

        self.theme_menu = ctk.CTkOptionMenu(
            ctrl_frame,
            values=list(THEMES.keys()),
            command=self.on_theme_change,
            font=("Segoe UI", 11),
            height=28,
            corner_radius=6,
            fg_color=self.colors["chip_bg"],
            button_color=self.colors["chip_hover"],
            text_color=self.colors["text_primary"]
        )
        self.theme_menu.pack(fill="x")

    def _on_slider_depth(self, val):
        depth = int(val)
        if getattr(self, "_last_depth", None) != depth:
            self._last_depth = depth
            self.depth_val_lbl.configure(text=str(depth))
            self.on_depth_change(depth)

    def update_sources_list(self, sources_meta: List[Dict[str, Any]]):
        for w in self.sources_scroll.winfo_children():
            w.destroy()

        if not sources_meta:
            self.empty_label = ctk.CTkLabel(
                self.sources_scroll,
                text="No documents loaded.\nClick 'Upload Files' to add PDF, Word, CSV, Images...",
                font=("Segoe UI", 11, "italic"),
                text_color=self.colors["text_muted"],
                justify="center"
            )
            self.empty_label.pack(pady=30)
            self.src_count_badge.configure(text="0 files")
            return

        self.src_count_badge.configure(text=f"{len(sources_meta)} files")

        for s in sources_meta:
            filename = s.get("filename", "Unknown")
            ext = s.get("ext", "").lower()
            chunks = s.get("chunks", 0)

            icon = "📄"
            if ext == "pdf": icon = "📄"
            elif ext == "docx": icon = "📘"
            elif ext in ["csv", "xlsx"]: icon = "📊"
            elif ext in ["png", "jpg", "jpeg"]: icon = "🖼️"
            elif ext == "txt": icon = "📝"
            elif ext in ["py", "js", "html"]: icon = "💻"

            card = ctk.CTkFrame(
                self.sources_scroll,
                fg_color=self.colors["bg_card_ai"],
                corner_radius=6,
                border_width=1,
                border_color=self.colors["border_color"]
            )
            card.pack(fill="x", padx=2, pady=2)

            info_frame = ctk.CTkFrame(card, fg_color="transparent")
            info_frame.pack(side="left", fill="both", expand=True, padx=8, pady=4)

            name_lbl = ctk.CTkLabel(
                info_frame,
                text=f"{icon} {filename[:16]}{'...' if len(filename) > 16 else ''}",
                font=("Segoe UI", 11),
                text_color=self.colors["text_primary"],
                anchor="w"
            )
            name_lbl.pack(anchor="w")

            meta_lbl = ctk.CTkLabel(
                info_frame,
                text=f"{chunks} chunks • {s.get('size_kb', 0)} KB",
                font=("Segoe UI", 9),
                text_color=self.colors["text_muted"],
                anchor="w"
            )
            meta_lbl.pack(anchor="w")

            del_btn = ctk.CTkButton(
                card,
                text="✕",
                font=("Segoe UI", 10),
                width=22,
                height=22,
                corner_radius=4,
                fg_color="transparent",
                hover_color=self.colors["chip_hover"],
                text_color=self.colors["text_muted"],
                command=lambda fn=filename: self._confirm_delete(fn)
            )
            del_btn.pack(side="right", padx=4)

    def _handle_close(self):
        if self.on_close:
            self.on_close()

    def set_mobile_mode(self, is_mobile: bool):
        self.is_mobile_mode = is_mobile
        if is_mobile:
            self.ver_badge.pack_forget()
            self.close_btn.pack(side="right")
        else:
            self.close_btn.pack_forget()
            self.ver_badge.pack(side="right")

    def _confirm_delete(self, filename: str):
        if messagebox.askyesno("Remove Document", f"Remove '{filename}' and delete its vectors?"):
            self.on_delete_source(filename)

    def apply_theme(self, colors, active_sources=None):
        self.colors = colors
        self.configure(fg_color=colors["bg_sidebar"])
        self.logo_label.configure(text_color=colors["text_primary"])
        self.ver_badge.configure(fg_color=colors["chip_bg"], text_color=colors["text_muted"])
        self.close_btn.configure(fg_color=colors["chip_bg"], hover_color=colors["chip_hover"], text_color=colors["text_primary"])
        self.upload_btn.configure(fg_color=colors["accent_primary"], hover_color=colors["accent_hover"])
        self.stats_btn.configure(fg_color=colors["chip_bg"], hover_color=colors["chip_hover"], border_color=colors["border_color"], text_color=colors["text_secondary"])
        self.src_title.configure(text_color=colors["text_muted"])
        self.src_count_badge.configure(text_color=colors["text_muted"])
        self.sources_scroll.configure(fg_color=colors["bg_base"], border_color=colors["border_color"])

        # Labels
        if hasattr(self, "mode_lbl"):
            self.mode_lbl.configure(text_color=colors["text_muted"])
        if hasattr(self, "model_lbl"):
            self.model_lbl.configure(text_color=colors["text_muted"])
        if hasattr(self, "depth_lbl"):
            self.depth_lbl.configure(text_color=colors["text_muted"])
        if hasattr(self, "theme_lbl"):
            self.theme_lbl.configure(text_color=colors["text_muted"])

        # Menus & Controls
        self.mode_menu.configure(fg_color=colors["chip_bg"], button_color=colors["chip_hover"], text_color=colors["text_primary"])
        self.model_menu.configure(fg_color=colors["chip_bg"], button_color=colors["chip_hover"], text_color=colors["text_primary"])
        self.theme_menu.configure(fg_color=colors["chip_bg"], button_color=colors["chip_hover"], text_color=colors["text_primary"])
        self.depth_val_lbl.configure(text_color=colors["accent_primary"])
        self.depth_slider.configure(progress_color=colors["accent_primary"])
        self.tts_switch.configure(text_color=colors["text_secondary"], progress_color=colors["accent_primary"])

        # In-place source cards update without destroying/reconstructing widgets
        if hasattr(self, "empty_label") and self.empty_label and self.empty_label.winfo_exists():
            try:
                self.empty_label.configure(text_color=colors["text_muted"])
            except Exception:
                pass

        for card in self.sources_scroll.winfo_children():
            if isinstance(card, ctk.CTkFrame):
                try:
                    card.configure(fg_color=colors["bg_card_ai"], border_color=colors["border_color"])
                    for child in card.winfo_children():
                        if isinstance(child, ctk.CTkFrame): # info_frame
                            for lbl in child.winfo_children():
                                if isinstance(lbl, ctk.CTkLabel):
                                    # Main name vs meta info
                                    if "chunks" in str(lbl.cget("text")):
                                        lbl.configure(text_color=colors["text_muted"])
                                    else:
                                        lbl.configure(text_color=colors["text_primary"])
                        elif isinstance(child, ctk.CTkButton): # del_btn
                            child.configure(hover_color=colors["chip_hover"], text_color=colors["text_muted"])
                except Exception:
                    pass
