"""
ChunksPanelMixin: Dynamic chunk visualization, tabbed consoles, and chunk-tree context actions.
"""
import os
import sys
import subprocess
from typing import List, Any

try:
    import tkinter as tk
    from tkinter import ttk
except Exception:
    tk = None  # type: ignore
    ttk = None  # type: ignore

from smart_download.i18n import tr
from .metrics_panel import MetricsPanelMixin


class ChunksPanelMixin(MetricsPanelMixin):
    """
    Mixin providing chunk segment visualization, tab container (chunks, activity log, history),
    and chunk tree context actions. Inherits MetricsPanelMixin.
    """

    def _build_chunk_visualizer_card(self, parent):
        """Visual TDM-style horizontal segmented chunk block visualizer."""
        card = tk.Frame(parent, bg=self.c_panel, padx=14, pady=8, relief="flat", highlightbackground=self.c_border, highlightthickness=1)
        card.pack(fill=tk.X, pady=(0, 10))

        header_row = tk.Frame(card, bg=self.c_panel)
        header_row.pack(fill=tk.X, pady=(0, 4))

        lbl = tk.Label(header_row, text="SD DYNAMIC CHUNK VISUALIZER (Segmented Byte Map)", font=("Segoe UI", 8, "bold"), bg=self.c_panel, fg=self.c_accent)
        lbl.pack(side=tk.LEFT)

        lbl_legend = tk.Label(header_row, text="■ Active (Cyan)   ■ Done (Green)   ■ Remaining (Dark)", font=("Segoe UI", 8), bg=self.c_panel, fg=self.c_text_muted)
        lbl_legend.pack(side=tk.RIGHT)

        chunk_height = max(30, int(32 * getattr(self, "dpi_scale", 1.0)))
        self.canvas_chunks = tk.Canvas(card, height=chunk_height, bg=self.c_input_bg, highlightthickness=0)
        self.chunk_canvas = self.canvas_chunks
        self.canvas_chunks.pack(fill=tk.X)
        self._draw_chunk_segments([])

    def _draw_chunk_segments(self, chunks: List[Any]):
        canvas = getattr(self, "chunk_canvas", None) or getattr(self, "canvas_chunks", None)
        if not canvas:
            return
        w = canvas.winfo_width()
        if w <= 1:
            w = getattr(self, "width", 800) - 64
        h = canvas.winfo_height() or max(30, int(32 * getattr(self, "dpi_scale", 1.0)))

        # Cache lightweight visual signature to eliminate redundant 4x/sec canvas redraws
        chunk_sig = []
        for c in chunks:
            with c.lock:
                span = max(1, c.end_byte - c.start_byte + 1)
                ratio_int = int((c.downloaded_bytes / span) * 1000)
                chunk_sig.append((c.chunk_id, c.start_byte, c.end_byte, ratio_int, c.status))
        current_sig = (w, h, tuple(chunk_sig), getattr(self.engine, "total_size", 0) if self.engine else 0)

        if getattr(self, "_last_chunk_canvas_sig", None) == current_sig:
            return
        self._last_chunk_canvas_sig = current_sig

        canvas.delete("all")

        c_input_bg = getattr(self, "c_input_bg", "#090d16")
        c_border = getattr(self, "c_border", "#475569")
        c_text_muted = getattr(self, "c_text_muted", "#94a3b8")
        c_success = getattr(self, "c_success", "#10b981")
        c_accent = getattr(self, "c_accent", "#38bdf8")

        # Background track
        canvas.create_rectangle(0, 0, w, h, fill=c_input_bg, outline=c_border)

        if not chunks or not self.engine or self.engine.total_size <= 0:
            msg = "Waiting to start..." if not self.engine else "Single-stream / unknown size"
            canvas.create_text(w // 2, h // 2, text=msg, font=("Segoe UI", 8), fill=c_text_muted)
            return

        total_size = self.engine.total_size

        for c in chunks:
            with c.lock:
                start_x = (c.start_byte / total_size) * w
                end_x = ((c.end_byte + 1) / total_size) * w
                done_x = min(end_x, ((c.start_byte + c.downloaded_bytes) / total_size) * w)
                status = c.status

            chunk_w = max(1.0, end_x - start_x)

            # Segment un-downloaded portion
            canvas.create_rectangle(start_x, 2, end_x, h - 2, fill="#1e293b", outline="")

            # Segment downloaded portion
            if done_x > start_x:
                fill_color = c_success if status == "completed" else c_accent
                canvas.create_rectangle(start_x, 2, done_x, h - 2, fill=fill_color, outline="")

            # Chunk divider line
            canvas.create_line(end_x, 0, end_x, h, fill=c_border, width=1)

            # Chunk label if wide enough
            if chunk_w > 36:
                mid_x = (start_x + end_x) / 2
                canvas.create_text(mid_x, h // 2, text=f"#{c.chunk_id}", font=("Segoe UI", 8, "bold"), fill="white")

    def _build_tabs_card(self, parent):
        """Dual Tab View: Detailed Chunk Table and Activity Console."""
        notebook = ttk.Notebook(parent, style="Custom.TNotebook")
        notebook.pack(fill=tk.BOTH, expand=True)

        # Tab 1: Chunk Details Table
        tab_chunks = tk.Frame(notebook, bg=self.c_panel)
        notebook.add(tab_chunks, text=tr("tab_chunks", "  📊 Chunk Segments  "))

        cols = ("id", "range", "size", "downloaded", "pct", "status")
        self.tree_chunks = ttk.Treeview(tab_chunks, columns=cols, show="headings", style="Custom.Treeview")
        self.tree_chunks.heading("id", text=tr("col_chunk_id", "ID"))
        self.tree_chunks.heading("range", text=tr("col_chunk_range", "Byte Offset Range"))
        self.tree_chunks.heading("size", text=tr("col_chunk_size", "Total Span"))
        self.tree_chunks.heading("downloaded", text=tr("col_chunk_downloaded", "Downloaded"))
        self.tree_chunks.heading("pct", text=tr("col_chunk_pct", "Progress"))
        self.tree_chunks.heading("status", text=tr("col_chunk_status", "Status"))

        scale = getattr(self, "dpi_scale", 1.0)
        self.tree_chunks.column("id", width=max(50, int(60 * scale)), minwidth=40, anchor="center")
        self.tree_chunks.column("range", width=max(200, int(250 * scale)), minwidth=180, anchor="w")
        self.tree_chunks.column("size", width=max(90, int(110 * scale)), minwidth=80, anchor="e")
        self.tree_chunks.column("downloaded", width=max(90, int(110 * scale)), minwidth=80, anchor="e")
        self.tree_chunks.column("pct", width=max(80, int(90 * scale)), minwidth=70, anchor="center")
        self.tree_chunks.column("status", width=max(100, int(120 * scale)), minwidth=90, anchor="center")

        scroll_tree = ttk.Scrollbar(tab_chunks, orient="vertical", command=self.tree_chunks.yview)
        self.tree_chunks.configure(yscrollcommand=scroll_tree.set)
        self.tree_chunks.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_tree.pack(side=tk.RIGHT, fill=tk.Y)

        self._build_tree_context_menu()
        self.tree_chunks.bind("<Button-3>", self._show_tree_context_menu)
        self.tree_chunks.bind("<Button-2>", self._show_tree_context_menu)

        # Tab 2: Activity Console Log
        tab_logs = tk.Frame(notebook, bg=self.c_panel)
        notebook.add(tab_logs, text=tr("tab_logs", "  📜 Activity Log  "))

        self.txt_log = tk.Text(
            tab_logs,
            bg=self.c_input_bg,
            fg=self.c_text_bright,
            insertbackground=self.c_accent,
            font=("Consolas", 9),
            relief="flat",
            wrap="word",
            padx=8,
            pady=8
        )
        scroll_log = ttk.Scrollbar(tab_logs, orient="vertical", command=self.txt_log.yview)
        self.txt_log.configure(yscrollcommand=scroll_log.set)
        self.txt_log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_log.pack(side=tk.RIGHT, fill=tk.Y)

        self.notebook = notebook

        # Tab 3: Download History Manager
        tab_history = tk.Frame(notebook, bg=self.c_panel)
        notebook.add(tab_history, text=tr("tab_history", "  📂 Download History  "))

        # Top Toolbar
        hist_toolbar = tk.Frame(tab_history, bg=self.c_panel, padx=8, pady=6)
        hist_toolbar.pack(side=tk.TOP, fill=tk.X)

        self.lbl_filter = tk.Label(hist_toolbar, text=tr("lbl_filter"), font=("Segoe UI", 9, "bold"), bg=self.c_panel, fg=self.c_text_bright)
        self.lbl_filter.pack(side=tk.LEFT, padx=(0, 6))

        categories = [
            tr("cat_all", "All Categories"),
            tr("cat_video", "Video"),
            tr("cat_audio", "Audio"),
            tr("cat_programs", "Programs"),
            tr("cat_compressed", "Compressed"),
            tr("cat_documents", "Documents"),
            tr("cat_images", "Images"),
            tr("cat_general", "General"),
        ]
        self.combo_history_filter = ttk.Combobox(
            hist_toolbar,
            values=categories,
            state="readonly",
            width=15
        )
        self.combo_history_filter.set(categories[0])
        self.combo_history_filter.pack(side=tk.LEFT, padx=(0, 10))
        self.combo_history_filter.bind("<<ComboboxSelected>>", lambda e: self._refresh_history_table())

        btn_font = ("Segoe UI", 8)
        self.btn_hist_open = tk.Button(
            hist_toolbar,
            text=tr("btn_hist_open", "📂 Open File"),
            command=self._history_open_selected_file,
            font=btn_font,
            bg=self.c_panel_light,
            fg=self.c_text_bright,
            relief="flat",
            activebackground=self.c_accent_dark,
            activeforeground="white",
            cursor="hand2",
            padx=8,
            pady=2
        )
        self.btn_hist_open.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_hist_folder = tk.Button(
            hist_toolbar,
            text=tr("btn_hist_folder", "📁 Open Folder"),
            command=self._history_open_selected_folder,
            font=btn_font,
            bg=self.c_panel_light,
            fg=self.c_text_bright,
            relief="flat",
            activebackground=self.c_accent_dark,
            activeforeground="white",
            cursor="hand2",
            padx=8,
            pady=2
        )
        self.btn_hist_folder.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_hist_redownload = tk.Button(
            hist_toolbar,
            text=tr("btn_hist_redownload", "🔄 Resume / Retry"),
            command=self._history_redownload_selected,
            font=("Segoe UI", 8, "bold"),
            bg=self.c_panel_light,
            fg=self.c_accent,
            relief="flat",
            activebackground=self.c_accent_dark,
            activeforeground="white",
            cursor="hand2",
            padx=8,
            pady=2
        )
        self.btn_hist_redownload.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_hist_remove = tk.Button(
            hist_toolbar,
            text=tr("btn_hist_remove", "🗑️ Remove"),
            command=self._history_remove_selected,
            font=btn_font,
            bg=self.c_panel_light,
            fg=self.c_text_muted,
            relief="flat",
            activebackground=self.c_accent_dark,
            activeforeground="white",
            cursor="hand2",
            padx=8,
            pady=2
        )
        self.btn_hist_remove.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_hist_clear = tk.Button(
            hist_toolbar,
            text=tr("btn_hist_clear", "🧹 Clear All"),
            command=self._history_clear_all,
            font=btn_font,
            bg=self.c_panel_light,
            fg="#ef4444",
            relief="flat",
            activebackground=self.c_accent_dark,
            activeforeground="white",
            cursor="hand2",
            padx=8,
            pady=2
        )
        self.btn_hist_clear.pack(side=tk.LEFT, padx=(0, 6))

        # History Treeview Frame
        tree_hist_frame = tk.Frame(tab_history, bg=self.c_panel)
        tree_hist_frame.pack(fill=tk.BOTH, expand=True)

        cols_hist = ("category", "filename", "size", "status", "date", "path")
        self.tree_history = ttk.Treeview(tree_hist_frame, columns=cols_hist, show="headings", style="Custom.Treeview")
        self.tree_history.heading("category", text=tr("col_hist_category", "Category"))
        self.tree_history.heading("filename", text=tr("col_hist_filename", "File Name"))
        self.tree_history.heading("size", text=tr("col_hist_size", "Size"))
        self.tree_history.heading("status", text=tr("col_hist_status", "Status"))
        self.tree_history.heading("date", text=tr("col_hist_date", "Date Added"))
        self.tree_history.heading("path", text=tr("col_hist_path", "Saved Location"))

        self.tree_history.column("category", width=max(80, int(95 * scale)), minwidth=70, anchor="center")
        self.tree_history.column("filename", width=max(180, int(220 * scale)), minwidth=140, anchor="w")
        self.tree_history.column("size", width=max(80, int(90 * scale)), minwidth=70, anchor="e")
        self.tree_history.column("status", width=max(80, int(90 * scale)), minwidth=70, anchor="center")
        self.tree_history.column("date", width=max(120, int(135 * scale)), minwidth=100, anchor="center")
        self.tree_history.column("path", width=max(220, int(260 * scale)), minwidth=180, anchor="w")

        scroll_hist = ttk.Scrollbar(tree_hist_frame, orient="vertical", command=self.tree_history.yview)
        self.tree_history.configure(yscrollcommand=scroll_hist.set)
        self.tree_history.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_hist.pack(side=tk.RIGHT, fill=tk.Y)

        self._build_history_context_menu()
        self.tree_history.bind("<Button-3>", self._show_history_context_menu)
        self.tree_history.bind("<Button-2>", self._show_history_context_menu)
        self.tree_history.bind("<Double-Button-1>", lambda e: self._history_open_selected_file())

        self._refresh_history_table()

    def _refresh_chunk_displays(self):
        if not self.engine:
            return

        if hasattr(self.engine, "get_chunks_snapshot"):
            chunks_copy = self.engine.get_chunks_snapshot()
        else:
            chunks_copy = list(getattr(self.engine, "chunks", []))

        # 1. Update Visual Segment Map
        self._draw_chunk_segments(chunks_copy)

        # 2. Update Table Rows with fast set lookup
        existing_items = set(self.tree_chunks.get_children())
        current_ids = set()
        for idx, c in enumerate(chunks_copy):
            with c.lock:
                item_id = f"c_{c.chunk_id}"
                current_ids.add(item_id)
                span = max(1, c.end_byte - c.start_byte + 1)
                pct_val = min(100.0, (c.downloaded_bytes / span) * 100.0)
                span_str = f"{span:,} B"
                done_str = f"{c.downloaded_bytes:,} B"
                pct_str = f"{pct_val:.1f}%"
                if c.status == "failed" and any(k in str(c.error_msg).lower() for k in ("expired", "401", "403", "410", "forbidden")):
                    status_str = "Expired ⚠️"
                else:
                    status_str = c.status.capitalize()
                range_str = f"{c.start_byte:,} — {c.end_byte:,}"

            vals = (f"#{c.chunk_id}", range_str, span_str, done_str, pct_str, status_str)

            if item_id in existing_items:
                self.tree_chunks.item(item_id, values=vals)
            else:
                self.tree_chunks.insert("", tk.END, iid=item_id, values=vals)

        # Prune any stale chunk rows (e.g. from previous stream phases)
        for stale_id in (existing_items - current_ids):
            self.tree_chunks.delete(stale_id)

    def _build_tree_context_menu(self):
        """Constructs right-click context menu for download task & chunk view."""
        self.tree_context_menu = tk.Menu(
            self.tree_chunks,
            tearoff=0,
            bg=self.c_panel,
            fg=self.c_text_bright,
            activebackground=self.c_accent_dark,
            activeforeground="white",
            relief="flat",
            bd=1
        )
        self.tree_context_menu.add_command(
            label=tr("ctx_refresh_address", "🔄 Refresh Download Address..."),
            command=self._open_refresh_link_dialog
        )
        self.tree_context_menu.add_separator()
        self.tree_context_menu.add_command(
            label=tr("ctx_resume_download", "▶ Resume Download"),
            command=self._menu_resume
        )
        self.tree_context_menu.add_command(
            label=tr("ctx_pause_download", "⏸ Pause Download"),
            command=self._menu_pause
        )
        self.tree_context_menu.add_command(
            label=tr("ctx_cancel_download", "⏹ Cancel Download"),
            command=self._on_cancel_download
        )
        self.tree_context_menu.add_separator()
        self.tree_context_menu.add_command(
            label=tr("ctx_copy_download_url", "📋 Copy Download URL"),
            command=self._copy_current_url
        )
        self.tree_context_menu.add_command(
            label=tr("ctx_open_folder", "📁 Open Containing Folder"),
            command=self._open_download_folder
        )

    def _show_tree_context_menu(self, event):
        """Displays right-click context menu on treeview."""
        self._build_tree_context_menu()
        try:
            iid = self.tree_chunks.identify_row(event.y)
            if iid:
                self.tree_chunks.selection_set(iid)
                self.tree_chunks.focus(iid)
        except Exception:
            pass
        try:
            self.tree_context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                self.tree_context_menu.grab_release()
            except Exception:
                pass

    def _menu_resume(self):
        if self.engine and self.engine.is_paused:
            self._on_pause_resume()
        elif self.engine and not self.engine.is_running:
            self.engine.resume_transfer()
            self.btn_start.configure(state="disabled")
            self.btn_pause.configure(state="normal", text=tr("btn_pause", "⏸ Pause"), bg=self.c_panel_light)
            self.btn_cancel.configure(state="normal")
            if hasattr(self, "btn_refresh_link"):
                self.btn_refresh_link.configure(state="normal")

    def _menu_pause(self):
        if self.engine and self.engine.is_running and not self.engine.is_paused:
            self._on_pause_resume()

    def _copy_current_url(self):
        url = (self.engine.url if self.engine else self.entry_url.get()).strip()
        if url:
            try:
                self.root.clipboard_clear()
                self.root.clipboard_append(url)
                if hasattr(self, "log") and callable(self.log):
                    self.log(f"Copied download URL to clipboard: {url}")
            except Exception:
                pass

    def _open_download_folder(self):
        dest = self.entry_dest.get().strip() if hasattr(self, "entry_dest") else ""
        folder = os.path.dirname(dest) if dest else os.path.expanduser("~")
        if os.path.isdir(folder):
            try:
                if sys.platform.startswith("win"):
                    os.startfile(folder)
                elif sys.platform.startswith("darwin"):
                    subprocess.Popen(["open", folder])
                else:
                    subprocess.Popen(["xdg-open", folder])
            except Exception as e:
                if hasattr(self, "log") and callable(self.log):
                    self.log(f"Failed to open folder: {e}")


__all__ = ["ChunksPanelMixin", "MetricsPanelMixin"]
