"""
DownloadConfirmationModal: Download metadata inspection, category routing, and pre-start confirmation modal.
"""
import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Optional, Callable, Dict, Any
try:
    from PIL import Image, ImageTk
except ImportError:
    Image = None
    ImageTk = None

from ...config import get_resource_path, get_setting, set_setting
from ...locales.i18n import tr
from ..components.base_modal import SafeModalDialog
from ..components.tooltip import ToolTip
from ...utils.url_utils import derive_download_filename, is_potential_html_url, parse_speed_limit
from ...utils.file_ops import (
    get_file_category_and_icon,
    resolve_categorized_path,
    open_containing_folder,
    open_downloaded_file,
)
from ...core.html_resolver import resolve_real_download_url
from ...core.engine import TurboDownloadEngine
from ...core.history import DownloadHistoryManager
from ...utils.tk_helpers import _detach_photo_tk

from .confirm_modal_logic import ConfirmModalLogicMixin


class DownloadConfirmationModal(ConfirmModalLogicMixin, tk.Toplevel):
    """
    Modern dark-themed TDM-style Download Confirmation & Standalone Progress Dialog:
    - Displays intercepted URL, extracted filename, file category badge & icon, and target save path.
    - Connection count selector and Speed limiter controls.
    - Three action buttons: Start Download, Open in Main App, Cancel.
    - Standalone compact download progress view with Pause/Resume/Cancel/Open.
    - Grab-free: strictly avoids grab_set() to eliminate Win32 message pump traps.
    """
    def __init__(
        self, parent: Optional[tk.Tk], url: str, default_dest_path: str,
        theme: Optional[Dict[str, str]] = None, on_confirm: Optional[Callable] = None,
        on_cancel: Optional[Callable[[], None]] = None, on_start_in_window: Optional[Callable] = None,
        on_open_in_main: Optional[Callable] = None, parent_app: Optional[Any] = None,
        default_connections: int = 8, default_speed_limit: float = 0.0,
        show_progress_immediately: bool = False, history_manager: Optional[Any] = None
    ):
        super().__init__(parent)
        self.url = str(url or "").strip()
        self.dest_path = str(default_dest_path or "").strip()
        self.on_confirm = on_confirm
        self.on_cancel = on_cancel
        self.on_start_in_window = on_start_in_window
        self.on_open_in_main = on_open_in_main
        self.parent_app = parent_app
        self.history_manager = history_manager or (getattr(parent_app, "history_manager", None) if parent_app else None)
        self.default_connections = default_connections
        self.default_speed_limit = default_speed_limit
        self._confirmed = False
        self.is_in_progress_view = False
        self.is_completed = False
        self.engine: Optional[Any] = None

        self.file_name = os.path.basename(self.dest_path) if self.dest_path else derive_download_filename(self.url)
        self.category, self.icon = get_file_category_and_icon(self.file_name or self.url)

        th = theme or {}
        _c_defaults = {
            "c_bg": "#0f172a", "c_panel": "#1e293b", "c_panel_light": "#334155",
            "c_border": "#475569", "c_text_bright": "#f8fafc", "c_text_muted": "#94a3b8",
            "c_accent": "#38bdf8", "c_accent_dark": "#0284c7", "c_danger": "#ef4444",
            "c_success": "#10b981", "c_warning": "#f59e0b", "c_input_bg": "#0b1220"
        }
        for k, v in _c_defaults.items():
            setattr(self, k, th.get(k, v))

        self.title(tr("modal_confirm_title", "Download File Info — Smart Download"))
        self.configure(bg=self.c_bg)
        self._last_pct = 0.0

        # Do not use grab_set(): Overrideredirect parent causes Win32 message pump traps and UI freezes

        # Determine parent DPI scale
        try:
            dpi = float(parent.winfo_fpixels('1i')) if parent and parent.winfo_exists() else 96.0
        except Exception:
            dpi = 96.0
        self.dpi_scale = max(1.0, dpi / 96.0)

        # Center on parent window with DPI scaling (or center on screen if parent is hidden/minimized)
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        dlg_w = min(int(630 * self.dpi_scale), max(500, int(sw * 0.90)))
        dlg_h = min(int(410 * self.dpi_scale), max(340, int(sh * 0.80)))

        is_parent_vis = False
        try:
            is_parent_vis = bool(parent and parent.winfo_exists() and parent.winfo_viewable() and parent.state() == "normal")
        except Exception:
            pass

        if is_parent_vis:
            try:
                self.transient(parent)
                px, py = parent.winfo_x(), parent.winfo_y()
                pw, ph = parent.winfo_width() or dlg_w, parent.winfo_height() or dlg_h
                x, y = max(0, px + (pw - dlg_w) // 2), max(0, py + (ph - dlg_h) // 2)
            except Exception:
                x, y = max(0, (sw - dlg_w) // 2), max(0, (sh - dlg_h) // 2)
        else:
            try:
                self.transient("")
                self.deiconify()
            except Exception:
                pass
            x, y = max(0, (sw - dlg_w) // 2), max(0, (sh - dlg_h) // 2)

        self.geometry(f"{dlg_w}x{dlg_h}+{x}+{y}")
        self.minsize(min(480, dlg_w), min(270, dlg_h))

        # Apply application icon to modal window
        ico_path = get_resource_path("app_icon.ico")
        png_path = get_resource_path("app_icon.png")
        if os.path.isfile(ico_path):
            try:
                self.iconbitmap(ico_path)
            except Exception:
                pass
        if os.path.isfile(png_path):
            try:
                from PIL import ImageTk
                self._modal_icon_photo = ImageTk.PhotoImage(file=png_path)
                self.iconphoto(True, self._modal_icon_photo)
            except Exception:
                pass

        # Elevate and focus to ensure modal stays above parent window
        try:
            self.lift()
            self.attributes("-topmost", True)
            self.focus_force()
            self.after(250, lambda: self.attributes("-topmost", False) if self.winfo_exists() else None)
            self._idle_job = self.after_idle(lambda: (self.lift(), self.focus_force()) if self.winfo_exists() else None)
        except Exception:
            pass

        self._build_ui()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Escape>", lambda e: self._on_close())
        self.bind("<Return>", lambda e: self._on_start())

        if show_progress_immediately:
            self.show_progress_view()

    def _build_ui(self):
        # Outer border
        outer = tk.Frame(self, bg=self.c_border, padx=1, pady=1)
        outer.pack(fill=tk.BOTH, expand=True)

        self.body = tk.Frame(outer, bg=self.c_bg, padx=18, pady=16)
        self.body.pack(fill=tk.BOTH, expand=True)

        # -------------------------------------------------------------
        # View 1: Download Confirmation View (Initial View)
        # -------------------------------------------------------------
        self.frame_confirmation = tk.Frame(self.body, bg=self.c_bg)
        self.frame_confirmation.pack(fill=tk.BOTH, expand=True)

        # Header Title row
        hdr_frame = tk.Frame(self.frame_confirmation, bg=self.c_bg)
        hdr_frame.pack(fill=tk.X, pady=(0, 10))

        lbl_icon = tk.Label(hdr_frame, text="📥", font=("Segoe UI", 16), bg=self.c_bg, fg=self.c_accent)
        lbl_icon.pack(side=tk.LEFT, padx=(0, 8))

        lbl_title = tk.Label( hdr_frame, text=tr("modal_confirm_title_header", "DOWNLOAD FILE INFO"),
            font=("Segoe UI", 11, "bold"),
            bg=self.c_bg,
            fg=self.c_accent,
            anchor="w"
        )
        lbl_title.pack(side=tk.LEFT)

        lbl_sub = tk.Label( hdr_frame, text=tr("modal_confirm_sub", "SD Smart Interception"),
            font=("Segoe UI", 8),
            bg=self.c_bg,
            fg=self.c_text_muted,
            anchor="e"
        )
        lbl_sub.pack(side=tk.RIGHT)

        # Details Card
        card = tk.Frame(self.frame_confirmation, bg=self.c_panel, padx=14, pady=10, highlightbackground=self.c_border, highlightthickness=1)
        card.pack(fill=tk.BOTH, expand=True, pady=(0, 12))

        # 1. URL Row
        url_frame = tk.Frame(card, bg=self.c_panel)
        url_frame.pack(fill=tk.X, pady=(0, 6))

        lbl_url = tk.Label(url_frame, text=tr("lbl_url", "URL:"), font=("Segoe UI", 9, "bold"), bg=self.c_panel, fg=self.c_text_muted, width=9, anchor="w")
        lbl_url.pack(side=tk.LEFT)

        self.entry_url = tk.Entry( url_frame, font=("Segoe UI", 9),
            bg=self.c_input_bg,
            fg=self.c_text_bright,
            insertbackground=self.c_accent,
            relief="flat",
            highlightbackground=self.c_border,
            highlightthickness=1
        )
        self.entry_url.insert(0, self.url)
        self.entry_url.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=3)

        # 2. File details row: Category and Filename
        info_row = tk.Frame(card, bg=self.c_panel)
        info_row.pack(fill=tk.X, pady=(0, 6))

        cat_box = tk.Frame(info_row, bg=self.c_panel_light, padx=8, pady=3, highlightbackground=self.c_border, highlightthickness=1)
        cat_box.pack(side=tk.LEFT, padx=(0, 12))

        self.lbl_category_val = tk.Label( cat_box, text=f"{self.icon}  {self.category}", font=("Segoe UI", 9, "bold"),
            bg=self.c_panel_light,
            fg=self.c_accent
        )
        self.lbl_category_val.pack()

        fn_frame = tk.Frame(info_row, bg=self.c_panel)
        fn_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)

        lbl_fn_title = tk.Label(fn_frame, text=tr("modal_file_name", "File Name:"), font=("Segoe UI", 8), bg=self.c_panel, fg=self.c_text_muted, anchor="w")
        lbl_fn_title.pack(anchor="w")

        self.lbl_filename_val = tk.Label( fn_frame, text=self.file_name, font=("Segoe UI", 9, "bold"),
            bg=self.c_panel,
            fg=self.c_text_bright,
            anchor="w"
        )
        self.lbl_filename_val.pack(anchor="w")

        # 3. Save Destination Row
        dest_frame = tk.Frame(card, bg=self.c_panel)
        dest_frame.pack(fill=tk.X, pady=(0, 6))

        lbl_dest = tk.Label(dest_frame, text=tr("modal_save_to", "Save To:"), font=("Segoe UI", 9, "bold"), bg=self.c_panel, fg=self.c_text_muted, width=9, anchor="w")
        lbl_dest.pack(side=tk.LEFT)

        self.entry_dest = tk.Entry( dest_frame, font=("Segoe UI", 9),
            bg=self.c_input_bg,
            fg=self.c_text_bright,
            insertbackground=self.c_accent,
            relief="flat",
            highlightbackground=self.c_border,
            highlightthickness=1
        )
        self.entry_dest.insert(0, self.dest_path)
        self.entry_dest.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8), ipady=3)
        self.entry_dest.bind("<KeyRelease>", self._on_dest_key_release)

        self.btn_browse = tk.Button( dest_frame, text=tr("modal_btn_browse", "📁 Browse..."),
            font=("Segoe UI", 9),
            bg=self.c_panel_light,
            fg=self.c_text_bright,
            relief="flat",
            activebackground=self.c_accent_dark,
            cursor="hand2",
            padx=12,
            pady=3,
            command=self._on_browse
        )
        self.btn_browse.pack(side=tk.RIGHT)

        # 4. Settings Row: Connections & Speed Limiter
        cfg_row = tk.Frame(card, bg=self.c_panel)
        cfg_row.pack(fill=tk.X, pady=(4, 0))

        # Connections subframe
        conn_frame = tk.Frame(cfg_row, bg=self.c_panel)
        conn_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)

        lbl_conn = tk.Label( conn_frame, text=tr("modal_threads", "Connections / Threads:"),
            font=("Segoe UI", 8, "bold"),
            bg=self.c_panel,
            fg=self.c_text_muted
        )
        lbl_conn.pack(anchor="w", pady=(0, 2))

        self.combo_threads = ttk.Combobox( conn_frame, values=["1", "2", "4", "8", "16", "32"], state="readonly", width=10, font=("Segoe UI", 9)
        )
        def_conn_str = str(self.default_connections) if str(self.default_connections) in ["1", "2", "4", "8", "16", "32"] else "8"
        self.combo_threads.set(def_conn_str)
        self.combo_threads.pack(anchor="w")

        # Speed limiter subframe
        spd_frame = tk.Frame(cfg_row, bg=self.c_panel)
        spd_frame.pack(side=tk.RIGHT, fill=tk.X, expand=True)

        lbl_spd = tk.Label( spd_frame, text=tr("modal_speed_limiter", "Speed Limiter:"),
            font=("Segoe UI", 8, "bold"),
            bg=self.c_panel,
            fg=self.c_text_muted
        )
        lbl_spd.pack(anchor="w", pady=(0, 2))

        self.combo_speed = ttk.Combobox( spd_frame, values=["Unlimited", "256 KB/s", "512 KB/s", "1 MB/s", "2 MB/s", "5 MB/s", "10 MB/s", "20 MB/s"], width=16, font=("Segoe UI", 9)
        )
        if self.default_speed_limit > 0:
            spd_str = f"{self.default_speed_limit / (1024*1024):.0f} MB/s" if self.default_speed_limit >= 1024*1024 else f"{self.default_speed_limit / 1024:.0f} KB/s"
            self.combo_speed.set(spd_str)
        else:
            self.combo_speed.set("Unlimited")
        self.combo_speed.pack(anchor="w")

        # Confirmation Bottom Buttons Row
        btn_row = tk.Frame(self.frame_confirmation, bg=self.c_bg)
        btn_row.pack(fill=tk.X)

        lbl_hint = tk.Label( btn_row, text=tr("modal_confirm_hint", "⏎ Press Enter to start, Esc to cancel"),
            font=("Segoe UI", 8),
            bg=self.c_bg,
            fg=self.c_text_muted
        )
        lbl_hint.pack(side=tk.LEFT)

        self.btn_cancel = tk.Button( btn_row, text=tr("modal_btn_cancel", "✕ Cancel"),
            font=("Segoe UI", 9, "bold"),
            bg=self.c_panel_light,
            fg=self.c_text_muted,
            relief="flat",
            activebackground=self.c_border,
            cursor="hand2",
            padx=14,
            pady=6,
            command=self._on_close
        )
        self.btn_cancel.pack(side=tk.RIGHT, padx=(8, 0))

        self.btn_open_app = tk.Button( btn_row, text=tr("modal_btn_open_in_main", "📋 Open in Main App"),
            font=("Segoe UI", 9),
            bg=self.c_panel_light,
            fg=self.c_text_bright,
            relief="flat",
            activebackground=self.c_border,
            cursor="hand2",
            padx=14,
            pady=6,
            command=self._on_open_in_main
        )
        self.btn_open_app.pack(side=tk.RIGHT, padx=(8, 0))

        self.btn_start = tk.Button( btn_row, text=tr("modal_btn_start", "▶ Start Download"),
            font=("Segoe UI", 9, "bold"),
            bg=self.c_success,
            fg="white",
            relief="flat",
            activebackground="#059669",
            cursor="hand2",
            padx=16,
            pady=6,
            command=self._on_start_in_window
        )
        self.btn_start.pack(side=tk.RIGHT)

        # -------------------------------------------------------------
        # View 2: Compact Download Progress View (Transitions on start)
        # -------------------------------------------------------------
        self.frame_progress = tk.Frame(self.body, bg=self.c_bg)
        # Initially not packed

        # Header Title row
        prog_hdr = tk.Frame(self.frame_progress, bg=self.c_bg)
        prog_hdr.pack(fill=tk.X, pady=(0, 8))

        self.lbl_prog_icon = tk.Label(prog_hdr, text=self.icon, font=("Segoe UI", 16), bg=self.c_bg, fg=self.c_accent)
        self.lbl_prog_icon.pack(side=tk.LEFT, padx=(0, 8))

        self.lbl_prog_filename = tk.Label( prog_hdr, text=self.file_name, font=("Segoe UI", 10, "bold"),
            bg=self.c_bg,
            fg=self.c_text_bright,
            anchor="w"
        )
        self.lbl_prog_filename.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.lbl_prog_cat = tk.Label( prog_hdr, text=f"{self.icon}  {self.category}", font=("Segoe UI", 8, "bold"),
            bg=self.c_panel_light,
            fg=self.c_accent,
            padx=6,
            pady=2
        )
        self.lbl_prog_cat.pack(side=tk.RIGHT)

        # Progress Card
        prog_card = tk.Frame(self.frame_progress, bg=self.c_panel, padx=14, pady=10, highlightbackground=self.c_border, highlightthickness=1)
        prog_card.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # Status row
        self.lbl_status = tk.Label( prog_card, text=tr("modal_status_connecting", "Status: Connecting..."),
            font=("Segoe UI", 9, "bold"),
            bg=self.c_panel,
            fg=self.c_accent,
            anchor="w"
        )
        self.lbl_status.pack(fill=tk.X, pady=(0, 4))

        # Metrics row 1
        m_row1 = tk.Frame(prog_card, bg=self.c_panel)
        m_row1.pack(fill=tk.X, pady=(0, 2))

        self.lbl_prog_size = tk.Label( m_row1, text="Transferred: 0 B / 0 B (0.0%)",
            font=("Segoe UI", 9),
            bg=self.c_panel,
            fg=self.c_text_bright,
            anchor="w"
        )
        self.lbl_prog_size.pack(side=tk.LEFT)

        self.lbl_prog_speed = tk.Label( m_row1, text="Speed: 0.0 KB/s", font=("Segoe UI", 9, "bold"),
            bg=self.c_panel,
            fg=self.c_success,
            anchor="e"
        )
        self.lbl_prog_speed.pack(side=tk.RIGHT)

        # Metrics row 2
        m_row2 = tk.Frame(prog_card, bg=self.c_panel)
        m_row2.pack(fill=tk.X, pady=(0, 6))

        self.lbl_prog_eta = tk.Label( m_row2, text="Time Left: --:--:--", font=("Segoe UI", 8),
            bg=self.c_panel,
            fg=self.c_text_muted,
            anchor="w"
        )
        self.lbl_prog_eta.pack(side=tk.LEFT)

        self.lbl_prog_threads = tk.Label( m_row2, text=f"Threads: {self.get_max_connections()} Active",
            font=("Segoe UI", 8),
            bg=self.c_panel,
            fg=self.c_text_muted,
            anchor="e"
        )
        self.lbl_prog_threads.pack(side=tk.RIGHT)

        # Live Canvas Progress Bar
        self.canvas_prog = tk.Canvas( prog_card, bg=self.c_input_bg, highlightthickness=0, height=int(24 * self.dpi_scale)
        )
        self.canvas_prog.pack(fill=tk.X, pady=(2, 0))
        self.canvas_prog.bind("<Configure>", lambda e: self._draw_modal_progress(getattr(self, "_last_pct", 0.0)))

        # Progress Buttons Row
        self.prog_btn_row = tk.Frame(self.frame_progress, bg=self.c_bg)
        self.prog_btn_row.pack(fill=tk.X)

        self.btn_open_app_prog = tk.Button( self.prog_btn_row, text=tr("modal_btn_open_in_main", "📋 Open in Main App"),
            font=("Segoe UI", 9),
            bg=self.c_panel_light,
            fg=self.c_text_bright,
            relief="flat",
            activebackground=self.c_border,
            cursor="hand2",
            padx=12,
            pady=5,
            command=self._on_open_in_main
        )
        self.btn_open_app_prog.pack(side=tk.LEFT)

        # Active download buttons
        self.btn_cancel_prog = tk.Button( self.prog_btn_row, text=tr("modal_btn_cancel", "✕ Cancel"),
            font=("Segoe UI", 9, "bold"),
            bg=self.c_panel_light,
            fg=self.c_text_muted,
            relief="flat",
            activebackground=self.c_border,
            cursor="hand2",
            padx=14,
            pady=5,
            command=self._on_close
        )
        self.btn_cancel_prog.pack(side=tk.RIGHT, padx=(6, 0))

        self.btn_pause_resume = tk.Button( self.prog_btn_row, text=tr("btn_pause", "⏸ Pause"),
            font=("Segoe UI", 9, "bold"),
            bg=self.c_panel_light,
            fg=self.c_text_bright,
            relief="flat",
            activebackground=self.c_accent_dark,
            cursor="hand2",
            padx=14,
            pady=5,
            command=self._on_pause_resume
        )
        self.btn_pause_resume.pack(side=tk.RIGHT)

        # Completion buttons (packed when download finishes)
        self.btn_close_prog = tk.Button( self.prog_btn_row, text=tr("browser_btn_close", "Close"),
            font=("Segoe UI", 9, "bold"),
            bg=self.c_panel_light,
            fg=self.c_text_bright,
            relief="flat",
            activebackground=self.c_border,
            cursor="hand2",
            padx=14,
            pady=5,
            command=self.destroy
        )

        self.btn_open_folder = tk.Button( self.prog_btn_row, text=tr("btn_hist_folder", "📁 Open Folder"),
            font=("Segoe UI", 9),
            bg=self.c_panel_light,
            fg=self.c_text_bright,
            relief="flat",
            activebackground=self.c_accent_dark,
            cursor="hand2",
            padx=12,
            pady=5,
            command=self._on_open_folder
        )

        self.btn_open_file = tk.Button(
            self.prog_btn_row,
            text=tr("btn_hist_open", "📂 Open File"),
            font=("Segoe UI", 9, "bold"),
            bg=self.c_success,
            fg="white",
            relief="flat",
            activebackground="#059669",
            cursor="hand2",
            padx=14,
            pady=5,
            command=self._on_open_file,
        )


DownloadConfirmationDialog = DownloadConfirmationModal
DownloadConfirmModal = DownloadConfirmationModal
__all__ = ["DownloadConfirmationModal", "DownloadConfirmationDialog", "DownloadConfirmModal", "ConfirmModalLogicMixin"]
