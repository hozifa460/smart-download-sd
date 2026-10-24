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

class DownloadConfirmationModal(tk.Toplevel):
    """
    Modern dark-themed TDM-style Download Confirmation & Standalone Progress Dialog:
    - Displays intercepted URL, extracted filename, file category badge & icon, and target save path.
    - Connection count selector (1, 2, 4, 8, 16, 32 threads).
    - Speed limiter control (presets: Unlimited, 256 KB/s, 512 KB/s, 1 MB/s, 2 MB/s, 5 MB/s, 10 MB/s, 20 MB/s or custom).
    - Three clear action buttons:
        1. [▶ Start Download] ("بدء التحميل هنا"): Keeps main window hidden and transitions into standalone compact progress view.
        2. [📋 Open in Main App] ("فتح في التطبيق"): Restores main window and manages download in main UI.
        3. [✕ Cancel] ("إلغاء"): Closes dialog cleanly without starting a download.
    - Standalone compact download progress view:
        * Live Canvas progress bar with percentage overlay.
        * Transferred / total size, current speed (MB/s or KB/s), and ETA (time remaining).
        * Pause / Resume and Cancel buttons.
        * Completion view with [📂 Open File], [📁 Open Folder], and [Close] buttons.
    - Grab-free: strictly avoids grab_set() / grab_set_global() to eliminate Win32 message pump deadlocks.
    - High-DPI scaled, dark-themed, centered on screen (or parent), and focused.
    """
    def __init__(
        self,
        parent: Optional[tk.Tk],
        url: str,
        default_dest_path: str,
        theme: Optional[Dict[str, str]] = None,
        on_confirm: Optional[Callable] = None,
        on_cancel: Optional[Callable[[], None]] = None,
        on_start_in_window: Optional[Callable] = None,
        on_open_in_main: Optional[Callable] = None,
        parent_app: Optional[Any] = None,
        default_connections: int = 8,
        default_speed_limit: float = 0.0,
        show_progress_immediately: bool = False,
        history_manager: Optional[Any] = None
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
        self.c_warning = th.get("c_warning", "#f59e0b")
        self.c_input_bg = th.get("c_input_bg", "#0b1220")

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
            except Exception:
                x = max(0, (sw - dlg_w) // 2)
                y = max(0, (sh - dlg_h) // 2)
        else:
            try:
                self.transient("")
                self.deiconify()
            except Exception:
                pass
            x = max(0, (sw - dlg_w) // 2)
            y = max(0, (sh - dlg_h) // 2)

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

        lbl_title = tk.Label(
            hdr_frame,
            text=tr("modal_confirm_title_header", "DOWNLOAD FILE INFO"),
            font=("Segoe UI", 11, "bold"),
            bg=self.c_bg,
            fg=self.c_accent,
            anchor="w"
        )
        lbl_title.pack(side=tk.LEFT)

        lbl_sub = tk.Label(
            hdr_frame,
            text=tr("modal_confirm_sub", "SD Smart Interception"),
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

        self.entry_url = tk.Entry(
            url_frame,
            font=("Segoe UI", 9),
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

        self.lbl_category_val = tk.Label(
            cat_box,
            text=f"{self.icon}  {self.category}",
            font=("Segoe UI", 9, "bold"),
            bg=self.c_panel_light,
            fg=self.c_accent
        )
        self.lbl_category_val.pack()

        fn_frame = tk.Frame(info_row, bg=self.c_panel)
        fn_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)

        lbl_fn_title = tk.Label(fn_frame, text=tr("modal_file_name", "File Name:"), font=("Segoe UI", 8), bg=self.c_panel, fg=self.c_text_muted, anchor="w")
        lbl_fn_title.pack(anchor="w")

        self.lbl_filename_val = tk.Label(
            fn_frame,
            text=self.file_name,
            font=("Segoe UI", 9, "bold"),
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

        self.entry_dest = tk.Entry(
            dest_frame,
            font=("Segoe UI", 9),
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

        self.btn_browse = tk.Button(
            dest_frame,
            text=tr("modal_btn_browse", "📁 Browse..."),
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

        lbl_conn = tk.Label(
            conn_frame,
            text=tr("modal_threads", "Connections / Threads:"),
            font=("Segoe UI", 8, "bold"),
            bg=self.c_panel,
            fg=self.c_text_muted
        )
        lbl_conn.pack(anchor="w", pady=(0, 2))

        self.combo_threads = ttk.Combobox(
            conn_frame,
            values=["1", "2", "4", "8", "16", "32"],
            state="readonly",
            width=10,
            font=("Segoe UI", 9)
        )
        def_conn_str = str(self.default_connections) if str(self.default_connections) in ["1", "2", "4", "8", "16", "32"] else "8"
        self.combo_threads.set(def_conn_str)
        self.combo_threads.pack(anchor="w")

        # Speed limiter subframe
        spd_frame = tk.Frame(cfg_row, bg=self.c_panel)
        spd_frame.pack(side=tk.RIGHT, fill=tk.X, expand=True)

        lbl_spd = tk.Label(
            spd_frame,
            text=tr("modal_speed_limiter", "Speed Limiter:"),
            font=("Segoe UI", 8, "bold"),
            bg=self.c_panel,
            fg=self.c_text_muted
        )
        lbl_spd.pack(anchor="w", pady=(0, 2))

        self.combo_speed = ttk.Combobox(
            spd_frame,
            values=["Unlimited", "256 KB/s", "512 KB/s", "1 MB/s", "2 MB/s", "5 MB/s", "10 MB/s", "20 MB/s"],
            width=16,
            font=("Segoe UI", 9)
        )
        if self.default_speed_limit > 0:
            if self.default_speed_limit >= 1024 * 1024:
                spd_str = f"{self.default_speed_limit / (1024*1024):.0f} MB/s"
            else:
                spd_str = f"{self.default_speed_limit / 1024:.0f} KB/s"
            self.combo_speed.set(spd_str)
        else:
            self.combo_speed.set("Unlimited")
        self.combo_speed.pack(anchor="w")

        # Confirmation Bottom Buttons Row
        btn_row = tk.Frame(self.frame_confirmation, bg=self.c_bg)
        btn_row.pack(fill=tk.X)

        lbl_hint = tk.Label(
            btn_row,
            text=tr("modal_confirm_hint", "⏎ Press Enter to start, Esc to cancel"),
            font=("Segoe UI", 8),
            bg=self.c_bg,
            fg=self.c_text_muted
        )
        lbl_hint.pack(side=tk.LEFT)

        self.btn_cancel = tk.Button(
            btn_row,
            text=tr("modal_btn_cancel", "✕ Cancel"),
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

        self.btn_open_app = tk.Button(
            btn_row,
            text=tr("modal_btn_open_in_main", "📋 Open in Main App"),
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

        self.btn_start = tk.Button(
            btn_row,
            text=tr("modal_btn_start", "▶ Start Download"),
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

        self.lbl_prog_filename = tk.Label(
            prog_hdr,
            text=self.file_name,
            font=("Segoe UI", 10, "bold"),
            bg=self.c_bg,
            fg=self.c_text_bright,
            anchor="w"
        )
        self.lbl_prog_filename.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.lbl_prog_cat = tk.Label(
            prog_hdr,
            text=f"{self.icon}  {self.category}",
            font=("Segoe UI", 8, "bold"),
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
        self.lbl_status = tk.Label(
            prog_card,
            text=tr("modal_status_connecting", "Status: Connecting..."),
            font=("Segoe UI", 9, "bold"),
            bg=self.c_panel,
            fg=self.c_accent,
            anchor="w"
        )
        self.lbl_status.pack(fill=tk.X, pady=(0, 4))

        # Metrics row 1
        m_row1 = tk.Frame(prog_card, bg=self.c_panel)
        m_row1.pack(fill=tk.X, pady=(0, 2))

        self.lbl_prog_size = tk.Label(
            m_row1,
            text="Transferred: 0 B / 0 B (0.0%)",
            font=("Segoe UI", 9),
            bg=self.c_panel,
            fg=self.c_text_bright,
            anchor="w"
        )
        self.lbl_prog_size.pack(side=tk.LEFT)

        self.lbl_prog_speed = tk.Label(
            m_row1,
            text="Speed: 0.0 KB/s",
            font=("Segoe UI", 9, "bold"),
            bg=self.c_panel,
            fg=self.c_success,
            anchor="e"
        )
        self.lbl_prog_speed.pack(side=tk.RIGHT)

        # Metrics row 2
        m_row2 = tk.Frame(prog_card, bg=self.c_panel)
        m_row2.pack(fill=tk.X, pady=(0, 6))

        self.lbl_prog_eta = tk.Label(
            m_row2,
            text="Time Left: --:--:--",
            font=("Segoe UI", 8),
            bg=self.c_panel,
            fg=self.c_text_muted,
            anchor="w"
        )
        self.lbl_prog_eta.pack(side=tk.LEFT)

        self.lbl_prog_threads = tk.Label(
            m_row2,
            text=f"Threads: {self.get_max_connections()} Active",
            font=("Segoe UI", 8),
            bg=self.c_panel,
            fg=self.c_text_muted,
            anchor="e"
        )
        self.lbl_prog_threads.pack(side=tk.RIGHT)

        # Live Canvas Progress Bar
        self.canvas_prog = tk.Canvas(
            prog_card,
            bg=self.c_input_bg,
            highlightthickness=0,
            height=int(24 * self.dpi_scale)
        )
        self.canvas_prog.pack(fill=tk.X, pady=(2, 0))
        self.canvas_prog.bind("<Configure>", lambda e: self._draw_modal_progress(getattr(self, "_last_pct", 0.0)))

        # Progress Buttons Row
        self.prog_btn_row = tk.Frame(self.frame_progress, bg=self.c_bg)
        self.prog_btn_row.pack(fill=tk.X)

        self.btn_open_app_prog = tk.Button(
            self.prog_btn_row,
            text=tr("modal_btn_open_in_main", "📋 Open in Main App"),
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
        self.btn_cancel_prog = tk.Button(
            self.prog_btn_row,
            text=tr("modal_btn_cancel", "✕ Cancel"),
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

        self.btn_pause_resume = tk.Button(
            self.prog_btn_row,
            text=tr("btn_pause", "⏸ Pause"),
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
        self.btn_close_prog = tk.Button(
            self.prog_btn_row,
            text=tr("browser_btn_close", "Close"),
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

        self.btn_open_folder = tk.Button(
            self.prog_btn_row,
            text=tr("btn_hist_folder", "📁 Open Folder"),
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
            command=self._on_open_file
        )

    def get_max_connections(self) -> int:
        if hasattr(self, "combo_threads"):
            try:
                val = int(str(self.combo_threads.get()).split()[0])
                return max(1, min(val, 32))
            except Exception:
                pass
        return self.default_connections or 8

    def get_speed_limit_bytes(self) -> float:
        if hasattr(self, "combo_speed"):
            try:
                return parse_speed_limit(self.combo_speed.get())
            except Exception:
                pass
        return float(self.default_speed_limit or 0.0)

    def attach_engine(self, engine: Any):
        """Attaches an active download engine to this modal for controls and metrics."""
        self.engine = engine

    def show_progress_view(self):
        """Transitions modal interface into standalone compact download progress view."""
        self.is_in_progress_view = True
        self.title(f"Downloading: {self.file_name} — Smart Download")
        self.frame_confirmation.pack_forget()
        self.frame_progress.pack(fill=tk.BOTH, expand=True)

        self.lbl_prog_filename.configure(text=self.file_name)
        cat, icon = get_file_category_and_icon(self.file_name)
        self.lbl_prog_cat.configure(text=f"{icon}  {cat}")
        self.lbl_prog_threads.configure(text=f"Threads: {self.get_max_connections()} Max")

        # Compact size
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        prog_w = min(int(580 * self.dpi_scale), max(500, int(sw * 0.90)))
        prog_h = min(int(320 * self.dpi_scale), max(270, int(sh * 0.70)))
        try:
            cur_x = self.winfo_x()
            cur_y = self.winfo_y()
            if cur_x <= 1 and cur_y <= 1:
                cur_x = max(0, (sw - prog_w) // 2)
                cur_y = max(0, (sh - prog_h) // 2)
        except Exception:
            cur_x = max(0, (sw - prog_w) // 2)
            cur_y = max(0, (sh - prog_h) // 2)
        self.geometry(f"{prog_w}x{prog_h}+{cur_x}+{cur_y}")
        self._draw_modal_progress(0.0)

    def _draw_modal_progress(self, pct: float):
        try:
            self._last_pct = float(pct)
            if not hasattr(self, "canvas_prog") or not self.canvas_prog.winfo_exists():
                return
            self.canvas_prog.delete("all")
            w = self.canvas_prog.winfo_width()
            if w <= 1:
                w = int(500 * self.dpi_scale)
            h = self.canvas_prog.winfo_height() or int(24 * self.dpi_scale)

            # Background track
            self.canvas_prog.create_rectangle(0, 0, w, h, fill=self.c_input_bg, outline=self.c_border)

            # Progress fill
            fill_w = max(0.0, min(float(w), (pct / 100.0) * float(w)))
            if fill_w > 0:
                fill_color = self.c_success if pct >= 100.0 else self.c_accent_dark
                line_color = "#34d399" if pct >= 100.0 else self.c_accent
                self.canvas_prog.create_rectangle(0, 0, fill_w, h, fill=fill_color, outline="")
                self.canvas_prog.create_line(0, 1, fill_w, 1, fill=line_color)

            # Percentage text overlay
            text_color = "white" if fill_w > (w * 0.45) else self.c_text_bright
            self.canvas_prog.create_text(w // 2, h // 2, text=f"{pct:.1f}%", font=("Segoe UI", 9, "bold"), fill=text_color)
        except Exception:
            pass

    def update_progress(self, downloaded: int, total: int, speed: float, eta: str, active_chunks: int = 1):
        """Thread-safe update of live download progress bar, speed, size, and ETA."""
        if threading.current_thread() != threading.main_thread():
            try:
                if self.winfo_exists():
                    self.after(0, lambda: self.update_progress(downloaded, total, speed, eta, active_chunks))
            except Exception:
                pass
            return

        pct = (downloaded / total * 100.0) if total > 0 else 0.0
        self._draw_modal_progress(pct)

        # Format speed
        if speed >= 1024 * 1024:
            speed_str = f"{speed / (1024*1024):.2f} MB/s"
        elif speed >= 1024:
            speed_str = f"{speed / 1024:.1f} KB/s"
        else:
            speed_str = f"{int(speed)} B/s"

        # Format sizes
        def _fmt(b):
            if b >= 1024 * 1024 * 1024:
                return f"{b / (1024**3):.2f} GB"
            if b >= 1024 * 1024:
                return f"{b / (1024**2):.1f} MB"
            if b >= 1024:
                return f"{b / 1024:.1f} KB"
            return f"{b} B"

        if total > 0:
            size_str = f"Transferred: {_fmt(downloaded)} / {_fmt(total)} ({pct:.1f}%)"
        else:
            size_str = f"Transferred: {_fmt(downloaded)} (Streaming...)"

        try:
            self.lbl_prog_size.configure(text=size_str)
            self.lbl_prog_speed.configure(text=f"Speed: {speed_str}")
            self.lbl_prog_eta.configure(text=f"Time Left: {eta}")
            self.lbl_prog_threads.configure(text=f"Threads: {active_chunks} Active")
            if not (self.engine and getattr(self.engine, "is_paused", False)):
                self.lbl_status.configure(text=tr("modal_status_downloading", "Status: Downloading..."), fg=self.c_accent)
        except Exception:
            pass

    def on_download_complete(self, dest_path: str, total_bytes: int, elapsed: float):
        """Thread-safe transition to completion view with Open File, Open Folder, and Close buttons."""
        if threading.current_thread() != threading.main_thread():
            try:
                if self.winfo_exists():
                    self.after(0, lambda: self.on_download_complete(dest_path, total_bytes, elapsed))
            except Exception:
                pass
            return

        self.dest_path = dest_path
        self.is_completed = True
        self._draw_modal_progress(100.0)
        try:
            self.lbl_status.configure(text=tr("modal_status_complete", "✅ Download Complete!"), fg=self.c_success)

            def _fmt(b):
                if b >= 1024 * 1024 * 1024:
                    return f"{b / (1024**3):.2f} GB"
                if b >= 1024 * 1024:
                    return f"{b / (1024**2):.1f} MB"
                if b >= 1024:
                    return f"{b / 1024:.1f} KB"
                return f"{b} B"

            avg_speed = (total_bytes / elapsed) if elapsed > 0 else 0
            if avg_speed >= 1024 * 1024:
                avg_str = f"{avg_speed / (1024*1024):.2f} MB/s"
            else:
                avg_str = f"{avg_speed / 1024:.1f} KB/s"

            self.lbl_prog_size.configure(text=f"Total: {_fmt(total_bytes)} in {elapsed:.1f}s")
            self.lbl_prog_speed.configure(text=f"Avg Speed: {avg_str}")
            self.lbl_prog_eta.configure(text="Time Left: 00:00:00")

            # Swap buttons to completion action buttons
            self.btn_pause_resume.pack_forget()
            self.btn_cancel_prog.pack_forget()
            self.btn_open_app_prog.pack_forget()

            self.btn_close_prog.pack(side=tk.RIGHT, padx=(6, 0))
            self.btn_open_folder.pack(side=tk.RIGHT, padx=(6, 0))
            self.btn_open_file.pack(side=tk.RIGHT)
        except Exception:
            pass

        try:
            hm = getattr(self, "history_manager", None)
            if not hm and self.parent_app:
                hm = getattr(self.parent_app, "history_manager", None)
            if not hm:
                hm = DownloadHistoryManager()
            hm.add_or_update_entry(
                url=self.url,
                file_path=dest_path,
                size_bytes=total_bytes,
                status="Completed",
                elapsed_sec=elapsed
            )
            if self.parent_app and hasattr(self.parent_app, "_refresh_history_table"):
                self.parent_app._refresh_history_table()
        except Exception:
            pass

    def on_download_error(self, err_msg: str):
        """Thread-safe display of download failure message."""
        if threading.current_thread() != threading.main_thread():
            try:
                if self.winfo_exists():
                    self.after(0, lambda: self.on_download_error(err_msg))
            except Exception:
                pass
            return
        try:
            self.lbl_status.configure(text=f"❌ Error: {err_msg}", fg=self.c_danger)
            self.btn_pause_resume.configure(state="disabled")
        except Exception:
            pass

        try:
            hm = getattr(self, "history_manager", None)
            if not hm and self.parent_app:
                hm = getattr(self.parent_app, "history_manager", None)
            if not hm:
                hm = DownloadHistoryManager()
            hm.add_or_update_entry(
                url=self.url,
                file_path=self.dest_path or (self.entry_dest.get().strip() if hasattr(self, "entry_dest") else ""),
                size_bytes=0,
                status="Failed",
                elapsed_sec=0.0
            )
            if self.parent_app and hasattr(self.parent_app, "_refresh_history_table"):
                self.parent_app._refresh_history_table()
        except Exception:
            pass

    def _on_dest_key_release(self, event=None):
        cur = self.entry_dest.get().strip()
        if cur:
            fn = os.path.basename(cur)
            if hasattr(self, "lbl_filename_val"):
                self.lbl_filename_val.configure(text=fn)
            cat, icon = get_file_category_and_icon(fn)
            if hasattr(self, "lbl_category_val"):
                self.lbl_category_val.configure(text=f"{icon}  {cat}")

    def _on_browse(self):
        cur = self.entry_dest.get().strip()
        init_dir = os.path.dirname(cur) if cur else os.path.join(os.path.expanduser("~"), "Downloads")
        init_file = os.path.basename(cur) if cur else (self.file_name or "download.bin")
        if not os.path.isdir(init_dir):
            init_dir = os.path.join(os.path.expanduser("~"), "Downloads")
        chosen = filedialog.asksaveasfilename(
            parent=self,
            title="Select Destination",
            initialdir=init_dir,
            initialfile=init_file
        )
        if chosen:
            self.entry_dest.delete(0, tk.END)
            self.entry_dest.insert(0, chosen)
            fn = os.path.basename(chosen)
            if hasattr(self, "lbl_filename_val"):
                self.lbl_filename_val.configure(text=fn)
            cat, icon = get_file_category_and_icon(fn)
            if hasattr(self, "lbl_category_val"):
                self.lbl_category_val.configure(text=f"{icon}  {cat}")

    def _call_on_confirm(self, dest: str, max_conn: int = 8, speed_limit: float = 0.0):
        if not self.on_confirm:
            return
        try:
            import inspect
            sig = inspect.signature(self.on_confirm)
            if len(sig.parameters) == 1:
                self.on_confirm(dest)
            else:
                self.on_confirm(dest, max_conn, speed_limit)
        except Exception:
            try:
                self.on_confirm(dest, max_conn, speed_limit)
            except TypeError:
                try:
                    self.on_confirm(dest)
                except Exception:
                    pass

    def _on_start_in_window(self):
        """Action 1: Starts download inside this window, keeping main window hidden."""
        final_dest = self.entry_dest.get().strip() or self.dest_path
        self.dest_path = final_dest
        self.file_name = os.path.basename(final_dest)
        conn_count = self.get_max_connections()
        speed_limit = self.get_speed_limit_bytes()
        self._confirmed = True
        self.show_progress_view()

        if self.on_start_in_window:
            try:
                self.on_start_in_window(final_dest, conn_count, speed_limit, self)
            except Exception:
                pass
        elif self.on_confirm:
            self._call_on_confirm(final_dest, conn_count, speed_limit)
        else:
            if not self.engine:
                self.engine = TurboDownloadEngine(
                    url=self.url,
                    destination_path=final_dest,
                    max_connections=conn_count,
                    rate_limit_bytes_per_sec=speed_limit,
                    on_progress=self.update_progress,
                    on_complete=self.on_download_complete,
                    on_error=self.on_download_error
                )
                self.engine.start()

    def _on_open_in_main(self):
        """Action 2: Restores main application window, populates task, and closes modal."""
        final_dest = self.entry_dest.get().strip() or self.dest_path
        conn_count = self.get_max_connections()
        speed_limit = self.get_speed_limit_bytes()
        self._confirmed = True

        is_running_now = self.is_in_progress_view or bool(self.engine and getattr(self.engine, "is_running", False))

        try:
            self.grab_release()
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass

        if is_running_now:
            # Transfer already active in background engine. Do NOT restart or wipe!
            if self.parent_app:
                try:
                    self.parent_app.restore_window()
                    if hasattr(self.parent_app, "root") and self.parent_app.root:
                        try:
                            self.parent_app.root.lift()
                            self.parent_app.root.focus_force()
                        except Exception:
                            pass
                    # Sync buttons to active engine state
                    if hasattr(self.parent_app, "btn_pause") and self.engine:
                        if getattr(self.engine, "is_paused", False):
                            self.parent_app.btn_pause.configure(text=tr("btn_resume", "▶ Resume"), bg=getattr(self.parent_app, "c_warning", "#f59e0b"), state="normal")
                        else:
                            self.parent_app.btn_pause.configure(text=tr("btn_pause", "⏸ Pause"), bg=getattr(self.parent_app, "c_panel_light", "#334155"), state="normal")
                    if hasattr(self.parent_app, "btn_cancel"):
                        self.parent_app.btn_cancel.configure(state="normal")
                    if hasattr(self.parent_app, "btn_start"):
                        self.parent_app.btn_start.configure(state="disabled")
                    self.parent_app.log(f"[GUI] Active download transferred to main window: {self.file_name}")
                except Exception:
                    pass
            elif self.master and hasattr(self.master, "restore_window"):
                try:
                    self.master.restore_window()
                except Exception:
                    pass
            return

        if self.on_open_in_main:
            try:
                self.on_open_in_main(final_dest, conn_count, speed_limit)
            except Exception:
                pass
        elif self.parent_app:
            try:
                self.parent_app.restore_window()
                self.parent_app.entry_url.delete(0, tk.END)
                self.parent_app.entry_url.insert(0, self.url)
                self.parent_app.entry_dest.delete(0, tk.END)
                self.parent_app.entry_dest.insert(0, final_dest)
                try:
                    self.parent_app.conn_var.set(str(conn_count))
                except Exception:
                    pass
                if speed_limit > 0:
                    try:
                        self.parent_app.entry_custom_speed.delete(0, tk.END)
                        self.parent_app.entry_custom_speed.insert(0, str(int(speed_limit / 1024.0)))
                    except Exception:
                        pass
                self.parent_app._on_start_download()
            except Exception:
                pass
        elif self.master:
            try:
                if hasattr(self.master, "restore_window"):
                    self.master.restore_window()
                elif hasattr(self.master, "deiconify"):
                    self.master.deiconify()
            except Exception:
                pass

    def _on_start(self):
        """Default start handler for Enter key and backward compatibility."""
        if self.on_start_in_window:
            self._on_start_in_window()
        else:
            final_dest = self.entry_dest.get().strip() or self.dest_path
            self.dest_path = final_dest
            conn_count = self.get_max_connections()
            speed_limit = self.get_speed_limit_bytes()
            self._confirmed = True
            try:
                self.grab_release()
            except Exception:
                pass
            if self.on_confirm:
                self._call_on_confirm(final_dest, conn_count, speed_limit)
            try:
                self.destroy()
            except Exception:
                pass

    def _on_pause_resume(self):
        if not self.engine:
            return
        if getattr(self.engine, "is_paused", False):
            try:
                self.engine.resume()
            except Exception:
                pass
            self.btn_pause_resume.configure(text=tr("btn_pause", "⏸ Pause"), bg=self.c_panel_light)
            self.lbl_status.configure(text=f"{tr('col_chunk_status', 'Status')}: {tr('status_in_progress', 'Downloading...')}", fg=self.c_accent)
            if self.parent_app and hasattr(self.parent_app, "btn_pause"):
                try:
                    self.parent_app.btn_pause.configure(text=tr("btn_pause", "⏸ Pause"), bg=getattr(self.parent_app, "c_panel_light", "#334155"))
                except Exception:
                    pass
        else:
            try:
                self.engine.pause()
            except Exception:
                pass
            self.btn_pause_resume.configure(text=tr("btn_resume", "▶ Resume"), bg=self.c_success)
            self.lbl_status.configure(text=f"{tr('col_chunk_status', 'Status')}: {tr('status_paused', 'Paused')}", fg=self.c_warning)
            if self.parent_app and hasattr(self.parent_app, "btn_pause"):
                try:
                    self.parent_app.btn_pause.configure(text=tr("btn_resume", "▶ Resume"), bg=getattr(self.parent_app, "c_warning", "#f59e0b"))
                except Exception:
                    pass

    def _on_open_file(self):
        open_downloaded_file(self.dest_path)

    def _on_open_folder(self):
        open_containing_folder(self.dest_path)

    def grab_set(self):
        """No-op: Eliminates Win32 input capture and message pump locking."""
        pass

    def grab_set_global(self):
        """No-op: Eliminates Win32 input capture and message pump locking."""
        pass

    def destroy(self):
        if getattr(self, "_idle_job", None):
            try:
                self.after_cancel(self._idle_job)
            except Exception:
                pass
            self._idle_job = None
        if hasattr(self, "_modal_icon_photo"):
            _detach_photo_tk(self._modal_icon_photo)
            self._modal_icon_photo = None
        try:
            self.grab_release()
        except Exception:
            pass
        if self.parent_app and getattr(self.parent_app, "_confirm_modal", None) is self:
            self.parent_app._confirm_modal = None
        super().destroy()

    def _on_close(self):
        """Action 3: Clean cancellation without starting download."""
        self._confirmed = False
        was_running = False
        if hasattr(self, "engine") and self.engine:
            was_running = getattr(self.engine, "is_running", False)
            try:
                self.engine.cancel()
            except Exception:
                pass

        if self.parent_app:
            try:
                if hasattr(self.parent_app, "clear_last_clipboard_url"):
                    self.parent_app.clear_last_clipboard_url()
                if getattr(self.parent_app, "_confirm_modal", None) is self:
                    self.parent_app._confirm_modal = None
                if was_running:
                    self.parent_app.engine = None
                    self.parent_app.btn_start.configure(state="normal")
                    self.parent_app.btn_pause.configure(state="disabled", text=tr("btn_pause", "⏸ Pause"), bg=getattr(self.parent_app, "c_panel_light", "#334155"))
                    self.parent_app.btn_cancel.configure(state="disabled")
                    self.parent_app.card_size.configure(text=tr("status_cancelled", "Cancelled"))
                    self.parent_app.log(f"[CLIPBOARD] Standalone download cancelled: {self.file_name}")
            except Exception:
                pass

        try:
            self.grab_release()
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass
        if self.on_cancel:
            try:
                self.on_cancel()
            except Exception:
                pass


DownloadConfirmationDialog = DownloadConfirmationModal


# ======================================================================================
# 3F. SLEEK GRAB-FREE REFRESH EXPIRED LINK MODAL DIALOG
# ======================================================================================


DownloadConfirmModal = DownloadConfirmationModal

