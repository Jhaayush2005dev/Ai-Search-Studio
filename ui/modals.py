import os
import json
import webbrowser
import threading
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from PIL import Image
from typing import Dict, Any, List, Optional

from core.config import get_theme_colors

class ImageViewerModal(ctk.CTkToplevel):
    """Modern modal for displaying, zooming, and saving images."""

    def __init__(self, master, image: Image.Image, title_text: str = "Image Preview", source_url: str = None):
        super().__init__(master)
        self.colors = get_theme_colors()
        self.image = image
        self.source_url = source_url

        self.title(f"🖼️ {title_text}")

        # Responsive geometry
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        w = min(640, max(320, screen_w - 30))
        h = min(660, max(380, screen_h - 60))
        self.geometry(f"{w}x{h}")
        self.minsize(min(320, w), min(350, h))
        self.attributes('-topmost', True)
        self.focus_force()

        self.configure(fg_color=self.colors["bg_base"])

        # Top Bar
        top_bar = ctk.CTkFrame(self, fg_color=self.colors["bg_sidebar"], height=45)
        top_bar.pack(fill="x", padx=10, pady=10)

        title_lbl = ctk.CTkLabel(
            top_bar,
            text=title_text[:24] + (".." if len(title_text) > 24 else ""),
            font=("Segoe UI", 13, "bold"),
            text_color=self.colors["text_primary"]
        )
        title_lbl.pack(side="left", padx=10)

        save_btn = ctk.CTkButton(
            top_bar,
            text="💾 Save",
            font=("Segoe UI", 11, "bold"),
            width=70,
            height=30,
            fg_color=self.colors["accent_primary"],
            hover_color=self.colors["accent_hover"],
            command=self._save_image
        )
        save_btn.pack(side="right", padx=6)

        if source_url and source_url.startswith("http"):
            web_btn = ctk.CTkButton(
                top_bar,
                text="🌐 URL",
                font=("Segoe UI", 11),
                width=65,
                height=30,
                fg_color=self.colors["chip_bg"],
                hover_color=self.colors["chip_hover"],
                text_color=self.colors["text_primary"],
                command=lambda: webbrowser.open(source_url)
            )
            web_btn.pack(side="right", padx=(0, 4))

        # Image Container
        img_container = ctk.CTkFrame(self, fg_color="transparent")
        img_container.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # Resize image for display
        display_img = image.copy()
        max_thumb_w = max(260, w - 40)
        max_thumb_h = max(240, h - 120)
        display_img.thumbnail((max_thumb_w, max_thumb_h), Image.Resampling.LANCZOS)
        self.ctk_img = ctk.CTkImage(light_image=display_img, dark_image=display_img, size=display_img.size)

        lbl = ctk.CTkLabel(img_container, image=self.ctk_img, text="")
        lbl.pack(expand=True, fill="both")

    def _save_image(self):
        file_path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG Image", "*.png"), ("JPEG Image", "*.jpg"), ("All Files", "*.*")]
        )
        if file_path:
            try:
                self.image.save(file_path)
                messagebox.showinfo("Saved", f"Image saved successfully to:\n{file_path}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed saving image:\n{e}")


class KnowledgeStatsModal(ctk.CTkToplevel):
    """Displays knowledge base analytics and loaded file statistics."""

    def __init__(self, master, stats: Dict[str, Any]):
        super().__init__(master)
        self.colors = get_theme_colors()
        self.title("📊 Knowledge Base Analytics")

        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        w = min(560, max(320, screen_w - 30))
        h = min(520, max(380, screen_h - 60))
        self.geometry(f"{w}x{h}")
        self.minsize(min(320, w), min(350, h))
        self.attributes('-topmost', True)
        self.focus_force()
        self.configure(fg_color=self.colors["bg_base"])

        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(16, 8))

        title = ctk.CTkLabel(
            header,
            text="📊 Knowledge Base Intelligence",
            font=("Segoe UI", 16 if w < 450 else 18, "bold"),
            text_color=self.colors["accent_primary"]
        )
        title.pack(anchor="w")

        subtitle = ctk.CTkLabel(
            header,
            text="Real-time statistics of vectors & uploaded documents",
            font=("Segoe UI", 10 if w < 450 else 11),
            text_color=self.colors["text_muted"]
        )
        subtitle.pack(anchor="w")

        # Stat Metric Cards
        metric_frame = ctk.CTkFrame(self, fg_color="transparent")
        metric_frame.pack(fill="x", padx=16, pady=8)
        metric_frame.grid_columnconfigure((0, 1, 2), weight=1)

        self._create_stat_card(metric_frame, 0, "📁 Uploaded Files", str(stats.get("total_files", 0)), self.colors["accent_primary"])
        self._create_stat_card(metric_frame, 1, "⚡ Chunks", str(stats.get("total_chunks", 0)), self.colors["accent_success"])
        self._create_stat_card(metric_frame, 2, "💾 Size", f"{stats.get('total_size_kb', 0)} KB", self.colors["accent_warning"])

        # Sources Table Header
        tbl_lbl = ctk.CTkLabel(
            self,
            text="DOCUMENT SOURCES BREAKDOWN",
            font=("Segoe UI", 10, "bold"),
            text_color=self.colors["text_muted"]
        )
        tbl_lbl.pack(anchor="w", padx=20, pady=(15, 5))

        # Sources List
        sources_scroll = ctk.CTkScrollableFrame(
            self,
            fg_color=self.colors["bg_sidebar"],
            corner_radius=8,
            border_width=1,
            border_color=self.colors["border_color"]
        )
        sources_scroll.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        sources_scroll.grid_columnconfigure(0, weight=1)

        sources = stats.get("sources", [])
        if not sources:
            no_docs = ctk.CTkLabel(
                sources_scroll,
                text="No documents uploaded yet. Upload files to populate knowledge.",
                font=("Segoe UI", 12, "italic"),
                text_color=self.colors["text_muted"]
            )
            no_docs.pack(pady=30)
        else:
            for idx, s in enumerate(sources):
                row = ctk.CTkFrame(sources_scroll, fg_color=self.colors["chip_bg"], corner_radius=6)
                row.pack(fill="x", padx=5, pady=4)

                icon = "📄"
                ext = s.get("ext", "")
                if ext == "pdf": icon = "📄"
                elif ext == "docx": icon = "📘"
                elif ext in ["csv", "xlsx"]: icon = "📊"
                elif ext in ["png", "jpg"]: icon = "🖼️"
                elif ext == "txt": icon = "📝"
                elif ext == "py": icon = "🐍"

                name_lbl = ctk.CTkLabel(
                    row,
                    text=f"{icon} {s.get('filename', 'Unknown')}",
                    font=("Segoe UI", 12, "bold"),
                    text_color=self.colors["text_primary"]
                )
                name_lbl.pack(side="left", padx=10, pady=8)

                meta_lbl = ctk.CTkLabel(
                    row,
                    text=f"{s.get('chunks', 0)} chunks • {s.get('size_kb', 0)} KB",
                    font=("Segoe UI", 11),
                    text_color=self.colors["text_secondary"]
                )
                meta_lbl.pack(side="right", padx=10)

    def _create_stat_card(self, master, col, title, value, color):
        card = ctk.CTkFrame(
            master,
            fg_color=self.colors["bg_sidebar"],
            corner_radius=10,
            border_width=1,
            border_color=self.colors["border_color"],
            height=70
        )
        card.grid(row=0, column=col, padx=5, sticky="ew")

        val_lbl = ctk.CTkLabel(card, text=value, font=("Segoe UI", 20, "bold"), text_color=color)
        val_lbl.pack(pady=(10, 0))

        title_lbl = ctk.CTkLabel(card, text=title, font=("Segoe UI", 10), text_color=self.colors["text_muted"])
        title_lbl.pack(pady=(0, 10))


class ExportChatModal(ctk.CTkToplevel):
    """Interactive modal for selecting specific chat messages and exporting with visual progress."""

    FORMAT_OPTIONS = [
        ("PDF Document (*.pdf)", ".pdf"),
        ("Word Document (*.docx)", ".docx"),
        ("Markdown Document (*.md)", ".md"),
        ("HTML Webpage (*.html)", ".html"),
        ("Plain Text Document (*.txt)", ".txt"),
        ("JSON Data (*.json)", ".json"),
    ]

    @staticmethod
    def export_conversation(messages: List[Dict[str, Any]], master=None):
        """Helper method for backwards-compatibility or static dispatch."""
        ExportChatModal(master, messages)

    def __init__(self, master, messages: List[Dict[str, Any]]):
        super().__init__(master)
        self.master = master
        self.colors = get_theme_colors()
        self.all_messages = messages or []

        self.title("💾 Export Chat Conversation")

        # Responsive geometry
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        w = min(680, max(360, screen_w - 40))
        h = min(720, max(460, screen_h - 60))
        self.geometry(f"{w}x{h}")
        self.minsize(min(340, w), min(400, h))
        self.attributes('-topmost', True)
        self.focus_force()
        self.configure(fg_color=self.colors["bg_base"])

        # State
        self.msg_vars: List[tk.BooleanVar] = []
        self.filter_mode = "all"

        # Check if conversation is empty
        if not self.all_messages:
            self._render_empty_state()
            return

        # Main Containers
        self.selection_container = ctk.CTkFrame(self, fg_color="transparent")
        self.selection_container.pack(fill="both", expand=True, padx=16, pady=16)

        self.progress_container = ctk.CTkFrame(self, fg_color="transparent")

        self._build_selection_ui()

    def _render_empty_state(self):
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=20, pady=20)

        lbl_icon = ctk.CTkLabel(frame, text="💬", font=("Segoe UI", 48))
        lbl_icon.pack(pady=(40, 10))

        lbl_title = ctk.CTkLabel(frame, text="No Messages to Export", font=("Segoe UI", 16, "bold"), text_color=self.colors["text_primary"])
        lbl_title.pack(pady=(0, 6))

        lbl_sub = ctk.CTkLabel(frame, text="The chat history is currently empty.\nStart a conversation to export messages.", font=("Segoe UI", 12), text_color=self.colors["text_muted"], justify="center")
        lbl_sub.pack(pady=(0, 20))

        btn_close = ctk.CTkButton(frame, text="Close", font=("Segoe UI", 12, "bold"), fg_color=self.colors["chip_bg"], hover_color=self.colors["chip_hover"], text_color=self.colors["text_primary"], width=100, command=self.destroy)
        btn_close.pack()

    def _build_selection_ui(self):
        # 1. Header Frame
        header_frame = ctk.CTkFrame(self.selection_container, fg_color="transparent")
        header_frame.pack(fill="x", pady=(0, 10))

        title_lbl = ctk.CTkLabel(
            header_frame,
            text="💾 Select Messages to Export",
            font=("Segoe UI", 15, "bold"),
            text_color=self.colors["text_primary"],
            anchor="w"
        )
        title_lbl.pack(fill="x")

        sub_lbl = ctk.CTkLabel(
            header_frame,
            text="Choose which questions, answers, or messages you want to include in your export file.",
            font=("Segoe UI", 11),
            text_color=self.colors["text_muted"],
            anchor="w"
        )
        sub_lbl.pack(fill="x", pady=(2, 0))

        # 2. Controls & Quick Filters Toolbar
        toolbar = ctk.CTkFrame(self.selection_container, fg_color=self.colors["bg_sidebar"], corner_radius=8, border_width=1, border_color=self.colors["border_color"])
        toolbar.pack(fill="x", pady=(0, 10), padx=0)

        # Quick action buttons
        btn_box = ctk.CTkFrame(toolbar, fg_color="transparent")
        btn_box.pack(side="left", padx=10, pady=8)

        btn_all = ctk.CTkButton(
            btn_box,
            text="✓ Select All",
            font=("Segoe UI", 11, "bold"),
            width=84,
            height=26,
            fg_color=self.colors["accent_primary"],
            hover_color=self.colors["accent_hover"],
            command=self._select_all
        )
        btn_all.pack(side="left", padx=(0, 6))

        btn_none = ctk.CTkButton(
            btn_box,
            text="✕ Clear All",
            font=("Segoe UI", 11),
            width=76,
            height=26,
            fg_color=self.colors["chip_bg"],
            hover_color=self.colors["chip_hover"],
            text_color=self.colors["text_primary"],
            command=self._deselect_all
        )
        btn_none.pack(side="left", padx=(0, 6))

        # Filter Segmented
        self.filter_segmented = ctk.CTkSegmentedButton(
            toolbar,
            values=["All Messages", "Q&A Only", "AI Only", "User Only"],
            font=("Segoe UI", 10),
            height=26,
            command=self._on_filter_changed
        )
        self.filter_segmented.set("All Messages")
        self.filter_segmented.pack(side="left", padx=6, pady=8)

        # Counter Badge
        self.counter_lbl = ctk.CTkLabel(
            toolbar,
            text=f"Selected: {len(self.all_messages)}/{len(self.all_messages)}",
            font=("Segoe UI", 11, "bold"),
            text_color=self.colors["accent_primary"]
        )
        self.counter_lbl.pack(side="right", padx=12, pady=8)

        # 3. Scrollable Message Cards List
        self.scroll_list = ctk.CTkScrollableFrame(
            self.selection_container,
            fg_color="transparent",
            corner_radius=8
        )
        self.scroll_list.pack(fill="both", expand=True, pady=(0, 10))

        self.card_widgets = []
        for i, msg in enumerate(self.all_messages):
            var = tk.BooleanVar(value=True)
            self.msg_vars.append(var)
            card = self._create_message_item(i, msg, var)
            self.card_widgets.append(card)

        # 4. Format Selector & Bottom Actions Bar
        bottom_bar = ctk.CTkFrame(self.selection_container, fg_color=self.colors["bg_sidebar"], corner_radius=8, border_width=1, border_color=self.colors["border_color"])
        bottom_bar.pack(fill="x", pady=(0, 0))

        fmt_frame = ctk.CTkFrame(bottom_bar, fg_color="transparent")
        fmt_frame.pack(side="left", padx=12, pady=10)

        fmt_label = ctk.CTkLabel(
            fmt_frame,
            text="Format:",
            font=("Segoe UI", 11, "bold"),
            text_color=self.colors["text_primary"]
        )
        fmt_label.pack(side="left", padx=(0, 6))

        self.format_menu = ctk.CTkOptionMenu(
            fmt_frame,
            values=[opt[0] for opt in self.FORMAT_OPTIONS],
            font=("Segoe UI", 11),
            width=180,
            height=30,
            fg_color=self.colors["chip_bg"],
            button_color=self.colors["accent_primary"],
            button_hover_color=self.colors["accent_hover"],
            text_color=self.colors["text_primary"],
            dropdown_font=("Segoe UI", 11)
        )
        self.format_menu.set(self.FORMAT_OPTIONS[0][0])
        self.format_menu.pack(side="left")

        # Action Buttons
        btn_action_box = ctk.CTkFrame(bottom_bar, fg_color="transparent")
        btn_action_box.pack(side="right", padx=12, pady=10)

        btn_cancel = ctk.CTkButton(
            btn_action_box,
            text="Cancel",
            font=("Segoe UI", 11),
            width=70,
            height=30,
            fg_color=self.colors["chip_bg"],
            hover_color=self.colors["chip_hover"],
            text_color=self.colors["text_primary"],
            command=self.destroy
        )
        btn_cancel.pack(side="left", padx=(0, 8))

        self.export_btn = ctk.CTkButton(
            btn_action_box,
            text=f"💾 Export ({len(self.all_messages)})",
            font=("Segoe UI", 11, "bold"),
            height=30,
            fg_color=self.colors["accent_primary"],
            hover_color=self.colors["accent_hover"],
            command=self._start_export_process
        )
        self.export_btn.pack(side="left")

    def _create_message_item(self, idx: int, msg: Dict[str, Any], var: tk.BooleanVar) -> ctk.CTkFrame:
        role = msg.get("role", "user")
        content = msg.get("content", "").strip()
        ts = msg.get("timestamp", "")
        citations = msg.get("citations", [])

        if role == "user":
            role_text = "👤 User Query"
            role_color = "#3b82f6"
            card_bg = self.colors["bg_card_user"]
        elif role == "ai":
            role_text = "⚡ Assistant Response"
            role_color = "#10b981"
            card_bg = self.colors["bg_card_ai"]
        else: # system
            role_text = "ℹ️ System Notice"
            role_color = "#64748b"
            card_bg = self.colors["chip_bg"]

        card = ctk.CTkFrame(
            self.scroll_list,
            fg_color=card_bg,
            corner_radius=8,
            border_width=1,
            border_color=self.colors["border_color"]
        )
        card.pack(fill="x", pady=4, padx=2)

        item_top = ctk.CTkFrame(card, fg_color="transparent")
        item_top.pack(fill="x", padx=10, pady=(6, 2))

        cb = ctk.CTkCheckBox(
            item_top,
            text="",
            variable=var,
            width=20,
            height=20,
            checkbox_width=18,
            checkbox_height=18,
            corner_radius=4,
            border_width=2,
            fg_color=self.colors["accent_primary"],
            hover_color=self.colors["accent_hover"],
            command=self._update_counter
        )
        cb.pack(side="left", padx=(0, 8))

        badge = ctk.CTkLabel(
            item_top,
            text=role_text,
            font=("Segoe UI", 11, "bold"),
            text_color=role_color
        )
        badge.pack(side="left")

        if ts:
            time_lbl = ctk.CTkLabel(
                item_top,
                text=ts,
                font=("Segoe UI", 10),
                text_color=self.colors["text_muted"]
            )
            time_lbl.pack(side="left", padx=(8, 0))

        if citations:
            cite_lbl = ctk.CTkLabel(
                item_top,
                text=f"📑 {len(citations)} source{'s' if len(citations) > 1 else ''}",
                font=("Segoe UI", 9, "bold"),
                text_color="#059669"
            )
            cite_lbl.pack(side="right")

        preview_text = content.replace("\n", " ")
        if len(preview_text) > 160:
            preview_text = preview_text[:160] + "..."

        msg_lbl = ctk.CTkLabel(
            card,
            text=preview_text if preview_text else "(No text content)",
            font=("Segoe UI", 11),
            text_color=self.colors["text_primary"],
            justify="left",
            wraplength=520,
            anchor="w"
        )
        msg_lbl.pack(fill="x", padx=38, pady=(0, 8), anchor="w")

        def _toggle(event=None):
            var.set(not var.get())
            self._update_counter()

        card.bind("<Button-1>", _toggle)
        msg_lbl.bind("<Button-1>", _toggle)
        badge.bind("<Button-1>", _toggle)
        item_top.bind("<Button-1>", _toggle)

        return card

    def _select_all(self):
        for var in self.msg_vars:
            var.set(True)
        self._update_counter()

    def _deselect_all(self):
        for var in self.msg_vars:
            var.set(False)
        self._update_counter()

    def _on_filter_changed(self, mode: str):
        self.filter_mode = mode
        for i, msg in enumerate(self.all_messages):
            role = msg.get("role", "user")
            if mode == "All Messages":
                self.msg_vars[i].set(True)
            elif mode == "Q&A Only":
                self.msg_vars[i].set(role in ["user", "ai"])
            elif mode == "AI Only":
                self.msg_vars[i].set(role == "ai")
            elif mode == "User Only":
                self.msg_vars[i].set(role == "user")
        self._update_counter()

    def _update_counter(self):
        selected_count = sum(1 for v in self.msg_vars if v.get())
        total_count = len(self.all_messages)
        self.counter_lbl.configure(text=f"Selected: {selected_count}/{total_count}")
        self.export_btn.configure(text=f"💾 Export ({selected_count})")
        if selected_count == 0:
            self.export_btn.configure(state="disabled", fg_color=self.colors["chip_bg"])
        else:
            self.export_btn.configure(state="normal", fg_color=self.colors["accent_primary"])

    def _start_export_process(self):
        selected_messages = [msg for i, msg in enumerate(self.all_messages) if self.msg_vars[i].get()]
        if not selected_messages:
            messagebox.showwarning("Export Chat", "Please select at least one message to export.")
            return

        selected_format_label = self.format_menu.get()
        ext = ".pdf"
        for label, extension in self.FORMAT_OPTIONS:
            if label == selected_format_label:
                ext = extension
                break

        file_path = filedialog.asksaveasfilename(
            parent=self,
            title="Save Exported Conversation",
            defaultextension=ext,
            filetypes=[
                ("PDF Document (*.pdf)", "*.pdf"),
                ("Word Document (*.docx)", "*.docx"),
                ("Markdown Document (*.md)", "*.md"),
                ("HTML Webpage (*.html)", "*.html"),
                ("Plain Text Document (*.txt)", "*.txt"),
                ("JSON Data (*.json)", "*.json"),
                ("All Files (*.*)", "*.*")
            ]
        )
        if not file_path:
            return

        self._show_saving_progress_ui(file_path, selected_messages)

    def _show_saving_progress_ui(self, file_path: str, selected_messages: List[Dict[str, Any]]):
        self.selection_container.pack_forget()
        self.progress_container.pack(fill="both", expand=True, padx=20, pady=20)

        for w in self.progress_container.winfo_children():
            w.destroy()

        card = ctk.CTkFrame(
            self.progress_container,
            fg_color=self.colors["bg_sidebar"],
            corner_radius=12,
            border_width=1,
            border_color=self.colors["border_color"]
        )
        card.pack(fill="both", expand=True, padx=6, pady=6)

        icon_lbl = ctk.CTkLabel(card, text="⚙️", font=("Segoe UI", 42))
        icon_lbl.pack(pady=(45, 10))

        title_lbl = ctk.CTkLabel(
            card,
            text="Exporting Conversation...",
            font=("Segoe UI", 16, "bold"),
            text_color=self.colors["text_primary"]
        )
        title_lbl.pack(pady=(0, 6))

        file_name = os.path.basename(file_path)
        status_lbl = ctk.CTkLabel(
            card,
            text=f"Processing and formatting {len(selected_messages)} selected messages into '{file_name}'...",
            font=("Segoe UI", 12),
            text_color=self.colors["text_muted"],
            wraplength=460,
            justify="center"
        )
        status_lbl.pack(pady=(0, 20))

        prog_bar = ctk.CTkProgressBar(
            card,
            width=360,
            height=10,
            corner_radius=5,
            progress_color=self.colors["accent_primary"],
            mode="indeterminate"
        )
        prog_bar.pack(pady=(0, 25))
        prog_bar.start()

        def worker():
            try:
                ext = file_path.lower().split(".")[-1]
                if ext == "pdf":
                    ExportChatModal._export_pdf(file_path, selected_messages)
                elif ext in ["docx", "doc"]:
                    ExportChatModal._export_docx(file_path, selected_messages)
                elif ext == "md":
                    ExportChatModal._export_markdown(file_path, selected_messages)
                elif ext in ["html", "htm"]:
                    ExportChatModal._export_html(file_path, selected_messages)
                elif ext == "json":
                    ExportChatModal._export_json(file_path, selected_messages)
                else:
                    ExportChatModal._export_txt(file_path, selected_messages)

                self.after(400, lambda: self._show_export_success(file_path, len(selected_messages)))
            except Exception as e:
                self.after(400, lambda err=str(e): self._show_export_error(err, file_path, selected_messages))

        threading.Thread(target=worker, daemon=True).start()

    def _show_export_success(self, file_path: str, count: int):
        for w in self.progress_container.winfo_children():
            w.destroy()

        card = ctk.CTkFrame(
            self.progress_container,
            fg_color=self.colors["bg_sidebar"],
            corner_radius=12,
            border_width=1,
            border_color=self.colors["border_color"]
        )
        card.pack(fill="both", expand=True, padx=6, pady=6)

        icon_lbl = ctk.CTkLabel(card, text="🎉", font=("Segoe UI", 46))
        icon_lbl.pack(pady=(35, 8))

        title_lbl = ctk.CTkLabel(
            card,
            text="Export Completed Successfully!",
            font=("Segoe UI", 16, "bold"),
            text_color=self.colors["text_primary"]
        )
        title_lbl.pack(pady=(0, 6))

        sub_lbl = ctk.CTkLabel(
            card,
            text=f"Successfully exported {count} selected messages to your file.",
            font=("Segoe UI", 12),
            text_color=self.colors["text_muted"]
        )
        sub_lbl.pack(pady=(0, 14))

        path_box = ctk.CTkFrame(card, fg_color=self.colors["bg_base"], corner_radius=6, border_width=1, border_color=self.colors["border_color"])
        path_box.pack(fill="x", padx=24, pady=(0, 24))

        path_lbl = ctk.CTkLabel(
            path_box,
            text=f"📄 {file_path}",
            font=("Segoe UI", 10),
            text_color=self.colors["text_primary"],
            wraplength=460,
            justify="left"
        )
        path_lbl.pack(padx=12, pady=8)

        actions_frame = ctk.CTkFrame(card, fg_color="transparent")
        actions_frame.pack(pady=(0, 20))

        def _open_file():
            try:
                os.startfile(file_path)
            except Exception:
                webbrowser.open(f"file:///{file_path}")

        def _open_folder():
            try:
                subprocess.Popen(f'explorer /select,"{os.path.normpath(file_path)}"')
            except Exception:
                pass

        btn_open = ctk.CTkButton(
            actions_frame,
            text="📂 Open File",
            font=("Segoe UI", 12, "bold"),
            width=120,
            height=34,
            fg_color=self.colors["accent_primary"],
            hover_color=self.colors["accent_hover"],
            command=_open_file
        )
        btn_open.pack(side="left", padx=6)

        btn_folder = ctk.CTkButton(
            actions_frame,
            text="📁 Open Folder",
            font=("Segoe UI", 12),
            width=120,
            height=34,
            fg_color=self.colors["chip_bg"],
            hover_color=self.colors["chip_hover"],
            text_color=self.colors["text_primary"],
            command=_open_folder
        )
        btn_folder.pack(side="left", padx=6)

        btn_done = ctk.CTkButton(
            actions_frame,
            text="✕ Close",
            font=("Segoe UI", 12),
            width=80,
            height=34,
            fg_color=self.colors["chip_bg"],
            hover_color=self.colors["chip_hover"],
            text_color=self.colors["text_primary"],
            command=self.destroy
        )
        btn_done.pack(side="left", padx=6)

    def _show_export_error(self, err_msg: str, file_path: str, selected_messages: List[Dict[str, Any]]):
        for w in self.progress_container.winfo_children():
            w.destroy()

        card = ctk.CTkFrame(
            self.progress_container,
            fg_color=self.colors["bg_sidebar"],
            corner_radius=12,
            border_width=1,
            border_color=self.colors["border_color"]
        )
        card.pack(fill="both", expand=True, padx=6, pady=6)

        icon_lbl = ctk.CTkLabel(card, text="⚠️", font=("Segoe UI", 48))
        icon_lbl.pack(pady=(30, 8))

        title_lbl = ctk.CTkLabel(
            card,
            text="Export Failed",
            font=("Segoe UI", 16, "bold"),
            text_color="#ef4444"
        )
        title_lbl.pack(pady=(0, 6))

        err_lbl = ctk.CTkLabel(
            card,
            text=f"An error occurred while generating the document:\n{err_msg}",
            font=("Segoe UI", 11),
            text_color=self.colors["text_muted"],
            wraplength=460,
            justify="center"
        )
        err_lbl.pack(pady=(0, 20))

        btn_box = ctk.CTkFrame(card, fg_color="transparent")
        btn_box.pack(pady=(0, 20))

        def _retry():
            self.progress_container.pack_forget()
            self.selection_container.pack(fill="both", expand=True, padx=16, pady=16)

        btn_retry = ctk.CTkButton(
            btn_box,
            text="🔄 Try Again",
            font=("Segoe UI", 12, "bold"),
            width=110,
            height=32,
            fg_color=self.colors["accent_primary"],
            hover_color=self.colors["accent_hover"],
            command=_retry
        )
        btn_retry.pack(side="left", padx=6)

        btn_close = ctk.CTkButton(
            btn_box,
            text="Close",
            font=("Segoe UI", 12),
            width=80,
            height=32,
            fg_color=self.colors["chip_bg"],
            hover_color=self.colors["chip_hover"],
            text_color=self.colors["text_primary"],
            command=self.destroy
        )
        btn_close.pack(side="left", padx=6)

    @staticmethod
    def _export_pdf(file_path: str, messages: List[Dict[str, Any]]):
        from reportlab.lib.pagesizes import letter
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Paragraph, HRFlowable

        doc = SimpleDocTemplate(
            file_path,
            pagesize=letter,
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36
        )

        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            'DocTitle',
            parent=styles['Heading1'],
            fontName='Helvetica-Bold',
            fontSize=18,
            leading=22,
            textColor=colors.HexColor('#4f46e5'),
            alignment=1,
            spaceAfter=4
        )

        meta_style = ParagraphStyle(
            'DocMeta',
            parent=styles['Normal'],
            fontName='Helvetica-Oblique',
            fontSize=9,
            leading=12,
            textColor=colors.HexColor('#64748b'),
            alignment=1,
            spaceAfter=12
        )

        user_header_style = ParagraphStyle(
            'UserHeader',
            parent=styles['Heading3'],
            fontName='Helvetica-Bold',
            fontSize=11,
            leading=14,
            textColor=colors.HexColor('#0f172a'),
            spaceBefore=6,
            spaceAfter=3
        )

        ai_header_style = ParagraphStyle(
            'AIHeader',
            parent=styles['Heading3'],
            fontName='Helvetica-Bold',
            fontSize=11,
            leading=14,
            textColor=colors.HexColor('#4f46e5'),
            spaceBefore=6,
            spaceAfter=3
        )

        body_style = ParagraphStyle(
            'MsgBody',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=10,
            leading=14,
            textColor=colors.HexColor('#1e293b'),
            spaceAfter=6
        )

        cite_style = ParagraphStyle(
            'MsgCite',
            parent=styles['Normal'],
            fontName='Helvetica-Oblique',
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor('#059669'),
            spaceAfter=4
        )

        story = []
        story.append(Paragraph("🧠 Search Studio — Chat Conversation Export", title_style))
        time_stamp = messages[0].get("timestamp", "") if messages else ""
        story.append(Paragraph(f"Exported Transcript • {len(messages)} messages • {time_stamp}", meta_style))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#cbd5e1'), spaceAfter=12))

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>")
            ts = msg.get("timestamp", "")
            citations = msg.get("citations", [])

            if role == "user":
                story.append(Paragraph(f"👤 User &nbsp;<font color='#64748b' size='8'>({ts})</font>", user_header_style))
                story.append(Paragraph(content, body_style))
            elif role == "ai":
                story.append(Paragraph(f"⚡ Search Studio Assistant &nbsp;<font color='#64748b' size='8'>({ts})</font>", ai_header_style))
                story.append(Paragraph(content, body_style))
                if citations:
                    cite_txt = "<b>📑 Sources:</b> " + ", ".join(citations)
                    story.append(Paragraph(cite_txt, cite_style))
            else: # system
                story.append(Paragraph(f"ℹ️ <font color='#64748b'>[{ts}] {content}</font>", cite_style))

            story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#e2e8f0'), spaceBefore=4, spaceAfter=8))

        doc.build(story)

    @staticmethod
    def _export_docx(file_path: str, messages: List[Dict[str, Any]]):
        import docx
        from docx.enum.text import WD_ALIGN_PARAGRAPH

        doc = docx.Document()
        title = doc.add_heading("🧠 Search Studio - Chat Conversation Export", level=0)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER

        time_stamp = messages[0].get("timestamp", "") if messages else ""
        p_meta = doc.add_paragraph(f"Exported Transcript • {len(messages)} messages • {time_stamp}")
        p_meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
        doc.add_paragraph("-" * 60)

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            ts = msg.get("timestamp", "")
            citations = msg.get("citations", [])

            if role == "user":
                doc.add_heading(f"👤 User ({ts})", level=2)
                doc.add_paragraph(content)
            elif role == "ai":
                doc.add_heading(f"⚡ AI Assistant ({ts})", level=2)
                doc.add_paragraph(content)
                if citations:
                    p_cite = doc.add_paragraph()
                    p_cite.add_run("📑 Sources: ").bold = True
                    p_cite.add_run(", ".join(citations))
            else: # system
                p = doc.add_paragraph(f"ℹ️ [{ts}] {content}")
                p.italic = True

            doc.add_paragraph()

        doc.save(file_path)

    @staticmethod
    def _export_markdown(file_path: str, messages: List[Dict[str, Any]]):
        lines = [
            "# 🧠 Search Studio - Chat Conversation Export",
            f"*Exported on: {messages[0].get('timestamp', '')}*\n",
            "---\n"
        ]
        for msg in messages:
            role_title = "👤 **User**" if msg["role"] == "user" else "⚡ **AI Assistant**"
            lines.append(f"### {role_title} ({msg.get('timestamp', '')})")
            lines.append(f"{msg['content']}\n")
            if msg.get("citations"):
                lines.append(f"> **📑 Sources:** {', '.join(msg['citations'])}\n")
            lines.append("---\n")

        content = "\n".join(lines)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

    @staticmethod
    def _export_html(file_path: str, messages: List[Dict[str, Any]]):
        html_items = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>")
            ts = msg.get("timestamp", "")
            citations = msg.get("citations", [])

            is_user = (role == "user")
            avatar = "👤 You" if is_user else "⚡ AI Assistant"
            bg_card = "#f8fafc" if is_user else "#f0fdf4"
            accent_color = "#3b82f6" if is_user else "#10b981"

            cite_html = ""
            if citations:
                cite_html = f'<div style="margin-top:8px; font-size:12px; color:#059669;"><b>📑 Sources:</b> {", ".join(citations)}</div>'

            card_html = f"""
            <div style="background:{bg_card}; border:1px solid #e2e8f0; border-left:4px solid {accent_color}; border-radius:8px; padding:14px; margin-bottom:14px;">
                <div style="display:flex; justify-content:space-between; margin-bottom:6px;">
                    <span style="font-weight:bold; color:{accent_color};">{avatar}</span>
                    <span style="font-size:11px; color:#94a3b8;">{ts}</span>
                </div>
                <div style="font-size:14px; line-height:1.6; color:#1e293b;">{content}</div>
                {cite_html}
            </div>
            """
            html_items.append(card_html)

        full_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Search Studio - Chat Transcript</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background:#f1f5f9; margin:0; padding:24px; }}
        .container {{ max-width:800px; margin:0 auto; background:#ffffff; border-radius:12px; box-shadow:0 4px 6px -1px rgba(0,0,0,0.1); padding:28px; }}
        h1 {{ font-size:22px; color:#0f172a; margin-top:0; }}
        .meta {{ font-size:12px; color:#64748b; margin-bottom:20px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🧠 Search Studio — Chat Conversation</h1>
        <div class="meta">Exported on: {messages[0].get('timestamp', '') if messages else ''}</div>
        <hr style="border:0; border-top:1px solid #e2e8f0; margin-bottom:20px;">
        {''.join(html_items)}
    </div>
</body>
</html>"""
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(full_html)

    @staticmethod
    def _export_json(file_path: str, messages: List[Dict[str, Any]]):
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(messages, f, indent=2)

    @staticmethod
    def _export_txt(file_path: str, messages: List[Dict[str, Any]]):
        lines = ["--- SEARCH STUDIO CHAT TRANSCRIPT ---\n"]
        for msg in messages:
            role = "USER" if msg["role"] == "user" else "AI ASSISTANT"
            lines.append(f"[{msg.get('timestamp', '')}] {role}:\n{msg['content']}\n")
            if msg.get("citations"):
                lines.append(f"Sources: {', '.join(msg['citations'])}\n")
            lines.append("-" * 40 + "\n")
        content = "\n".join(lines)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
