"""
MultipleCandidatesModal: Interactive selection dialog when page sniffer extracts multiple download links.
"""
import os
import sys
try:
    import tkinter as tk
    from tkinter import ttk
except Exception:
    tk = None  # type: ignore
    ttk = None  # type: ignore
from typing import Optional, Callable, Dict, Any, List
try:
    from PIL import Image, ImageTk
except ImportError:
    Image = None
    ImageTk = None

from ...config import get_resource_path
from ...locales.i18n import tr
from ...utils.file_ops import get_file_category_and_icon
from ...utils.url_utils import derive_download_filename
from ...services.youtube_service import format_filesize
from ...utils.tk_helpers import _detach_photo_tk

_BaseToplevel = tk.Toplevel if tk is not None else object

class MultipleCandidatesModal(_BaseToplevel):
    """
    Sleek, modern, dark-themed Tkinter modal dialog displayed when multiple
    download candidate links are detected on a landing page or download page.

    Features:
    - Displays source page title / URL.
    - Scrollable list of candidate files with individual checkboxes, file name,
      file type / extension badge, and destination link preview.
    - Master "Select All / تحديد الكل" checkbox.
    - Action buttons:
      * "تحميل المحدد / Download Selected"
      * "تحميل الكل / Download All"
      * "إلغاء / Cancel"
    - High-DPI scaled, grab-free (avoids grab_set() traps).
    - Fully non-blocking, safe dispatch to Tkinter main thread.
    - Complete Arabic and English localization support.
    """
    def __init__(
        self,
        parent: Optional[tk.Tk],
        source_url: str,
        candidates: List[Dict[str, Any]],
        page_title: str = "",
        theme: Optional[Dict[str, str]] = None,
        on_download_selected: Optional[Callable[[List[Dict[str, Any]]], None]] = None,
        on_download_all: Optional[Callable[[List[Dict[str, Any]]], None]] = None,
        on_cancel: Optional[Callable[[], None]] = None,
        parent_app: Optional[Any] = None
    ):
        super().__init__(parent)
        self.source_url = str(source_url or "").strip()
        self.candidates = list(candidates or [])
        self.page_title = str(page_title or "").strip()
        self.on_download_selected = on_download_selected
        self.on_download_all = on_download_all
        self.on_cancel = on_cancel
        self.parent_app = parent_app

        th = theme or {}
        self.c_bg = th.get("c_bg", "#0f172a")
        self.c_panel = th.get("c_panel", "#1e293b")
        self.c_panel_light = th.get("c_panel_light", "#334155")
        self.c_border = th.get("c_border", "#475569")
        self.c_text_bright = th.get("c_text_bright", "#f8fafc")
        self.c_text_muted = th.get("c_text_muted", "#94a3b8")
        self.c_accent = th.get("c_accent", "#38bdf8")
        self.c_accent_dark = th.get("c_accent_dark", "#0284c7")
        self.c_danger = th.get("c_danger", "#ef4444")
        self.c_success = th.get("c_success", "#10b981")
        self.c_input_bg = th.get("c_input_bg", "#0b1220")

        self.title(tr("multi_modal_title"))
        self.configure(bg=self.c_bg)

        # High-DPI scaling
        try:
            dpi = float(parent.winfo_fpixels('1i')) if parent and parent.winfo_exists() else 96.0
        except Exception:
            dpi = 96.0
        self.dpi_scale = max(1.0, dpi / 96.0)

        # Center on parent window or screen
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        dlg_w = min(int(740 * self.dpi_scale), max(560, int(sw * 0.90)))
        dlg_h = min(int(520 * self.dpi_scale), max(400, int(sh * 0.82)))

        is_parent_visible = False
        try:
            if parent and parent.winfo_exists() and parent.winfo_viewable() and parent.state() == "normal":
                is_parent_visible = True
        except Exception:
            is_parent_visible = False

        if is_parent_visible:
            try:
                self.transient(parent)
            except Exception:
                pass
            try:
                px = parent.winfo_x()
                py = parent.winfo_y()
                pw = parent.winfo_width() or dlg_w
                ph = parent.winfo_height() or dlg_h
                x = max(0, px + (pw - dlg_w) // 2)
                y = max(0, py + (ph - dlg_h) // 2)
                self.geometry(f"{dlg_w}x{dlg_h}+{x}+{y}")
            except Exception:
                self.geometry(f"{dlg_w}x{dlg_h}")
        else:
            try:
                self.transient("")
                self.deiconify()
            except Exception:
                pass
            x = max(0, (sw - dlg_w) // 2)
            y = max(0, (sh - dlg_h) // 2)
            self.geometry(f"{dlg_w}x{dlg_h}+{x}+{y}")

        self.protocol("WM_DELETE_WINDOW", self._on_cancel_clicked)
        self.bind("<Escape>", lambda e: self._on_cancel_clicked())

        self.candidate_vars: List[tk.BooleanVar] = []
        self._build_ui()

    def _build_ui(self):
        # Outer border
        outer = tk.Frame(self, bg=self.c_border, padx=1, pady=1)
        outer.pack(fill=tk.BOTH, expand=True)

        body = tk.Frame(outer, bg=self.c_bg, padx=16, pady=14)
        body.pack(fill=tk.BOTH, expand=True)

        # Header Frame
        hdr_frame = tk.Frame(body, bg=self.c_bg)
        hdr_frame.pack(fill=tk.X, pady=(0, 8))

        lbl_icon = tk.Label(hdr_frame, text="📦", font=("Segoe UI", 16), bg=self.c_bg, fg=self.c_accent)
        lbl_icon.pack(side=tk.LEFT, padx=(0, 8))

        title_box = tk.Frame(hdr_frame, bg=self.c_bg)
        title_box.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.lbl_title = tk.Label(
            title_box,
            text=tr("multi_modal_title"),
            font=("Segoe UI", 11, "bold"),
            bg=self.c_bg,
            fg=self.c_accent,
            anchor="w"
        )
        self.lbl_title.pack(anchor="w")

        src_text = self.page_title or self.source_url
        if len(src_text) > 85:
            src_text = src_text[:82] + "..."
        self.lbl_source = tk.Label(
            title_box,
            text=f"{tr('multi_modal_source')} {src_text}",
            font=("Segoe UI", 8),
            bg=self.c_bg,
            fg=self.c_text_muted,
            anchor="w"
        )
        self.lbl_source.pack(anchor="w", pady=(1, 0))

        # Subtitle instructions
        self.lbl_subtitle = tk.Label(
            body,
            text=tr("multi_modal_subtitle"),
            font=("Segoe UI", 9),
            bg=self.c_bg,
            fg=self.c_text_bright,
            anchor="w",
            wraplength=int(680 * self.dpi_scale),
            justify="left"
        )
        self.lbl_subtitle.pack(fill=tk.X, pady=(0, 8))

        # Master Selection Bar
        master_bar = tk.Frame(body, bg=self.c_panel, padx=10, pady=6, highlightbackground=self.c_border, highlightthickness=1)
        master_bar.pack(fill=tk.X, pady=(0, 8))

        self.var_select_all = tk.BooleanVar(master=self, value=True)
        self.chk_select_all = tk.Checkbutton(
            master_bar,
            text=tr("multi_select_all"),
            variable=self.var_select_all,
            command=self._toggle_select_all,
            font=("Segoe UI", 9, "bold"),
            bg=self.c_panel,
            fg=self.c_text_bright,
            selectcolor=self.c_input_bg,
            activebackground=self.c_panel,
            activeforeground="white",
            cursor="hand2"
        )
        self.chk_select_all.pack(side=tk.LEFT)

        total_cnt = len(self.candidates)
        self.lbl_counter = tk.Label(
            master_bar,
            text=tr("multi_selection_count", selected=total_cnt, total=total_cnt),
            font=("Segoe UI", 8),
            bg=self.c_panel,
            fg=self.c_accent
        )
        self.lbl_counter.pack(side=tk.RIGHT)

        # Candidates List Canvas with Scrollbar
        list_container = tk.Frame(body, bg=self.c_input_bg, highlightbackground=self.c_border, highlightthickness=1)
        list_container.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        self.canvas = tk.Canvas(list_container, bg=self.c_input_bg, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(list_container, orient="vertical", command=self.canvas.yview)
        self.scroll_frame = tk.Frame(self.canvas, bg=self.c_input_bg)

        self.scroll_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        self.canvas_window = self.canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        # Populate rows
        self._populate_candidates_list()

        # Bottom Button Row
        btn_bar = tk.Frame(body, bg=self.c_bg)
        btn_bar.pack(fill=tk.X)

        self.btn_download_selected = tk.Button(
            btn_bar,
            text=tr("multi_btn_download_selected"),
            command=self._on_download_selected_clicked,
            font=("Segoe UI", 9, "bold"),
            bg=self.c_accent_dark,
            fg="white",
            relief="flat",
            activebackground=self.c_accent,
            activeforeground="white",
            cursor="hand2",
            padx=14,
            pady=6
        )
        self.btn_download_selected.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_download_all = tk.Button(
            btn_bar,
            text=tr("multi_btn_download_all"),
            command=self._on_download_all_clicked,
            font=("Segoe UI", 9, "bold"),
            bg=self.c_panel_light,
            fg=self.c_accent,
            relief="flat",
            activebackground=self.c_border,
            activeforeground="white",
            cursor="hand2",
            padx=14,
            pady=6
        )
        self.btn_download_all.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_cancel = tk.Button(
            btn_bar,
            text=tr("multi_btn_cancel"),
            command=self._on_cancel_clicked,
            font=("Segoe UI", 9),
            bg=self.c_panel_light,
            fg=self.c_text_muted,
            relief="flat",
            activebackground=self.c_border,
            activeforeground="white",
            cursor="hand2",
            padx=14,
            pady=6
        )
        self.btn_cancel.pack(side=tk.RIGHT)

    def _populate_candidates_list(self):
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()
        self.candidate_vars.clear()

        for idx, cand in enumerate(self.candidates):
            var = tk.BooleanVar(master=self, value=True)
            self.candidate_vars.append(var)

            fn = cand.get("filename") or derive_download_filename(cand.get("url", ""))
            ext = cand.get("ext", "")
            title = cand.get("title", "")
            url = cand.get("url", "")
            size_b = cand.get("size_bytes")
            size_str = ""
            if size_b is not None and isinstance(size_b, (int, float)) and size_b > 0:
                if size_b >= 1024 * 1024 * 1024:
                    size_str = f"({size_b / (1024*1024*1024):.1f} GB)"
                elif size_b >= 1024 * 1024:
                    size_str = f"({size_b / (1024*1024):.1f} MB)"
                elif size_b >= 1024:
                    size_str = f"({size_b / 1024:.1f} KB)"
                else:
                    size_str = f"({size_b} B)"

            cat, icon = get_file_category_and_icon(fn)

            row = tk.Frame(
                self.scroll_frame,
                bg=self.c_panel,
                padx=8,
                pady=6,
                highlightbackground=self.c_border,
                highlightthickness=1
            )
            row.pack(fill=tk.X, expand=True, pady=3, padx=2)

            chk = tk.Checkbutton(
                row,
                variable=var,
                command=self._on_item_toggled,
                bg=self.c_panel,
                selectcolor=self.c_input_bg,
                activebackground=self.c_panel,
                cursor="hand2"
            )
            chk.pack(side=tk.LEFT, padx=(0, 6))

            badge = tk.Label(row, text=icon, font=("Segoe UI", 12), bg=self.c_panel)
            badge.pack(side=tk.LEFT, padx=(0, 6))

            info_col = tk.Frame(row, bg=self.c_panel)
            info_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

            line1 = tk.Frame(info_col, bg=self.c_panel)
            line1.pack(fill=tk.X, anchor="w")

            lbl_fn = tk.Label(line1, text=fn, font=("Segoe UI", 9, "bold"), bg=self.c_panel, fg=self.c_text_bright)
            lbl_fn.pack(side=tk.LEFT, padx=(0, 6))

            if ext:
                lbl_ext = tk.Label(
                    line1,
                    text=ext.upper().lstrip("."),
                    font=("Segoe UI", 7, "bold"),
                    bg=self.c_panel_light,
                    fg=self.c_accent,
                    padx=4,
                    pady=1
                )
                lbl_ext.pack(side=tk.LEFT, padx=(0, 6))

            if size_str:
                lbl_sz = tk.Label(line1, text=size_str, font=("Segoe UI", 8), bg=self.c_panel, fg=self.c_text_muted)
                lbl_sz.pack(side=tk.LEFT)

            line2 = tk.Frame(info_col, bg=self.c_panel)
            line2.pack(fill=tk.X, anchor="w", pady=(2, 0))

            if title and title != fn:
                disp_title = title if len(title) <= 45 else title[:42] + "..."
                lbl_t = tk.Label(line2, text=disp_title, font=("Segoe UI", 8), bg=self.c_panel, fg=self.c_accent)
                lbl_t.pack(side=tk.LEFT, padx=(0, 6))

            disp_url = url if len(url) <= 70 else url[:67] + "..."
            lbl_u = tk.Label(line2, text=disp_url, font=("Segoe UI", 7), bg=self.c_panel, fg=self.c_text_muted)
            lbl_u.pack(side=tk.LEFT)

    def _on_canvas_configure(self, event):
        self.canvas.itemconfig(self.canvas_window, width=event.width)

    def _on_mousewheel(self, event):
        try:
            if self.canvas.winfo_exists():
                self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        except Exception:
            pass

    def _toggle_select_all(self):
        state = self.var_select_all.get()
        for var in self.candidate_vars:
            var.set(state)
        self._update_counter()

    def _on_item_toggled(self):
        selected_count = sum(1 for v in self.candidate_vars if v.get())
        total_count = len(self.candidate_vars)
        if selected_count == total_count:
            self.var_select_all.set(True)
        else:
            self.var_select_all.set(False)
        self._update_counter()

    def _update_counter(self):
        sel = sum(1 for v in self.candidate_vars if v.get())
        tot = len(self.candidate_vars)
        self.lbl_counter.configure(
            text=tr("multi_selection_count", selected=sel, total=tot)
        )

    def select_all(self, state: bool = True):
        self.var_select_all.set(state)
        for var in self.candidate_vars:
            var.set(state)
        self._update_counter()

    def select_candidate(self, index: int, state: bool = True):
        if 0 <= index < len(self.candidate_vars):
            self.candidate_vars[index].set(state)
            self._on_item_toggled()

    def get_selected_candidates(self) -> List[Dict[str, Any]]:
        return [cand for cand, var in zip(self.candidates, self.candidate_vars) if var.get()]

    def _on_download_selected_clicked(self):
        selected = self.get_selected_candidates()
        if not selected:
            if hasattr(self, "parent_app") and self.parent_app and hasattr(self.parent_app, "show_safe_warning"):
                self.parent_app.show_safe_warning(tr("multi_modal_title"), tr("multi_no_selection_warning"))
            return
        if self.on_download_selected:
            self.on_download_selected(selected)
        self.destroy()

    def _on_download_all_clicked(self):
        if self.on_download_all:
            self.on_download_all(self.candidates)
        elif self.on_download_selected:
            self.on_download_selected(self.candidates)
        self.destroy()

    def _on_cancel_clicked(self):
        try:
            self.unbind_all("<MouseWheel>")
        except Exception:
            pass
        if self.on_cancel:
            try:
                self.on_cancel()
            except Exception:
                pass
        self.destroy()

    def destroy(self):
        try:
            self.unbind_all("<MouseWheel>")
        except Exception:
            pass
        if self.parent_app and getattr(self.parent_app, "_candidates_modal", None) is self:
            self.parent_app._candidates_modal = None
        if self.parent_app and hasattr(self.parent_app, "clear_last_clipboard_url"):
            try:
                self.parent_app.clear_last_clipboard_url()
            except Exception:
                pass
        super().destroy()

    def grab_set(self):
        pass

    def grab_set_global(self):
        pass

