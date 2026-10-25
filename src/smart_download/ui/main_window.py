"""
ModernFramelessGUI: Complete Dark-themed, frameless, dynamic chunking download manager GUI.
"""
import sys
import os
import time
import re
import math
import shutil
import tempfile
import hashlib
import threading
import subprocess
import weakref
import queue
import ssl
import urllib.request
import json
import urllib.parse
import urllib.error
import ctypes
import zlib
import zipfile
import tarfile
from typing import List, Optional, Callable, Dict, Any, Union, Tuple

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
try:
    from PIL import Image, ImageTk
except ImportError:
    Image = None
    ImageTk = None

from ..config import (
    get_resource_path,
    get_config_dir,
    get_app_config_dir,
    get_settings_file_path,
    load_settings,
    save_settings,
    get_setting,
    set_setting,
    APP_NAME,
    APP_TITLE,
    APP_ID,
    APP_VERSION,
    APP_AUTHOR,
    GITHUB_REPO_OWNER,
    GITHUB_REPO_NAME,
    DEFAULT_USER_AGENT,
    CHUNK_SIZE_KB,
    MAX_CONCURRENT_CHUNKS,
    DEFAULT_CHUNKS,
    MIN_CHUNK_BYTES,
    BUFFER_SIZE,
)
from ..locales.i18n import (
    LocalizationManager,
    tr,
    get_current_language,
    set_current_language,
    TRANSLATIONS,
)
from ..utils.dpi import enable_high_dpi_awareness, get_windows_work_area
from ..utils.clipboard import _win32_clipboard_get, get_clipboard_text
from ..utils.url_utils import (
    COMMON_DOWNLOAD_EXTENSIONS,
    WEB_SCRIPT_EXTENSIONS,
    is_downloadable_url,
    clean_download_filename,
    derive_download_filename,
    is_potential_html_url,
    parse_filename_from_cd_header,
    parse_speed_limit,
    format_speed,
)
from ..utils.file_ops import (
    MagicBytesDetector,
    calculate_file_integrity,
    auto_unpack_archive,
    get_file_category_and_icon,
    CATEGORY_SUBFOLDERS,
    resolve_categorized_path,
    open_downloaded_file,
    open_containing_folder,
)
from ..utils.tk_helpers import (
    _detach_photo_tk,
    _detach_widget_tk_refs,
    _drain_bg_tk_callbacks,
)
from ..core.rate_limiter import TokenBucketRateLimiter
from ..core.chunk import DownloadChunk, get_permissive_ssl_context, _SSL_CONTEXT_LOCK
from ..core.html_resolver import (
    _HtmlCandidateExtractor,
    resolve_all_download_candidates,
    _HtmlLinkCandidateParser,
    resolve_real_download_url,
    validate_refresh_url,
)
from ..core.engine import TurboDownloadEngine
from ..core.stream_coordinator import StreamDownloadCoordinator
from ..core.history import DownloadHistoryManager

from ..services.startup_service import (
    IS_WINDOWS,
    GWL_STYLE,
    GWL_EXSTYLE,
    WS_EX_APPWINDOW,
    WS_EX_TOOLWINDOW,
    WS_MINIMIZEBOX,
    WS_SYSMENU,
    SW_HIDE,
    SW_MINIMIZE,
    SW_RESTORE,
    SW_SHOW,
    get_installed_exe_path,
    get_startup_folder,
    get_startup_dir,
    is_startup_enabled,
    enable_startup,
    disable_startup,
    get_startup_entry,
)
from ..services.single_instance import notify_running_instance
from ..services.youtube_service import (
    YouTubeResolver,
    MediaResolver,
    is_youtube_url,
    is_social_media_url,
    is_media_url,
    extract_youtube_id,
    extract_media_platform,
    extract_media_id,
    is_ytdlp_available,
    get_ytdlp_version,
    update_ytdlp_engine,
    has_ffmpeg,
    find_ffmpeg_bin,
    sanitize_filename,
    YouTubeStreamInfo,
    MediaStreamInfo,
    VideoFormatOption,
    format_filesize,
    SUPPORTED_COOKIE_BROWSERS,
    detect_installed_cookie_browsers,
)
from ..services.updater_service import (
    parse_version,
    is_newer_version,
    YtDlpAutoUpdater,
    AppAutoUpdater,
    get_ytdlp_plugin_dir,
)
from ..services.browser.bridge_server import BrowserBridgeServer, DEFAULT_BRIDGE_PORT
from ..services.browser.registry import (
    register_native_host,
    unregister_native_host,
    check_and_register_browser,
    register_browser_extensions,
    unregister_browser_extensions,
    is_registered as is_browser_registered,
    get_status as get_browser_reg_status,
)

from .components.base_modal import SafeModalDialog
from .components.tooltip import ToolTip
from .modals.toasts import FetchingLinkToast, StartupWelcomeToast
from .modals.quality_modal import QualitySelectionModal
from .modals.confirm_modal import (
    DownloadConfirmationModal,
    DownloadConfirmationDialog,
    DownloadConfirmModal,
)
from .modals.candidates_modal import MultipleCandidatesModal
from .modals.refresh_modal import RefreshLinkModal, RefreshLinkDialog
from .modals.update_modal import AppUpdateModal
from .system_tray import SystemTrayManager, PYSTRAY_AVAILABLE

class ModernFramelessGUI:
    """
    Sleek Frameless Window GUI with:
    - Custom draggable dark title bar with minimize and close controls.
    - Windows OS taskbar integration via ctypes.
    - Per-download manual rate limiter controls (presets, custom KB/s, dynamic slider).
    - TDM-style visual segmented chunk progress bar.
    - Real-time performance metrics (speed, progress, ETA, active threads).
    - Detailed chunk status table and event logging console.
    """
    def __init__(self, root: tk.Tk, start_hidden: Optional[bool] = None, initial_url: Optional[str] = None):
        self.root = root
        if start_hidden is None:
            start_hidden = any(arg.lower() in ("--background", "-background", "/background",
                                                "--minimized", "-minimized", "/minimized")
                               for arg in sys.argv[1:])
        self._start_hidden: bool = bool(start_hidden)
        self._was_started_hidden: bool = bool(start_hidden)
        self._startup_enabled: bool = is_startup_enabled()
        self.minimize_to_tray: bool = bool(get_setting("minimize_to_tray", True))
        self.auto_categorize_folders: bool = bool(get_setting("auto_categorize_folders", True))
        self.history_manager = DownloadHistoryManager()
        self.cookies_browser: str = str(get_setting("cookies_browser", "auto") or "auto")
        self.cookies_file: str = str(get_setting("cookies_file", "") or "")
        self.engine: Optional[Union[TurboDownloadEngine, StreamDownloadCoordinator]] = None
        self.speed_limit: float = 0.0
        self._yt_cancel_event = threading.Event()
        self._quality_modal: Optional[tk.Toplevel] = None
        self._confirm_modal: Optional[tk.Toplevel] = None
        self._update_modal: Optional[tk.Toplevel] = None
        self._fetching_toast: Optional[Any] = None
        self._bg_toast: Optional[tk.Toplevel] = None
        self._refresh_job = None
        self._update_check_job = None
        self._closing = False
        self._log_jobs: List[Any] = []
        self._gui_dispatch_queue: queue.Queue = queue.Queue()

        # Clipboard URL Sniffer (Automatic clipboard monitor)
        self._clipboard_sniffer_active: bool = True
        self._auto_start_clipboard: bool = True
        self._last_clipboard_url: Optional[str] = None
        self._last_clipboard_seq: Optional[int] = None
        self._clipboard_job = None
        self._clipboard_poll_interval = 500  # ms

        # DPI Scaling & Metrics Calculation
        try:
            dpi = float(self.root.winfo_fpixels('1i'))
        except Exception:
            dpi = 96.0
        self.dpi = dpi if dpi > 0 else 96.0
        self.dpi_scale = max(1.0, self.dpi / 96.0)

        # Configure Tk font scaling ratio to match physical monitor DPI
        try:
            self.root.tk.call('tk', 'scaling', self.dpi / 72.0)
        except Exception:
            pass

        # Window Configuration (DPI Aware)
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        target_w = int(980 * self.dpi_scale)
        target_h = int(760 * self.dpi_scale)
        self.width = min(target_w, max(850, int(sw * 0.92)))
        self.height = min(target_h, max(650, int(sh * 0.88)))
        self._setup_window()
        self._init_theme()
        self._build_ui()

        if initial_url:
            try:
                self.entry_url.delete(0, tk.END)
                self.entry_url.insert(0, initial_url)
            except Exception:
                pass

        # Initialize Browser Bridge loopback IPC server using weakref callbacks
        # so background HTTP threads never retain strong references to self/root.tk
        _weak_self = weakref.ref(self)

        def _bridge_dl(task):
            g = _weak_self()
            if g is not None and not getattr(g, "_closing", False):
                g._on_browser_download_received(task)

        def _bridge_log(msg):
            g = _weak_self()
            if g is not None and not getattr(g, "_closing", False):
                g.log(msg)

        def _bridge_show():
            g = _weak_self()
            if g is not None and not getattr(g, "_closing", False):
                g.dispatch_to_main_thread(g.restore_window)

        self.bridge_server = BrowserBridgeServer(
            port=DEFAULT_BRIDGE_PORT,
            on_download=_bridge_dl,
            on_log=_bridge_log,
            on_show=_bridge_show
        )
        self.bridge_server.start()

        # Initialize Clipboard URL Sniffer (TDM-style auto detection)
        self._init_clipboard_sniffer()

        # Initialize Windows System Tray Notification Area Manager
        self.tray_manager = SystemTrayManager(self)
        try:
            self.tray_manager.start()
        except Exception:
            pass

        # Configure window close and destroy protocols
        try:
            self.root.protocol("WM_DELETE_WINDOW", self._on_close)
            self.root.bind("<Destroy>", self._on_root_destroyed, add="+")
        except Exception:
            pass

        # Start periodic GUI refresh timer
        self._refresh_job = self.root.after(100, self._gui_refresh_tick)

        self._bg_notify_job = None
        if self._start_hidden and os.environ.get("SD_DISABLE_STARTUP_TOAST") != "1":
            try:
                self._bg_notify_job = self.root.after(400, self._show_background_startup_notification)
            except Exception:
                pass

        # Idempotent and non-blocking embedded browser self-registration
        if os.environ.get("SD_DISABLE_AUTO_REGISTER") != "1" and "unittest" not in sys.modules:
            self._start_browser_self_registration()

        self._download_queue: List[Tuple[str, str, int, float]] = []
        self._candidates_modal: Optional[tk.Toplevel] = None
        LocalizationManager.get_instance().register_observer(self._update_ui_language)

        # Non-blocking background check for application and yt-dlp updates
        if os.environ.get("SD_DISABLE_AUTO_UPDATE") != "1" and "unittest" not in sys.modules:
            try:
                self._update_check_job = self.root.after(2500, self._start_auto_update_check)
            except Exception:
                pass

    def toggle_language(self):
        """Toggles active language between Arabic and English dynamically in-place."""
        new_lang = LocalizationManager.get_instance().toggle_language()
        self._update_ui_language()
        self.log(f"[LOCALE] Switched interface language to: {new_lang.upper()}")

    def _update_ui_language(self):
        """Dynamically re-translates and updates all main UI widgets in-place."""
        cur_lang = LocalizationManager.get_instance().get_language()
        if hasattr(self, "btn_lang_toggle") and self.btn_lang_toggle.winfo_exists():
            self.btn_lang_toggle.configure(text="🌐 English" if cur_lang == "ar" else "🌐 العربية")

        if hasattr(self, "title_lbl") and self.title_lbl.winfo_exists():
            self.title_lbl.configure(text=tr("app_header"))
        if hasattr(self, "subtitle_lbl") and self.subtitle_lbl.winfo_exists():
            self.subtitle_lbl.configure(text=tr("app_subtitle"))
        try:
            self.root.title(tr("app_title"))
        except Exception:
            pass

        # Input card
        if hasattr(self, "lbl_url") and self.lbl_url.winfo_exists():
            self.lbl_url.configure(text=tr("lbl_url"))
        if hasattr(self, "btn_paste") and self.btn_paste.winfo_exists():
            self.btn_paste.configure(text=tr("btn_paste"))
        if hasattr(self, "btn_refresh_url") and self.btn_refresh_url.winfo_exists():
            self.btn_refresh_url.configure(text=tr("btn_refresh_url"))
        if hasattr(self, "lbl_dest") and self.lbl_dest.winfo_exists():
            self.lbl_dest.configure(text=tr("lbl_dest"))
        if hasattr(self, "btn_browse") and self.btn_browse.winfo_exists():
            self.btn_browse.configure(text=tr("btn_browse"))

        # Limiter & options card
        if hasattr(self, "lbl_conn") and self.lbl_conn.winfo_exists():
            self.lbl_conn.configure(text=tr("lbl_threads"))
        if hasattr(self, "lbl_limit") and self.lbl_limit.winfo_exists():
            self.lbl_limit.configure(text=tr("lbl_speed_limiter"))
        if hasattr(self, "lbl_custom") and self.lbl_custom.winfo_exists():
            self.lbl_custom.configure(text=tr("lbl_custom_speed"))
        if hasattr(self, "btn_apply_speed") and self.btn_apply_speed.winfo_exists():
            self.btn_apply_speed.configure(text=tr("btn_apply_limit"))
        if hasattr(self, "lbl_slider_title") and self.lbl_slider_title.winfo_exists():
            self.lbl_slider_title.configure(text=tr("lbl_live_throttle_slider"))

        # Actions card
        if hasattr(self, "btn_start") and self.btn_start.winfo_exists():
            self.btn_start.configure(text=tr("btn_start"))
        if hasattr(self, "btn_pause") and self.btn_pause.winfo_exists():
            if self.engine and getattr(self.engine, "is_paused", False):
                self.btn_pause.configure(text=tr("btn_resume"))
            else:
                self.btn_pause.configure(text=tr("btn_pause"))
        if hasattr(self, "btn_cancel") and self.btn_cancel.winfo_exists():
            self.btn_cancel.configure(text=tr("btn_cancel"))
        if hasattr(self, "btn_refresh_link") and self.btn_refresh_link.winfo_exists():
            self.btn_refresh_link.configure(text=tr("btn_refresh_url"))
        if hasattr(self, "btn_browser") and self.btn_browser.winfo_exists():
            self.btn_browser.configure(text=tr("btn_browser"))
        if hasattr(self, "btn_check_updates") and self.btn_check_updates.winfo_exists():
            self.btn_check_updates.configure(text=tr("btn_check_updates"))

        self._update_sniffer_btn()
        self._update_startup_btn()
        self._update_cookies_btn()
        self._update_auto_cat_btn()

        # Metrics card
        if hasattr(self, "lbl_t_speed") and self.lbl_t_speed.winfo_exists():
            self.lbl_t_speed.configure(text=tr("metric_speed"))
        if hasattr(self, "lbl_t_size") and self.lbl_t_size.winfo_exists():
            self.lbl_t_size.configure(text=tr("metric_total_size"))
        if hasattr(self, "lbl_t_eta") and self.lbl_t_eta.winfo_exists():
            self.lbl_t_eta.configure(text=tr("metric_eta"))
        if hasattr(self, "lbl_t_threads") and self.lbl_t_threads.winfo_exists():
            self.lbl_t_threads.configure(text=tr("metric_threads"))

        # Notebook tabs
        if hasattr(self, "notebook") and self.notebook.winfo_exists():
            try:
                self.notebook.tab(0, text=tr("tab_chunks"))
            except Exception:
                pass
            try:
                self.notebook.tab(1, text=tr("tab_logs"))
            except Exception:
                pass
            try:
                self.notebook.tab(2, text=tr("tab_history"))
            except Exception:
                pass

        # Chunks treeview headings
        if hasattr(self, "tree_chunks") and self.tree_chunks.winfo_exists():
            self.tree_chunks.heading("id", text=tr("col_chunk_id"))
            self.tree_chunks.heading("range", text=tr("col_chunk_range"))
            self.tree_chunks.heading("size", text=tr("col_chunk_size"))
            self.tree_chunks.heading("downloaded", text=tr("col_chunk_downloaded"))
            self.tree_chunks.heading("pct", text=tr("col_chunk_pct"))
            self.tree_chunks.heading("status", text=tr("col_chunk_status"))

        # History toolbar
        if hasattr(self, "lbl_filter") and self.lbl_filter.winfo_exists():
            self.lbl_filter.configure(text=tr("lbl_filter"))
        if hasattr(self, "btn_hist_open") and self.btn_hist_open.winfo_exists():
            self.btn_hist_open.configure(text=tr("btn_hist_open"))
        if hasattr(self, "btn_hist_folder") and self.btn_hist_folder.winfo_exists():
            self.btn_hist_folder.configure(text=tr("btn_hist_folder"))
        if hasattr(self, "btn_hist_redownload") and self.btn_hist_redownload.winfo_exists():
            self.btn_hist_redownload.configure(text=tr("btn_hist_redownload"))
        if hasattr(self, "btn_hist_remove") and self.btn_hist_remove.winfo_exists():
            self.btn_hist_remove.configure(text=tr("btn_hist_remove"))
        if hasattr(self, "btn_hist_clear") and self.btn_hist_clear.winfo_exists():
            self.btn_hist_clear.configure(text=tr("btn_hist_clear"))

        # History treeview headings
        if hasattr(self, "tree_history") and self.tree_history.winfo_exists():
            self.tree_history.heading("category", text=tr("col_hist_category"))
            self.tree_history.heading("filename", text=tr("col_hist_filename"))
            self.tree_history.heading("size", text=tr("col_hist_size"))
            self.tree_history.heading("status", text=tr("col_hist_status"))
            self.tree_history.heading("date", text=tr("col_hist_date"))
            self.tree_history.heading("path", text=tr("col_hist_path"))

        # History filter combo and table refresh
        if hasattr(self, "combo_history_filter") and self.combo_history_filter.winfo_exists():
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
            self.combo_history_filter.configure(values=categories)
            cur = self.combo_history_filter.get()
            if not cur or cur in ("All Categories", "كافة التصنيفات", "All", "الكل"):
                self.combo_history_filter.set(categories[0])
            self._refresh_history_table()

        if hasattr(self, "lbl_active_limit") and self.lbl_active_limit.winfo_exists():
            cur_limit = getattr(self, "speed_limit", 0.0)
            if cur_limit <= 0:
                self.lbl_active_limit.configure(text=tr("lbl_current_unlimited", "● Current: Unlimited"))
            else:
                self.lbl_active_limit.configure(text=tr("lbl_current_limit", "● Current: {limit}").format(limit=format_speed(cur_limit)))
        if hasattr(self, "lbl_slider_val") and self.lbl_slider_val.winfo_exists():
            cur_val = getattr(self.slider_speed, "get", lambda: 0)() if hasattr(self, "slider_speed") else 0
            if cur_val <= 0:
                self.lbl_slider_val.configure(text=f"{tr('lbl_unlimited', 'Unlimited')} (0 KB/s)")
            else:
                self.lbl_slider_val.configure(text=f"{cur_val:,} KB/s ({cur_val/1024:.1f} MB/s)")

        # Tray menu
        if hasattr(self, "tray_manager") and self.tray_manager:
            try:
                self.tray_manager.update_menu()
            except Exception:
                pass

    def _show_multiple_candidates_dialog(self, source_url: str, candidates: List[Dict[str, Any]], page_title: str = ""):
        """Displays modern dark-themed modal for choosing among multiple download links."""
        if threading.current_thread() != threading.main_thread():
            self.root.after(0, lambda: self._show_multiple_candidates_dialog(source_url, candidates, page_title))
            return

        self._close_fetching_toast()

        def _on_download_selected(selected: List[Dict[str, Any]]):
            if not selected:
                return
            if len(selected) == 1:
                cand = selected[0]
                dl_url = cand["url"]
                fn = cand.get("filename") or derive_download_filename(dl_url)
                downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
                auto_cat = getattr(self, "auto_categorize_folders", True)
                dest = resolve_categorized_path(downloads_dir, fn, auto_categorize=auto_cat)
                self._show_download_confirmation_dialog(dl_url, dest)
            else:
                self._queue_multiple_candidate_downloads(selected)

        def _on_download_all(all_cands: List[Dict[str, Any]]):
            self._queue_multiple_candidate_downloads(all_cands)

        modal = MultipleCandidatesModal(
            parent=self.root,
            source_url=source_url,
            candidates=candidates,
            page_title=page_title,
            theme=self._theme_dict(),
            on_download_selected=_on_download_selected,
            on_download_all=_on_download_all,
            parent_app=self
        )
        self._candidates_modal = modal

    def _queue_multiple_candidate_downloads(self, items: List[Dict[str, Any]]):
        """Queues a list of candidate downloads, starting the first one if idle."""
        if not items:
            return
        downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
        auto_cat = getattr(self, "auto_categorize_folders", True)
        try:
            max_conn = int(self.conn_var.get())
        except Exception:
            max_conn = 8
        try:
            kb_limit = float(self.entry_custom_speed.get().strip())
        except Exception:
            kb_limit = 0.0
        bytes_limit = kb_limit * 1024.0 if kb_limit > 0 else 0.0

        self.log(f"[BATCH] Queuing {len(items)} download candidates...")
        for item in items:
            dl_url = item["url"]
            fn = item.get("filename") or derive_download_filename(dl_url)
            dest = resolve_categorized_path(downloads_dir, fn, auto_categorize=auto_cat)
            self.queue_download(dl_url, dest, max_conn=max_conn, bytes_limit=bytes_limit)

    def queue_download(self, url: str, dest: str, max_conn: int = 8, bytes_limit: float = 0.0):
        """Queues a download task, starting it immediately if no download is currently running."""
        if not hasattr(self, "_download_queue"):
            self._download_queue = []

        if not (self.engine and getattr(self.engine, "is_running", False)):
            self._start_download_with_engine(url, dest, max_conn, bytes_limit)
        else:
            self._download_queue.append((url, dest, max_conn, bytes_limit))
            self.log(f"[QUEUE] Task queued: {os.path.basename(dest)} ({len(self._download_queue)} queued)")

    def _start_browser_self_registration(self):
        """Asynchronously checks and registers or heals browser integration in background without blocking GUI."""
        def _task():
            try:
                check_and_register_browser()
            except Exception:
                pass
        t = threading.Thread(target=_task, daemon=True, name="BrowserAutoRegisterThread")
        t.start()

    def _show_background_startup_notification(self):
        """Displays Windows startup welcome toast when running in background on boot."""
        if getattr(self, "_closing", False):
            return
        if not getattr(self, "_start_hidden", False) and not getattr(self, "_was_started_hidden", False):
            return
        if os.environ.get("SD_DISABLE_STARTUP_TOAST") == "1":
            return
        if not get_setting("show_startup_toast", True):
            return

        try:
            self._dismiss_bg_toast()
            self._bg_toast = StartupWelcomeToast(
                self.root,
                parent_app=self,
                theme=self._theme_dict(),
                duration_ms=4000
            )
        except Exception:
            pass

    def _show_background_toast(self, message: str):
        """Displays a brief, non-intrusive dark-themed toast notification at the bottom-right corner."""
        try:
            self._dismiss_bg_toast()

            toast = tk.Toplevel(self.root)
            self._bg_toast = toast
            toast.overrideredirect(True)
            toast.configure(bg=self.c_border)
            try:
                toast.attributes("-topmost", True)
            except Exception:
                pass

            try:
                dpi = float(self.root.winfo_fpixels('1i')) if self.root.winfo_exists() else 96.0
            except Exception:
                dpi = 96.0
            scale = max(1.0, dpi / 96.0)

            w = int(370 * scale)
            h = int(76 * scale)
            sw = toast.winfo_screenwidth()
            sh = toast.winfo_screenheight()
            x = max(0, sw - w - int(24 * scale))
            y = max(0, sh - h - int(48 * scale))
            toast.geometry(f"{w}x{h}+{x}+{y}")

            inner = tk.Frame(toast, bg=self.c_panel, padx=12, pady=10)
            inner.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

            lbl_ico = tk.Label(inner, text="🚀", font=("Segoe UI", 16), bg=self.c_panel, fg=self.c_accent)
            lbl_ico.pack(side=tk.LEFT, padx=(0, 10))

            text_frame = tk.Frame(inner, bg=self.c_panel)
            text_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

            lbl_t = tk.Label(text_frame, text="Smart Download (SD)", font=("Segoe UI", 9, "bold"), bg=self.c_panel, fg=self.c_accent, anchor="w")
            lbl_t.pack(anchor="w")

            lbl_m = tk.Label(text_frame, text=message, font=("Segoe UI", 8), bg=self.c_panel, fg=self.c_text_bright, anchor="w")
            lbl_m.pack(anchor="w")

            btn_close = tk.Label(inner, text="✕", font=("Segoe UI", 9, "bold"), bg=self.c_panel, fg=self.c_text_muted, cursor="hand2")
            btn_close.pack(side=tk.RIGHT, padx=(4, 0))
            btn_close.bind("<Button-1>", lambda e: self._dismiss_bg_toast())

            # Auto-dismiss after 3200ms
            toast._dismiss_job = toast.after(3200, self._dismiss_bg_toast)
        except Exception:
            pass

    def _dismiss_bg_toast(self):
        """Safely dismisses the background notification toast."""
        if hasattr(self, "_bg_toast") and self._bg_toast:
            try:
                if hasattr(self._bg_toast, "_close"):
                    self._bg_toast._close()
                elif hasattr(self._bg_toast, "_dismiss_job") and self._bg_toast._dismiss_job:
                    try:
                        self._bg_toast.after_cancel(self._bg_toast._dismiss_job)
                    except Exception:
                        pass
                    self._bg_toast._dismiss_job = None
                if self._bg_toast and hasattr(self._bg_toast, "winfo_exists") and self._bg_toast.winfo_exists():
                    self._bg_toast.destroy()
            except Exception:
                pass
            self._bg_toast = None

    def _show_fetching_toast(self, url: str, on_cancel: Optional[Callable[[], None]] = None) -> Optional[FetchingLinkToast]:
        """Displays instantaneous (< 50ms) sleek dark-themed fetching indicator toast."""
        self._close_fetching_toast()
        try:
            def _handle_cancel():
                self.log(f"[FETCHING] Link analysis cancelled by user for: {url}")
                if hasattr(self, "_yt_cancel_event") and self._yt_cancel_event:
                    self._yt_cancel_event.set()
                if callable(on_cancel):
                    try:
                        on_cancel()
                    except Exception:
                        pass
                self._fetching_toast = None
                self.clear_last_clipboard_url()
                try:
                    self.btn_start.configure(state="normal")
                    self.btn_pause.configure(state="disabled")
                    self.btn_cancel.configure(state="disabled")
                    self.card_size.configure(text=tr("status_ready", "Ready"))
                except Exception:
                    pass

            self._fetching_toast = FetchingLinkToast(
                parent=self.root,
                url=url,
                theme=self._theme_dict(),
                on_cancel=_handle_cancel,
                parent_app=self
            )
            return self._fetching_toast
        except Exception as e:
            self.log(f"[FETCHING] Failed to display fetching toast: {e}")
            return None

    def _close_fetching_toast(self):
        """Safely closes active fetching indicator toast."""
        if hasattr(self, "_fetching_toast") and self._fetching_toast:
            try:
                self._fetching_toast.close()
            except Exception:
                pass
            self._fetching_toast = None

    def _theme_dict(self) -> Dict[str, str]:
        """Returns active theme dictionary for modals and child widgets."""
        return {
            "c_bg": self.c_bg,
            "c_panel": self.c_panel,
            "c_panel_light": self.c_panel_light,
            "c_border": self.c_border,
            "c_accent": self.c_accent,
            "c_accent_dark": self.c_accent_dark,
            "c_success": self.c_success,
            "c_danger": self.c_danger,
            "c_warning": self.c_warning,
            "c_text_bright": self.c_text_bright,
            "c_text_muted": self.c_text_muted,
            "c_input_bg": self.c_input_bg
        }

    def show_safe_error(self, title: str, message: str):
        """Displays error via safe theme dialog without Win32 message loop corruption."""
        if hasattr(self, "log"):
            try:
                self.log(f"[ERROR] {title}: {message}")
            except Exception:
                pass
        if threading.current_thread() != threading.main_thread():
            if hasattr(self, "root") and self.root:
                try:
                    self.root.after(0, lambda: self.show_safe_error(title, message))
                except Exception:
                    pass
            return
        if getattr(messagebox.showerror, "_mock_name", None) or hasattr(messagebox.showerror, "mock"):
            messagebox.showerror(title, message)
            return
        try:
            if hasattr(self, "root") and self.root and self.root.winfo_exists():
                if hasattr(self, "_active_modal_dialog") and self._active_modal_dialog:
                    try:
                        if self._active_modal_dialog.winfo_exists():
                            try:
                                self._active_modal_dialog.grab_release()
                            except Exception:
                                pass
                            self._active_modal_dialog.destroy()
                    except Exception:
                        pass
                    self._active_modal_dialog = None
                self._active_modal_dialog = SafeModalDialog(
                    self.root, title, message, dialog_type="error", theme=self._theme_dict()
                )
        except Exception:
            pass

    def show_safe_info(self, title: str, message: str):
        """Displays info via safe theme dialog."""
        if hasattr(self, "log"):
            try:
                self.log(f"[INFO] {title}: {message}")
            except Exception:
                pass
        if threading.current_thread() != threading.main_thread():
            if hasattr(self, "root") and self.root:
                try:
                    self.root.after(0, lambda: self.show_safe_info(title, message))
                except Exception:
                    pass
            return
        if getattr(messagebox.showinfo, "_mock_name", None) or hasattr(messagebox.showinfo, "mock"):
            messagebox.showinfo(title, message)
            return
        try:
            if hasattr(self, "root") and self.root and self.root.winfo_exists():
                if hasattr(self, "_active_modal_dialog") and self._active_modal_dialog:
                    try:
                        if self._active_modal_dialog.winfo_exists():
                            try:
                                self._active_modal_dialog.grab_release()
                            except Exception:
                                pass
                            self._active_modal_dialog.destroy()
                    except Exception:
                        pass
                    self._active_modal_dialog = None
                self._active_modal_dialog = SafeModalDialog(
                    self.root, title, message, dialog_type="info", theme=self._theme_dict()
                )
        except Exception:
            pass

    def show_safe_warning(self, title: str, message: str):
        """Displays warning via safe theme dialog."""
        if hasattr(self, "log"):
            try:
                self.log(f"[WARNING] {title}: {message}")
            except Exception:
                pass
        if threading.current_thread() != threading.main_thread():
            if hasattr(self, "root") and self.root:
                try:
                    self.root.after(0, lambda: self.show_safe_warning(title, message))
                except Exception:
                    pass
            return
        if getattr(messagebox.showwarning, "_mock_name", None) or hasattr(messagebox.showwarning, "mock"):
            messagebox.showwarning(title, message)
            return
        try:
            if hasattr(self, "root") and self.root and self.root.winfo_exists():
                if hasattr(self, "_active_modal_dialog") and self._active_modal_dialog:
                    try:
                        if self._active_modal_dialog.winfo_exists():
                            try:
                                self._active_modal_dialog.grab_release()
                            except Exception:
                                pass
                            self._active_modal_dialog.destroy()
                    except Exception:
                        pass
                    self._active_modal_dialog = None
                self._active_modal_dialog = SafeModalDialog(
                    self.root, title, message, dialog_type="warning", theme=self._theme_dict()
                )
        except Exception:
            pass

    def ask_safe_yesno(self, title: str, message: str, on_yes: Callable[[], None], on_no: Optional[Callable[[], None]] = None):
        """Safe confirmation modal with Yes/No actions."""
        if threading.current_thread() != threading.main_thread():
            if hasattr(self, "root") and self.root:
                try:
                    self.root.after(0, lambda: self.ask_safe_yesno(title, message, on_yes, on_no))
                except Exception:
                    pass
            return
        if getattr(messagebox.askyesno, "_mock_name", None) or hasattr(messagebox.askyesno, "mock"):
            if messagebox.askyesno(title, message):
                on_yes()
            elif on_no:
                on_no()
            return
        try:
            if hasattr(self, "root") and self.root and self.root.winfo_exists():
                if hasattr(self, "_active_modal_dialog") and self._active_modal_dialog:
                    try:
                        if self._active_modal_dialog.winfo_exists():
                            try:
                                self._active_modal_dialog.grab_release()
                            except Exception:
                                pass
                            self._active_modal_dialog.destroy()
                    except Exception:
                        pass
                    self._active_modal_dialog = None
                self._active_modal_dialog = SafeModalDialog(
                    self.root,
                    title,
                    message,
                    dialog_type="confirm",
                    theme=self._theme_dict(),
                    on_confirm=on_yes,
                    on_cancel=on_no
                )
        except Exception:
            pass

    def _setup_window(self):
        """Configures frameless window, centering, and dragging."""
        self.root.overrideredirect(True)

        # Center on screen
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = max(0, (sw - self.width) // 2)
        y = max(0, (sh - self.height) // 2)
        self.root.geometry(f"{self.width}x{self.height}+{x}+{y}")

        # Set Window Icons
        ico_path = get_resource_path("app_icon.ico")
        png_path = get_resource_path("app_icon.png")

        if os.path.isfile(ico_path):
            try:
                self.root.iconbitmap(ico_path)
            except Exception:
                pass

        if os.path.isfile(png_path):
            try:
                from PIL import ImageTk
                self._app_icon_photo = ImageTk.PhotoImage(file=png_path)
                self.root.iconphoto(True, self._app_icon_photo)
            except Exception:
                pass

        # Windows Taskbar Integration
        if IS_WINDOWS:
            self.root.update_idletasks()
            try:
                hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
                style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_STYLE)
                style |= (WS_MINIMIZEBOX | WS_SYSMENU)
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_STYLE, style)

                ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                ex_style = (ex_style & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style)

                # Set native taskbar and alt-tab icon via Win32 SendMessageW
                if os.path.isfile(ico_path):
                    try:
                        IMAGE_ICON = 1
                        LR_LOADFROMFILE = 0x00000010
                        WM_SETICON = 0x0080
                        ICON_SMALL = 0
                        ICON_BIG = 1

                        ctypes.windll.user32.LoadImageW.restype = ctypes.c_void_p
                        ctypes.windll.user32.LoadImageW.argtypes = [
                            ctypes.c_void_p,
                            ctypes.c_wchar_p,
                            ctypes.c_uint,
                            ctypes.c_int,
                            ctypes.c_int,
                            ctypes.c_uint
                        ]
                        ctypes.windll.user32.SendMessageW.argtypes = [
                            ctypes.c_void_p,
                            ctypes.c_uint,
                            ctypes.c_void_p,
                            ctypes.c_void_p
                        ]

                        sm_cx = ctypes.windll.user32.GetSystemMetrics(49) or 16
                        sm_cy = ctypes.windll.user32.GetSystemMetrics(50) or 16
                        hicon_sm = ctypes.windll.user32.LoadImageW(None, ico_path, IMAGE_ICON, sm_cx, sm_cy, LR_LOADFROMFILE)
                        if hicon_sm:
                            ctypes.windll.user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, hicon_sm)

                        lg_cx = ctypes.windll.user32.GetSystemMetrics(11) or 32
                        lg_cy = ctypes.windll.user32.GetSystemMetrics(12) or 32
                        hicon_lg = ctypes.windll.user32.LoadImageW(None, ico_path, IMAGE_ICON, lg_cx, lg_cy, LR_LOADFROMFILE)
                        if hicon_lg:
                            ctypes.windll.user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, hicon_lg)
                    except Exception:
                        pass

                if getattr(self, "_start_hidden", False):
                    try:
                        ctypes.windll.user32.ShowWindow(hwnd, SW_HIDE)
                    except Exception:
                        pass
                    try:
                        self.root.withdraw()
                    except Exception:
                        pass
                else:
                    ctypes.windll.user32.ShowWindow(hwnd, SW_SHOW)
            except Exception:
                pass

        if getattr(self, "_start_hidden", False):
            try:
                self.root.withdraw()
            except Exception:
                pass

        # Draggable title bar coordinate tracking (Root-relative to prevent jitter)
        self._drag_offset_x = 0
        self._drag_offset_y = 0

    def restore_window(self):
        """Restores and brings the main window to foreground if hidden or minimized."""
        self._start_hidden = False
        try:
            self.root.deiconify()
        except Exception:
            pass
        if IS_WINDOWS:
            try:
                hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
                ctypes.windll.user32.ShowWindow(hwnd, SW_RESTORE)
                ctypes.windll.user32.ShowWindow(hwnd, SW_SHOW)
                # Elevation pulse to overcome Windows OS focus-stealing prevention
                HWND_TOPMOST = -1
                HWND_NOTOPMOST = -2
                SWP_NOMOVE = 0x0002
                SWP_NOSIZE = 0x0001
                SWP_SHOWWINDOW = 0x0040
                ctypes.windll.user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
                ctypes.windll.user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
                ctypes.windll.user32.SetForegroundWindow(hwnd)
            except Exception:
                pass
        try:
            self.root.lift()
            self.root.attributes("-topmost", True)
            self._restore_idle_job = self.root.after_idle(lambda: self.root.attributes("-topmost", False) if hasattr(self, "root") and self.root else None)
            self.root.focus_force()
        except Exception:
            pass

    def _init_theme(self):
        """Palette and styling definitions."""
        self.c_bg = "#0f172a"          # Slate 900
        self.c_panel = "#1e293b"       # Slate 800
        self.c_panel_light = "#334155" # Slate 700
        self.c_border = "#475569"      # Slate 600
        self.c_accent = "#38bdf8"      # Sky 400
        self.c_accent_dark = "#0284c7" # Sky 600
        self.c_success = "#10b981"     # Emerald 500
        self.c_warning = "#f59e0b"     # Amber 500
        self.c_danger = "#ef4444"      # Red 500
        self.c_text_bright = "#f8fafc" # Slate 50
        self.c_text_muted = "#94a3b8"  # Slate 400
        self.c_input_bg = "#090d16"

        self.root.configure(bg=self.c_bg)

        # TTK Styles
        self.style = ttk.Style()
        self.style.theme_use("clam")

        # Treeview styling
        self.style.configure(
            "Custom.Treeview",
            background=self.c_panel,
            foreground=self.c_text_bright,
            fieldbackground=self.c_panel,
            borderwidth=0,
            rowheight=max(26, int(28 * getattr(self, "dpi_scale", 1.0))),
            font=("Segoe UI", 9)
        )
        self.style.configure(
            "Custom.Treeview.Heading",
            background=self.c_panel_light,
            foreground=self.c_accent,
            font=("Segoe UI", 9, "bold"),
            relief="flat"
        )
        self.style.map("Custom.Treeview.Heading", background=[('active', self.c_border)])
        self.style.map("Custom.Treeview", background=[('selected', self.c_accent_dark)])

        # Notebook tabs
        self.style.configure("Custom.TNotebook", background=self.c_panel, borderwidth=0)
        self.style.configure(
            "Custom.TNotebook.Tab",
            background=self.c_panel_light,
            foreground=self.c_text_bright,
            padding=[14, 5],
            font=("Segoe UI", 9, "bold")
        )
        self.style.map(
            "Custom.TNotebook.Tab",
            background=[("selected", self.c_accent_dark)],
            foreground=[("selected", self.c_text_bright)]
        )

    def _build_ui(self):
        """Constructs all GUI elements."""
        # Main Outer Border Frame
        main_border = tk.Frame(self.root, bg=self.c_border, padx=1, pady=1)
        main_border.pack(fill=tk.BOTH, expand=True)

        self.container = tk.Frame(main_border, bg=self.c_bg)
        self.container.pack(fill=tk.BOTH, expand=True)

        # 1. Custom Title Bar
        self._build_title_bar(self.container)

        # Content Area
        content = tk.Frame(self.container, bg=self.c_bg, padx=16, pady=12)
        content.pack(fill=tk.BOTH, expand=True)

        # 2. Input Section (URL & Destination Path)
        self._build_inputs_card(content)

        # 3. Download Options & Speed Limiter Section
        self._build_limiter_and_actions_card(content)

        # 4. Progress Bar & Metric Dashboard Cards
        self._build_metrics_card(content)

        # 5. Segmented Chunk Visualizer Bar (TDM Style)
        self._build_chunk_visualizer_card(content)

        # 6. Tabbed View (Chunk Table & Activity Log)
        self._build_tabs_card(content)

    def _build_title_bar(self, parent):
        """Constructs the custom dark draggable title bar."""
        tb_height = max(38, int(38 * getattr(self, "dpi_scale", 1.0)))
        title_bar = tk.Frame(parent, bg=self.c_panel, height=tb_height)
        title_bar.pack(fill=tk.X, side=tk.TOP)
        title_bar.pack_propagate(False)

        # Drag bindings using root coordinates for silky-smooth motion
        title_bar.bind("<ButtonPress-1>", self._on_title_press)
        title_bar.bind("<B1-Motion>", self._on_title_drag)

        # App Logo Icon in Title Bar
        png_path = get_resource_path("app_icon.png")
        if os.path.isfile(png_path):
            try:
                from PIL import Image, ImageTk
                icon_dim = max(20, int(20 * getattr(self, "dpi_scale", 1.0)))
                with Image.open(png_path) as im:
                    raw_icon = im.resize((icon_dim, icon_dim), Image.Resampling.LANCZOS)
                    self._title_icon_photo = ImageTk.PhotoImage(raw_icon)
                logo_lbl = tk.Label(title_bar, image=self._title_icon_photo, bg=self.c_panel)
                logo_lbl.pack(side=tk.LEFT, padx=(12, 4))
                logo_lbl.bind("<ButtonPress-1>", self._on_title_press)
                logo_lbl.bind("<B1-Motion>", self._on_title_drag)
            except Exception:
                pass

        # App Title
        self.title_lbl = tk.Label(
            title_bar,
            text=tr("app_header"),
            font=("Segoe UI", 10, "bold"),
            bg=self.c_panel,
            fg=self.c_accent
        )
        self.title_lbl.pack(side=tk.LEFT, padx=(6, 8))
        self.title_lbl.bind("<ButtonPress-1>", self._on_title_press)
        self.title_lbl.bind("<B1-Motion>", self._on_title_drag)

        self.subtitle_lbl = tk.Label(
            title_bar,
            text=tr("app_subtitle"),
            font=("Segoe UI", 8),
            bg=self.c_panel,
            fg=self.c_text_muted
        )
        self.subtitle_lbl.pack(side=tk.LEFT)
        self.subtitle_lbl.bind("<ButtonPress-1>", self._on_title_press)
        self.subtitle_lbl.bind("<B1-Motion>", self._on_title_drag)

        # Window Control Buttons (Minimize & Close)
        btn_close = tk.Label(
            title_bar,
            text="✕",
            font=("Segoe UI", 11, "bold"),
            bg=self.c_panel,
            fg=self.c_text_muted,
            width=4
        )
        btn_close.pack(side=tk.RIGHT, fill=tk.Y)
        btn_close.bind("<Enter>", lambda e: btn_close.configure(bg=self.c_danger, fg="white"))
        btn_close.bind("<Leave>", lambda e: btn_close.configure(bg=self.c_panel, fg=self.c_text_muted))
        btn_close.bind("<Button-1>", lambda e: self._on_close())

        btn_min = tk.Label(
            title_bar,
            text="—",
            font=("Segoe UI", 10, "bold"),
            bg=self.c_panel,
            fg=self.c_text_muted,
            width=4
        )
        btn_min.pack(side=tk.RIGHT, fill=tk.Y)
        btn_min.bind("<Enter>", lambda e: btn_min.configure(bg=self.c_panel_light, fg="white"))
        btn_min.bind("<Leave>", lambda e: btn_min.configure(bg=self.c_panel, fg=self.c_text_muted))
        btn_min.bind("<Button-1>", lambda e: self._on_minimize())

        self.btn_check_updates = tk.Button(
            title_bar,
            text=tr("btn_check_updates", "🔄 Check for Updates"),
            font=("Segoe UI", 8, "bold"),
            bg=self.c_panel_light,
            fg=self.c_accent,
            relief="flat",
            activebackground=self.c_accent_dark,
            activeforeground="white",
            cursor="hand2",
            padx=10,
            pady=2,
            command=self.check_for_updates_manual
        )
        self.btn_check_updates.pack(side=tk.RIGHT, padx=(6, 8), pady=6)
        self.btn_update = self.btn_check_updates

        # Prominent Language Toggle Button
        cur_lang = LocalizationManager.get_instance().get_language()
        toggle_txt = "🌐 English" if cur_lang == "ar" else "🌐 العربية"
        self.btn_lang_toggle = tk.Button(
            title_bar,
            text=toggle_txt,
            font=("Segoe UI", 8, "bold"),
            bg=self.c_panel_light,
            fg=self.c_accent,
            relief="flat",
            activebackground=self.c_accent_dark,
            activeforeground="white",
            cursor="hand2",
            padx=10,
            pady=2,
            command=self.toggle_language
        )
        self.btn_lang_toggle.pack(side=tk.RIGHT, padx=(4, 6), pady=6)
        ToolTip(self.btn_lang_toggle, "tip_lang_toggle")

        lbl_ver = tk.Label(
            title_bar,
            text=f"v{APP_VERSION}",
            font=("Consolas", 8, "bold"),
            bg=self.c_panel,
            fg=self.c_success
        )
        lbl_ver.pack(side=tk.RIGHT, padx=(4, 4))
        lbl_ver.bind("<ButtonPress-1>", self._on_title_press)
        lbl_ver.bind("<B1-Motion>", self._on_title_drag)

        # Separator Line
        sep = tk.Frame(parent, bg=self.c_panel_light, height=1)
        sep.pack(fill=tk.X, side=tk.TOP)

    def _on_title_press(self, event):
        self._drag_offset_x = event.x_root - self.root.winfo_x()
        self._drag_offset_y = event.y_root - self.root.winfo_y()

    def _on_title_drag(self, event):
        x = event.x_root - self._drag_offset_x
        y = event.y_root - self._drag_offset_y
        self.root.geometry(f"+{x}+{y}")

    def _on_minimize(self):
        """Minimize frameless window smoothly without TclError."""
        if IS_WINDOWS:
            try:
                hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
                ctypes.windll.user32.ShowWindow(hwnd, SW_MINIMIZE)
                return
            except Exception:
                pass
        try:
            self.root.overrideredirect(False)
            self.root.iconify()
        except Exception:
            pass

    def _on_root_destroyed(self, event):
        if event.widget == self.root:
            self._cleanup_resources()

    def _cleanup_resources(self):
        self._closing = True
        try:
            LocalizationManager.get_instance().unregister_observer(self._update_ui_language)
        except Exception:
            pass
        if hasattr(self, "_yt_cancel_event") and self._yt_cancel_event:
            try:
                self._yt_cancel_event.set()
            except Exception:
                pass
        if hasattr(self, "engine") and self.engine:
            try:
                for cb_attr in ("on_progress", "on_chunk_update", "on_log", "on_complete", "on_error"):
                    if hasattr(self.engine, cb_attr):
                        setattr(self.engine, cb_attr, None)
                if getattr(self.engine, "is_running", False):
                    if hasattr(self.engine, "safe_shutdown"):
                        self.engine.safe_shutdown()
                    else:
                        self.engine.cancel()
            except Exception:
                pass
        if hasattr(self, "tray_manager") and self.tray_manager:
            try:
                self.tray_manager.stop()
            except Exception:
                pass
        if hasattr(self, "_clipboard_job") and self._clipboard_job:
            try:
                self.root.after_cancel(self._clipboard_job)
            except Exception:
                pass
            self._clipboard_job = None
        if hasattr(self, "_refresh_job") and self._refresh_job:
            try:
                self.root.after_cancel(self._refresh_job)
            except Exception:
                pass
            self._refresh_job = None
        if hasattr(self, "_bg_notify_job") and self._bg_notify_job:
            try:
                self.root.after_cancel(self._bg_notify_job)
            except Exception:
                pass
            self._bg_notify_job = None
        if hasattr(self, "_update_check_job") and self._update_check_job:
            try:
                self.root.after_cancel(self._update_check_job)
            except Exception:
                pass
            self._update_check_job = None
        if hasattr(self, "_log_jobs") and self._log_jobs:
            for j in list(self._log_jobs):
                try:
                    self.root.after_cancel(j)
                except Exception:
                    pass
            self._log_jobs.clear()
        if hasattr(self, "bridge_server") and self.bridge_server:
            try:
                self.bridge_server.stop()
            except Exception:
                pass
            self.bridge_server = None
        if hasattr(self, "_confirm_modal") and self._confirm_modal:
            try:
                if self._confirm_modal.winfo_exists():
                    self._confirm_modal.destroy()
            except Exception:
                pass
            self._confirm_modal = None
        if hasattr(self, "_quality_modal") and self._quality_modal:
            try:
                if self._quality_modal.winfo_exists():
                    self._quality_modal.destroy()
            except Exception:
                pass
            self._quality_modal = None
        if hasattr(self, "_refresh_modal") and self._refresh_modal:
            try:
                if self._refresh_modal.winfo_exists():
                    self._refresh_modal.destroy()
            except Exception:
                pass
            self._refresh_modal = None
        if hasattr(self, "_active_modal_dialog") and self._active_modal_dialog:
            try:
                if self._active_modal_dialog.winfo_exists():
                    self._active_modal_dialog.destroy()
            except Exception:
                pass
            self._active_modal_dialog = None
        if hasattr(self, "_update_modal") and self._update_modal:
            try:
                if hasattr(self._update_modal, "_cancel_event"):
                    self._update_modal._cancel_event.set()
                if self._update_modal.winfo_exists():
                    self._update_modal.destroy()
            except Exception:
                pass
            self._update_modal = None
        self._close_fetching_toast()
        self._dismiss_bg_toast()
        if hasattr(self, "style") and self.style is not None:
            _detach_photo_tk(self.style)
            self.style = None
        for var_name in ("conn_var", "limit_preset_var"):
            if hasattr(self, var_name):
                _detach_photo_tk(getattr(self, var_name))
        for photo_attr in ("_app_icon_photo", "_title_icon_photo"):
            if hasattr(self, photo_attr):
                _detach_photo_tk(getattr(self, photo_attr))
                setattr(self, photo_attr, None)
        if hasattr(self, "_restore_idle_job") and self._restore_idle_job:
            try:
                self.root.after_cancel(self._restore_idle_job)
            except Exception:
                pass
            self._restore_idle_job = None
        if hasattr(self, "_browser_integration_dlg") and self._browser_integration_dlg:
            try:
                if hasattr(self._browser_integration_dlg, "_browser_icon_photo"):
                    _detach_photo_tk(self._browser_integration_dlg._browser_icon_photo)
                    self._browser_integration_dlg._browser_icon_photo = None
                if self._browser_integration_dlg.winfo_exists():
                    self._browser_integration_dlg.destroy()
            except Exception:
                pass
            self._browser_integration_dlg = None
        self._update_dlg_startup_ui = None
        self._update_dlg_tray_ui = None
        try:
            self.root.update_idletasks()
        except Exception:
            pass

    def _on_close(self, force_exit: bool = False):
        """
        Handles the window close button '✕' or WM_DELETE_WINDOW protocol.
        If minimize_to_tray is True (default) and force_exit is False,
        minimizes/hides the window to the Windows System Tray while keeping
        the clipboard sniffer and loopback server running.
        Otherwise, executes a clean application exit.
        """
        if not force_exit and getattr(self, "minimize_to_tray", True):
            self.minimize_to_tray_action()
            return

        self.exit_completely()

    def minimize_to_tray_action(self):
        """Hides the main window to the Windows System Tray while keeping background services alive."""
        try:
            self.root.withdraw()
        except Exception:
            pass

        if IS_WINDOWS:
            try:
                hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
                ctypes.windll.user32.ShowWindow(hwnd, SW_HIDE)
            except Exception:
                pass

        if hasattr(self, "tray_manager") and self.tray_manager:
            try:
                self.tray_manager.start()
            except Exception:
                pass

        self.log("[SYSTEM TRAY] Application minimized to system tray. Clipboard sniffer & browser bridge remain active.")

    def exit_completely(self):
        """Cleanly terminates the application, background threads, servers, and system tray icons."""
        self._closing = True
        if hasattr(self, "_yt_cancel_event"):
            self._yt_cancel_event.set()
        if hasattr(self, "_quality_modal") and self._quality_modal:
            try:
                if self._quality_modal.winfo_exists():
                    try:
                        self._quality_modal.grab_release()
                    except Exception:
                        pass
                    self._quality_modal.destroy()
            except Exception:
                pass
            self._quality_modal = None
        if hasattr(self, "_confirm_modal") and self._confirm_modal:
            try:
                if self._confirm_modal.winfo_exists():
                    try:
                        self._confirm_modal.grab_release()
                    except Exception:
                        pass
                    self._confirm_modal.destroy()
            except Exception:
                pass
            self._confirm_modal = None
        if hasattr(self, "_update_modal") and self._update_modal:
            try:
                if hasattr(self._update_modal, "_cancel_event"):
                    self._update_modal._cancel_event.set()
                if self._update_modal.winfo_exists():
                    self._update_modal.destroy()
            except Exception:
                pass
            self._update_modal = None
        if hasattr(self, "_active_modal_dialog") and self._active_modal_dialog:
            try:
                if self._active_modal_dialog.winfo_exists():
                    try:
                        self._active_modal_dialog.grab_release()
                    except Exception:
                        pass
                    self._active_modal_dialog.destroy()
            except Exception:
                pass
            self._active_modal_dialog = None

        def _do_exit():
            if self.engine and self.engine.is_running:
                try:
                    dl_url = (self.engine.url if self.engine and getattr(self.engine, "url", None) else self.entry_url.get()).strip()
                    dl_dest = (self.engine.dest_path if self.engine and getattr(self.engine, "dest_path", None) else self.entry_dest.get()).strip()
                    if dl_url and dl_dest and hasattr(self, "history_manager") and self.history_manager:
                        self.history_manager.add_or_update_entry(
                            url=dl_url,
                            file_path=dl_dest,
                            size_bytes=getattr(self.engine, "total_size", 0) or 0,
                            status="Paused",
                            elapsed_sec=0.0
                        )
                except Exception:
                    pass
                try:
                    self.engine.safe_shutdown()
                except Exception:
                    pass
            self._cleanup_resources()
            try:
                if hasattr(self, "root") and self.root and self.root.winfo_exists():
                    self.root.destroy()
            except Exception:
                pass

        if self.engine and self.engine.is_running:
            self.restore_window()
            self.ask_safe_yesno(
                tr("dialog_exit_title", "Exit Confirmation"),
                tr("dialog_exit_msg", "A download is currently active. Stop and exit completely?"),
                on_yes=_do_exit
            )
            return
        _do_exit()

    def _build_inputs_card(self, parent):
        """URL & File Destination inputs."""
        card = tk.Frame(parent, bg=self.c_panel, padx=14, pady=10, relief="flat", highlightbackground=self.c_border, highlightthickness=1)
        card.pack(fill=tk.X, pady=(0, 10))

        # URL Row
        url_row = tk.Frame(card, bg=self.c_panel)
        url_row.pack(fill=tk.X, pady=2)

        self.lbl_url = tk.Label(url_row, text=tr("lbl_url"), font=("Segoe UI", 9, "bold"), bg=self.c_panel, fg=self.c_text_bright, width=13, anchor="w")
        self.lbl_url.pack(side=tk.LEFT)

        default_url = "https://speed.cloudflare.com/__down?bytes=50000000"  # 50MB benchmark file
        self.entry_url = tk.Entry(url_row, font=("Segoe UI", 9), bg=self.c_input_bg, fg=self.c_text_bright, insertbackground=self.c_accent, relief="flat")
        self.entry_url.insert(0, default_url)
        self.entry_url.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 8), ipady=3)
        self.entry_url.bind("<KeyRelease>", lambda e: self._on_url_change())

        self.btn_paste = tk.Button(url_row, text=tr("btn_paste"), font=("Segoe UI", 8), bg=self.c_panel_light, fg=self.c_text_bright, relief="flat", activebackground=self.c_accent_dark, cursor="hand2", command=self._paste_url)
        self.btn_paste.pack(side=tk.RIGHT)

        self.btn_refresh_url = tk.Button(url_row, text=tr("btn_refresh_url"), font=("Segoe UI", 8), bg=self.c_panel_light, fg=self.c_accent, relief="flat", activebackground=self.c_accent_dark, cursor="hand2", command=self._open_refresh_link_dialog)
        self.btn_refresh_url.pack(side=tk.RIGHT, padx=(0, 6))

        # Destination Row
        dest_row = tk.Frame(card, bg=self.c_panel)
        dest_row.pack(fill=tk.X, pady=(6, 2))

        self.lbl_dest = tk.Label(dest_row, text=tr("lbl_dest"), font=("Segoe UI", 9, "bold"), bg=self.c_panel, fg=self.c_text_bright, width=13, anchor="w")
        self.lbl_dest.pack(side=tk.LEFT)

        downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
        default_fn = "cloudflare_50mb.bin"
        if getattr(self, "auto_categorize_folders", True):
            default_dest = resolve_categorized_path(downloads_dir, default_fn, auto_categorize=True)
        else:
            default_dest = os.path.join(downloads_dir, default_fn)
        self.entry_dest = tk.Entry(dest_row, font=("Segoe UI", 9), bg=self.c_input_bg, fg=self.c_text_bright, insertbackground=self.c_accent, relief="flat")
        self.entry_dest.insert(0, default_dest)
        self.entry_dest.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 8), ipady=3)

        self.btn_browse = tk.Button(dest_row, text=tr("btn_browse"), font=("Segoe UI", 8), bg=self.c_panel_light, fg=self.c_text_bright, relief="flat", activebackground=self.c_accent_dark, cursor="hand2", command=self._browse_destination)
        self.btn_browse.pack(side=tk.RIGHT)

    def _paste_url(self):
        try:
            clipboard = self.root.clipboard_get()
            if clipboard:
                self.entry_url.delete(0, tk.END)
                self.entry_url.insert(0, clipboard.strip())
                self._on_url_change()
        except Exception:
            pass

    def _browse_destination(self):
        path = filedialog.asksaveasfilename(
            title="Select Destination File",
            initialdir=os.path.dirname(self.entry_dest.get()) or os.path.expanduser("~"),
            initialfile=os.path.basename(self.entry_dest.get()) or "download.bin"
        )
        if path:
            self.entry_dest.delete(0, tk.END)
            self.entry_dest.insert(0, path)

    def _is_downloads_or_category_subfolder(self, dest_dir: str, downloads_dir: str) -> bool:
        """Checks if dest_dir is either the base downloads_dir or one of its category subfolders."""
        if not dest_dir or not downloads_dir:
            return False
        norm_dest = os.path.normcase(os.path.abspath(dest_dir))
        norm_dl = os.path.normcase(os.path.abspath(downloads_dir))
        if norm_dest == norm_dl:
            return True
        if os.path.dirname(norm_dest) == norm_dl:
            base = os.path.basename(norm_dest)
            subfolders_lower = {s.lower() for s in CATEGORY_SUBFOLDERS.values()}
            if base in subfolders_lower:
                return True
        return False

    def _on_url_change(self, *args):
        """Updates default destination path based on the current URL if not actively transferring."""
        if hasattr(self, "engine") and self.engine and getattr(self.engine, "is_running", False):
            return
        if not hasattr(self, "entry_url") or not hasattr(self, "entry_dest"):
            return
        url = self.entry_url.get().strip()
        if not url:
            return
        fn = derive_download_filename(url)
        cur_dest = self.entry_dest.get().strip()
        downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
        dest_dir = os.path.dirname(cur_dest) if cur_dest else downloads_dir
        if not os.path.isdir(dest_dir):
            dest_dir = downloads_dir
        if getattr(self, "auto_categorize_folders", True) and self._is_downloads_or_category_subfolder(dest_dir, downloads_dir):
            new_dest = resolve_categorized_path(downloads_dir, fn, auto_categorize=True)
        else:
            new_dest = os.path.join(dest_dir, fn)
        self.entry_dest.delete(0, tk.END)
        self.entry_dest.insert(0, new_dest)

    def _build_limiter_and_actions_card(self, parent):
        """Configuration options: Speed Limiter (Presets + Custom + Dynamic Slider) & Action Buttons."""
        card = tk.Frame(parent, bg=self.c_panel, padx=14, pady=10, relief="flat", highlightbackground=self.c_border, highlightthickness=1)
        card.pack(fill=tk.X, pady=(0, 10))

        # Row 1: Max Connections + Bandwidth Presets + Custom Entry
        row1 = tk.Frame(card, bg=self.c_panel)
        row1.pack(fill=tk.X, pady=2)

        # Max Connections
        self.lbl_conn = tk.Label(row1, text=tr("lbl_threads"), font=("Segoe UI", 9, "bold"), bg=self.c_panel, fg=self.c_text_bright)
        self.lbl_conn.pack(side=tk.LEFT)

        self.conn_var = tk.StringVar(value="8")
        conn_combo = ttk.Combobox(row1, textvariable=self.conn_var, values=["1", "2", "4", "8", "16", "24", "32"], width=4, state="readonly")
        conn_combo.pack(side=tk.LEFT, padx=(4, 16))

        # Speed Limiter controls
        self.lbl_limit = tk.Label(row1, text=tr("lbl_speed_limiter"), font=("Segoe UI", 9, "bold"), bg=self.c_panel, fg=self.c_accent)
        self.lbl_limit.pack(side=tk.LEFT)

        self.limit_preset_var = tk.StringVar(value="Unlimited")
        self.preset_options = [
            "Unlimited",
            "128 KB/s",
            "256 KB/s",
            "512 KB/s",
            "1.0 MB/s",
            "2.0 MB/s",
            "5.0 MB/s",
            "10.0 MB/s",
            "20.0 MB/s",
            "Custom"
        ]
        preset_combo = ttk.Combobox(row1, textvariable=self.limit_preset_var, values=self.preset_options, width=12, state="readonly")
        preset_combo.pack(side=tk.LEFT, padx=(4, 8))
        preset_combo.bind("<<ComboboxSelected>>", self._on_preset_selected)

        # Custom entry
        self.lbl_custom = tk.Label(row1, text=tr("lbl_custom_speed"), font=("Segoe UI", 8), bg=self.c_panel, fg=self.c_text_muted)
        self.lbl_custom.pack(side=tk.LEFT)

        self.entry_custom_speed = tk.Entry(row1, font=("Segoe UI", 9), width=7, bg=self.c_input_bg, fg=self.c_text_bright, insertbackground=self.c_accent, relief="flat")
        self.entry_custom_speed.insert(0, "0")
        self.entry_custom_speed.pack(side=tk.LEFT, padx=(4, 6), ipady=1)
        self.entry_custom_speed.bind("<Return>", lambda e: self._apply_speed_limit())

        self.btn_apply_speed = tk.Button(row1, text=tr("btn_apply_limit"), font=("Segoe UI", 8, "bold"), bg=self.c_accent_dark, fg="white", relief="flat", activebackground=self.c_accent, cursor="hand2", command=self._apply_speed_limit)
        self.btn_apply_speed.pack(side=tk.LEFT, padx=(2, 16))

        # Active limit status indicator
        self.lbl_active_limit = tk.Label(row1, text=tr("lbl_current_unlimited", "● Current: Unlimited"), font=("Segoe UI", 8, "bold"), bg=self.c_panel, fg=self.c_success)
        self.lbl_active_limit.pack(side=tk.LEFT)

        # Row 2: Dynamic Rate Limiter Slider (0 KB/s to 20,480 KB/s)
        row_slider = tk.Frame(card, bg=self.c_panel)
        row_slider.pack(fill=tk.X, pady=(6, 2))

        self.lbl_slider_title = tk.Label(row_slider, text=tr("lbl_live_throttle_slider"), font=("Segoe UI", 8, "bold"), bg=self.c_panel, fg=self.c_text_muted)
        self.lbl_slider_title.pack(side=tk.LEFT, padx=(0, 8))

        slider_len = max(20, int(22 * getattr(self, "dpi_scale", 1.0)))
        slider_w = max(14, int(16 * getattr(self, "dpi_scale", 1.0)))
        self.slider_speed = tk.Scale(
            row_slider,
            from_=0,
            to=20480,  # 0 to 20 MB/s in KB/s
            orient=tk.HORIZONTAL,
            showvalue=False,
            bg=self.c_panel,
            troughcolor=self.c_input_bg,
            activebackground=self.c_accent,
            highlightthickness=0,
            relief="flat",
            sliderlength=slider_len,
            width=slider_w,
            command=self._on_slider_moved
        )
        self.slider_speed.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        ToolTip(self.slider_speed, "tip_speed_slider")

        self.lbl_slider_val = tk.Label(row_slider, text=f"{tr('lbl_unlimited', 'Unlimited')} (0 KB/s)", font=("Segoe UI", 8, "bold"), bg=self.c_panel, fg=self.c_accent, width=18, anchor="w")
        self.lbl_slider_val.pack(side=tk.RIGHT)

        # Row 3: Action Buttons (Start, Pause, Cancel)
        row2 = tk.Frame(card, bg=self.c_panel)
        row2.pack(fill=tk.X, pady=(10, 2))

        self.btn_start = tk.Button(
            row2,
            text=tr("btn_start", "▶ Start Download"),
            font=("Segoe UI", 9, "bold"),
            bg=self.c_success,
            fg="white",
            relief="flat",
            activebackground="#059669",
            cursor="hand2",
            padx=14,
            pady=4,
            command=self._on_start_download
        )
        self.btn_start.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_pause = tk.Button(
            row2,
            text=tr("btn_pause", "⏸ Pause"),
            font=("Segoe UI", 9, "bold"),
            bg=self.c_panel_light,
            fg=self.c_text_bright,
            relief="flat",
            activebackground=self.c_border,
            cursor="hand2",
            padx=14,
            pady=4,
            state="disabled",
            command=self._on_pause_resume
        )
        self.btn_pause.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_cancel = tk.Button(
            row2,
            text=tr("btn_cancel", "⏹ Cancel"),
            font=("Segoe UI", 9, "bold"),
            bg=self.c_danger,
            fg="white",
            relief="flat",
            activebackground="#dc2626",
            cursor="hand2",
            padx=14,
            pady=4,
            state="disabled",
            command=self._on_cancel_download
        )
        self.btn_cancel.pack(side=tk.LEFT)

        self.btn_refresh_link = tk.Button(
            row2,
            text=tr("btn_refresh_url", "🔄 Refresh Link"),
            font=("Segoe UI", 9, "bold"),
            bg=self.c_panel_light,
            fg=self.c_accent,
            relief="flat",
            activebackground=self.c_accent_dark,
            activeforeground="white",
            cursor="hand2",
            padx=12,
            pady=4,
            command=self._open_refresh_link_dialog
        )
        self.btn_refresh_link.pack(side=tk.LEFT, padx=(8, 0))

        self.btn_browser = tk.Button(
            row2,
            text=tr("btn_browser", "🌐 Settings & Integration"),
            font=("Segoe UI", 9, "bold"),
            bg=self.c_panel_light,
            fg=self.c_accent,
            relief="flat",
            activebackground=self.c_accent_dark,
            cursor="hand2",
            padx=12,
            pady=4,
            command=self._open_browser_integration_dialog
        )
        self.btn_browser.pack(side=tk.RIGHT)

        self.btn_clipboard_sniffer = tk.Button(
            row2,
            text="📋 Sniffer: Active",
            font=("Segoe UI", 9, "bold"),
            bg=self.c_panel_light,
            fg=self.c_success,
            relief="flat",
            activebackground=self.c_accent_dark,
            activeforeground="white",
            cursor="hand2",
            padx=12,
            pady=4,
            command=self.toggle_clipboard_sniffer
        )
        self.btn_clipboard_sniffer.pack(side=tk.RIGHT, padx=(0, 8))
        ToolTip(self.btn_clipboard_sniffer, "tip_sniffer")

        self.btn_startup = tk.Button(
            row2,
            text=tr("btn_startup_off", "🚀 Boot: OFF"),
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            activebackground=self.c_accent_dark,
            activeforeground="white",
            cursor="hand2",
            padx=12,
            pady=4,
            command=self.toggle_startup_setting
        )
        self.btn_startup.pack(side=tk.RIGHT, padx=(0, 8))
        ToolTip(self.btn_startup, "tip_startup")
        self._update_startup_btn()

        self.btn_cookies = tk.Button(
            row2,
            text=self._get_cookies_btn_text(),
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            activebackground=self.c_accent_dark,
            activeforeground="white",
            cursor="hand2",
            padx=12,
            pady=4,
            command=self.cycle_cookies_setting
        )
        self.btn_cookies.pack(side=tk.RIGHT, padx=(0, 8))
        self._update_cookies_btn()

        self.btn_auto_cat = tk.Button(
            row2,
            text="📁 Auto-Sort: ON" if self.auto_categorize_folders else "📁 Auto-Sort: OFF",
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            bg=self.c_panel_light if self.auto_categorize_folders else self.c_panel,
            fg=self.c_success if self.auto_categorize_folders else self.c_text_muted,
            activebackground=self.c_accent_dark,
            activeforeground="white",
            cursor="hand2",
            padx=12,
            pady=4,
            command=self.toggle_auto_categorize
        )
        self.btn_auto_cat.pack(side=tk.RIGHT, padx=(0, 8))
        ToolTip(self.btn_auto_cat, "tip_auto_cat")
        self._update_auto_cat_btn()

    def toggle_auto_categorize(self):
        """Toggles automatic categorization into subfolders (Videos, Music, etc.)."""
        self.auto_categorize_folders = not self.auto_categorize_folders
        set_setting("auto_categorize_folders", self.auto_categorize_folders)
        self._update_auto_cat_btn()
        if not (self.engine and getattr(self.engine, "is_running", False)):
            cur_dest = self.entry_dest.get().strip() if hasattr(self, "entry_dest") else ""
            if cur_dest:
                fn = os.path.basename(cur_dest)
                downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
                dest_dir = os.path.dirname(cur_dest)
                if self._is_downloads_or_category_subfolder(dest_dir, downloads_dir):
                    new_dest = resolve_categorized_path(downloads_dir, fn, auto_categorize=self.auto_categorize_folders)
                    self.entry_dest.delete(0, tk.END)
                    self.entry_dest.insert(0, new_dest)

    def _update_auto_cat_btn(self):
        if not hasattr(self, "btn_auto_cat") or not self.btn_auto_cat.winfo_exists():
            return
        if self.auto_categorize_folders:
            self.btn_auto_cat.configure(
                text=tr("btn_auto_cat_on"),
                fg=self.c_success,
                bg=self.c_panel_light
            )
        else:
            self.btn_auto_cat.configure(
                text=tr("btn_auto_cat_off"),
                fg=self.c_text_muted,
                bg=self.c_panel
            )

    def _on_slider_moved(self, val_str):
        """Dynamic slider movement throttles engine in real-time."""
        try:
            kb_val = int(float(val_str))
        except ValueError:
            return

        if kb_val <= 0:
            self.lbl_slider_val.configure(text=f"{tr('lbl_unlimited', 'Unlimited')} (0 KB/s)", fg=self.c_success)
            self.lbl_active_limit.configure(text=tr("lbl_current_unlimited", "● Current: Unlimited"), fg=self.c_success)
            self.limit_preset_var.set("Unlimited")
            bytes_sec = 0.0
        else:
            if kb_val >= 1024:
                disp = f"{kb_val / 1024.0:.1f} MB/s ({kb_val:,} KB/s)"
                active_disp = tr("lbl_current_limit", "● Current: {limit}").format(limit=f"{kb_val / 1024.0:.2f} MB/s")
            else:
                disp = f"{kb_val} KB/s"
                active_disp = tr("lbl_current_limit", "● Current: {limit}").format(limit=f"{kb_val} KB/s")
            self.lbl_slider_val.configure(text=disp, fg=self.c_warning)
            self.lbl_active_limit.configure(text=active_disp, fg=self.c_warning)
            bytes_sec = kb_val * 1024.0

        self.speed_limit = bytes_sec

        # Sync entry box without triggering infinite callback
        self.entry_custom_speed.delete(0, tk.END)
        self.entry_custom_speed.insert(0, str(kb_val))

        if self.engine and self.engine.is_running:
            self.engine.set_speed_limit(bytes_sec)

    def _on_preset_selected(self, event=None):
        val = self.limit_preset_var.get()
        mapping = {
            "Unlimited": 0,
            "128 KB/s": 128,
            "256 KB/s": 256,
            "512 KB/s": 512,
            "1.0 MB/s": 1024,
            "2.0 MB/s": 2048,
            "5.0 MB/s": 5120,
            "10.0 MB/s": 10240,
            "20.0 MB/s": 20480,
        }
        if val in mapping:
            target_kb = mapping[val]
            self.entry_custom_speed.delete(0, tk.END)
            self.entry_custom_speed.insert(0, str(target_kb))
            self.slider_speed.set(target_kb)
            self._apply_speed_limit()
        elif val == "Custom":
            self.entry_custom_speed.focus_set()

    def _apply_speed_limit(self):
        """Applies speed limit dynamically to active engine."""
        try:
            kb_val = float(self.entry_custom_speed.get().strip())
        except ValueError:
            self.show_safe_warning("Invalid Speed", "Please enter a valid numeric speed limit in KB/s.")
            return

        kb_val = max(0.0, kb_val)
        bytes_sec = kb_val * 1024.0 if kb_val > 0 else 0.0
        self.speed_limit = bytes_sec

        if bytes_sec <= 0:
            self.lbl_active_limit.configure(text=tr("lbl_current_unlimited", "● Current: Unlimited"), fg=self.c_success)
            self.lbl_slider_val.configure(text=f"{tr('lbl_unlimited', 'Unlimited')} (0 KB/s)", fg=self.c_success)
            self.limit_preset_var.set("Unlimited")
            self.slider_speed.set(0)
        else:
            if bytes_sec >= 1024 * 1024:
                disp = f"{bytes_sec / (1024*1024):.2f} MB/s"
            else:
                disp = f"{bytes_sec / 1024:.0f} KB/s"
            self.lbl_active_limit.configure(text=tr("lbl_current_limit", "● Current: {limit}").format(limit=disp), fg=self.c_warning)
            self.lbl_slider_val.configure(text=disp, fg=self.c_warning)
            self.slider_speed.set(min(20480, int(kb_val)))

        if self.engine and self.engine.is_running:
            self.engine.set_speed_limit(bytes_sec)

    def _build_metrics_card(self, parent):
        """Overall progress bar and 4 real-time metric cards."""
        card = tk.Frame(parent, bg=self.c_panel, padx=14, pady=10, relief="flat", highlightbackground=self.c_border, highlightthickness=1)
        card.pack(fill=tk.X, pady=(0, 10))

        # Main Progress Canvas
        prog_height = max(22, int(24 * getattr(self, "dpi_scale", 1.0)))
        self.canvas_prog = tk.Canvas(card, height=prog_height, bg=self.c_input_bg, highlightthickness=0)
        self.canvas_prog.pack(fill=tk.X, pady=(0, 10))
        self._draw_main_progress(0.0)

        # 4 Metric Cards Grid
        grid_frame = tk.Frame(card, bg=self.c_panel)
        grid_frame.pack(fill=tk.X)
        for i in range(4):
            grid_frame.columnconfigure(i, weight=1, uniform="metric")

        # 1. Download Speed
        self.card_speed = self._create_metric_box(grid_frame, 0, tr("metric_speed"), "0.0 KB/s")
        self.lbl_t_speed = self.card_speed.master.lbl_t
        # 2. Downloaded / Total
        self.card_size = self._create_metric_box(grid_frame, 1, tr("metric_total_size"), "0 B / 0 B (0%)")
        self.lbl_t_size = self.card_size.master.lbl_t
        # 3. ETA
        self.card_eta = self._create_metric_box(grid_frame, 2, tr("metric_eta"), "--:--:--")
        self.lbl_t_eta = self.card_eta.master.lbl_t
        # 4. Connections
        self.card_threads = self._create_metric_box(grid_frame, 3, tr("metric_threads"), "0 / 0 Threads")
        self.lbl_t_threads = self.card_threads.master.lbl_t

    def _create_metric_box(self, parent, col, title, initial_value):
        frame = tk.Frame(parent, bg=self.c_bg, padx=10, pady=8, highlightbackground=self.c_border, highlightthickness=1)
        frame.grid(row=0, column=col, padx=4, sticky="nsew")

        lbl_t = tk.Label(frame, text=title, font=("Segoe UI", 8, "bold"), bg=self.c_bg, fg=self.c_text_muted)
        lbl_t.pack(anchor="w")
        frame.lbl_t = lbl_t

        lbl_v = tk.Label(frame, text=initial_value, font=("Segoe UI", 11, "bold"), bg=self.c_bg, fg=self.c_text_bright)
        lbl_v.pack(anchor="w", pady=(2, 0))
        frame.lbl_v = lbl_v
        return lbl_v

    def _draw_main_progress(self, pct: float):
        self.canvas_prog.delete("all")
        w = self.canvas_prog.winfo_width()
        if w <= 1:
            w = self.width - 64
        h = self.canvas_prog.winfo_height() or max(22, int(24 * getattr(self, "dpi_scale", 1.0)))

        # Background track
        self.canvas_prog.create_rectangle(0, 0, w, h, fill=self.c_input_bg, outline=self.c_border)

        # Progress fill
        fill_w = max(0.0, min(float(w), (pct / 100.0) * float(w)))
        if fill_w > 0:
            self.canvas_prog.create_rectangle(0, 0, fill_w, h, fill=self.c_accent_dark, outline="")
            self.canvas_prog.create_line(0, 1, fill_w, 1, fill=self.c_accent)

        # Percentage text overlay
        text_color = "white" if fill_w > (w * 0.45) else self.c_text_bright
        self.canvas_prog.create_text(w // 2, h // 2, text=f"{pct:.1f}%", font=("Segoe UI", 9, "bold"), fill=text_color)

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
        self.canvas_chunks.pack(fill=tk.X)
        self._draw_chunk_segments([])

    def _draw_chunk_segments(self, chunks: List[DownloadChunk]):
        self.canvas_chunks.delete("all")
        w = self.canvas_chunks.winfo_width()
        if w <= 1:
            w = self.width - 64
        h = self.canvas_chunks.winfo_height() or max(30, int(32 * getattr(self, "dpi_scale", 1.0)))

        # Background track
        self.canvas_chunks.create_rectangle(0, 0, w, h, fill=self.c_input_bg, outline=self.c_border)

        if not chunks or not self.engine or self.engine.total_size <= 0:
            msg = "Waiting to start..." if not self.engine else "Single-stream / unknown size"
            self.canvas_chunks.create_text(w // 2, h // 2, text=msg, font=("Segoe UI", 8), fill=self.c_text_muted)
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
            self.canvas_chunks.create_rectangle(start_x, 2, end_x, h - 2, fill="#1e293b", outline="")

            # Segment downloaded portion
            if done_x > start_x:
                fill_color = self.c_success if status == "completed" else self.c_accent
                self.canvas_chunks.create_rectangle(start_x, 2, done_x, h - 2, fill=fill_color, outline="")

            # Chunk divider line
            self.canvas_chunks.create_line(end_x, 0, end_x, h, fill=self.c_border, width=1)

            # Chunk label if wide enough
            if chunk_w > 36:
                mid_x = (start_x + end_x) / 2
                self.canvas_chunks.create_text(mid_x, h // 2, text=f"#{c.chunk_id}", font=("Segoe UI", 8, "bold"), fill="white")

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

    def _build_history_context_menu(self):
        """Constructs right-click context menu for download history."""
        self.history_context_menu = tk.Menu(
            self.tree_history,
            tearoff=0,
            bg=self.c_panel,
            fg=self.c_text_bright,
            activebackground=self.c_accent_dark,
            activeforeground="white",
            relief="flat",
            bd=1
        )
        self.history_context_menu.add_command(
            label=tr("ctx_open_file", "📂 Open File"),
            command=self._history_open_selected_file
        )
        self.history_context_menu.add_command(
            label=tr("ctx_open_folder", "📁 Open Containing Folder"),
            command=self._history_open_selected_folder
        )
        self.history_context_menu.add_separator()
        self.history_context_menu.add_command(
            label=tr("ctx_copy_url", "📋 Copy URL"),
            command=self._history_copy_selected_url
        )
        self.history_context_menu.add_command(
            label=tr("ctx_resume_retry", "🔄 Resume / Retry"),
            command=self._history_redownload_selected
        )
        self.history_context_menu.add_separator()
        self.history_context_menu.add_command(
            label=tr("ctx_remove_history", "🗑️ Remove from History"),
            command=self._history_remove_selected
        )

    def _show_history_context_menu(self, event):
        """Displays right-click context menu on history treeview."""
        self._build_history_context_menu()
        try:
            iid = self.tree_history.identify_row(event.y)
            if iid:
                self.tree_history.selection_set(iid)
                self.tree_history.focus(iid)
        except Exception:
            pass
        try:
            self.history_context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                self.history_context_menu.grab_release()
            except Exception:
                pass

    def _refresh_history_table(self):
        """Refreshes tree_history items according to selected filter."""
        if threading.current_thread() != threading.main_thread():
            if hasattr(self, "root") and self.root and self.root.winfo_exists():
                try:
                    self.root.after(0, self._refresh_history_table)
                except Exception:
                    pass
            return

        if not hasattr(self, "tree_history") or not hasattr(self, "history_manager"):
            return
        cat_filter = "All Categories"
        if hasattr(self, "combo_history_filter"):
            cat_filter = self.combo_history_filter.get() or "All Categories"
        entries = self.history_manager.get_entries(category_filter=cat_filter)

        cur_sel = self.tree_history.selection()
        selected_id = cur_sel[0] if cur_sel else None

        for item in self.tree_history.get_children():
            self.tree_history.delete(item)

        for idx, e in enumerate(entries):
            eid = str(e.get("id") or f"dl_{idx}_{int(time.time() * 1000)}")
            if self.tree_history.exists(eid):
                eid = f"{eid}_{idx}"
            cat_display = f"{e.get('icon', '')} {e.get('category', 'General')}".strip()
            fn = e.get("filename", "")
            size_bytes = e.get("size_bytes", 0)
            size_str = format_filesize(size_bytes) if size_bytes > 0 else "—"
            status = e.get("status", "Completed")
            date_str = e.get("timestamp", "")
            fp = e.get("file_path", "")
            self.tree_history.insert("", tk.END, iid=eid, values=(cat_display, fn, size_str, status, date_str, fp))

        if selected_id and self.tree_history.exists(selected_id):
            self.tree_history.selection_set(selected_id)
            self.tree_history.focus(selected_id)

    def _history_open_selected_file(self):
        sel = self.tree_history.selection()
        if not sel:
            return
        entry = self.history_manager.get_entry(sel[0])
        if entry and entry.get("file_path"):
            fp = entry["file_path"]
            if os.path.exists(fp):
                open_downloaded_file(fp)
            else:
                parts_dir = fp + ".sd_parts"
                status = str(entry.get("status", "")).strip()
                if os.path.isdir(parts_dir) or status in ("Paused", "In Progress", "Failed"):
                    self.ask_safe_yesno(
                        tr("dialog_resume_incomplete_title", "Resume Incomplete Download"),
                        tr("dialog_resume_incomplete_msg", "This file is paused or incomplete. Would you like to resume downloading now?"),
                        on_yes=self._history_redownload_selected
                    )
                else:
                    self.log(f"[HISTORY] File not found on disk: {fp}")
                    if hasattr(self, "show_safe_warning"):
                        msg = tr("dialog_not_found_msg", "The downloaded file does not exist at:\n{path}").format(path=fp)
                        self.show_safe_warning(tr("dialog_not_found_title", "File Not Found"), msg)

    def _history_open_selected_folder(self):
        sel = self.tree_history.selection()
        if not sel:
            return
        entry = self.history_manager.get_entry(sel[0])
        if entry and entry.get("file_path"):
            open_containing_folder(entry["file_path"])

    def _history_copy_selected_url(self):
        sel = self.tree_history.selection()
        if not sel:
            return
        entry = self.history_manager.get_entry(sel[0])
        if entry and entry.get("url"):
            try:
                self.root.clipboard_clear()
                self.root.clipboard_append(entry["url"])
                self.log(f"[HISTORY] Copied URL to clipboard: {entry['url']}")
            except Exception:
                pass

    def _history_redownload_selected(self):
        """Loads selected history entry into URL/Destination and triggers download."""
        sel = self.tree_history.selection()
        if not sel:
            return
        entry_id = sel[0]
        entry = self.history_manager.get_entry(entry_id)
        if not entry:
            return
        url = entry.get("url", "").strip()
        file_path = entry.get("file_path", "").strip()
        if not url:
            return
        if hasattr(self, "entry_url"):
            self.entry_url.delete(0, tk.END)
            self.entry_url.insert(0, url)
        if file_path and hasattr(self, "entry_dest"):
            self.entry_dest.delete(0, tk.END)
            self.entry_dest.insert(0, file_path)
        elif hasattr(self, "_on_url_change"):
            self._on_url_change()
        if hasattr(self, "notebook"):
            try:
                self.notebook.select(0)
            except Exception:
                pass
        self._on_start_download()

    def _history_remove_selected(self, delete_file: bool = False):
        sel = self.tree_history.selection()
        if not sel:
            return
        for entry_id in sel:
            self.history_manager.remove_entry(entry_id, delete_file=delete_file)
        self._refresh_history_table()

    def _history_clear_all(self):
        self.history_manager.clear_history()
        self._refresh_history_table()

    def log(self, message: str):
        """Appends message to activity log console."""
        if getattr(self, "_closing", False):
            return
        job_box = [None]
        def _append():
            try:
                if hasattr(self, "_log_jobs") and job_box[0] in self._log_jobs:
                    self._log_jobs.remove(job_box[0])
                if not getattr(self, "_closing", False) and hasattr(self, "txt_log"):
                    if hasattr(self, "root") and self.root and self.root.winfo_exists():
                        if self.txt_log.winfo_exists():
                            self.txt_log.insert(tk.END, message + "\n")
                            self.txt_log.see(tk.END)
            except Exception:
                pass
        try:
            if not getattr(self, "_closing", False) and hasattr(self, "root") and self.root and self.root.winfo_exists():
                j = self.root.after(0, _append)
                job_box[0] = j
                if hasattr(self, "_log_jobs"):
                    self._log_jobs.append(j)
        except Exception:
            pass

    # ----------------------------------------------------------------------------------
    # Engine Control Callbacks
    # ----------------------------------------------------------------------------------

    def is_window_hidden_or_minimized(self) -> bool:
        """Determines if the main application window is minimized, iconic, withdrawn, or hidden."""
        if getattr(self, "_start_hidden", False):
            return True
        if not hasattr(self, "root") or not self.root:
            return False
        try:
            if not self.root.winfo_exists():
                return False
            state = self.root.state()
            if state in ("withdrawn", "iconic"):
                return True
            if not self.root.winfo_viewable():
                return True
            if IS_WINDOWS:
                try:
                    hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
                    if ctypes.windll.user32.IsIconic(hwnd):
                        return True
                except Exception:
                    pass
        except Exception:
            pass
        return False

    def _on_start_download(self, skip_resolver: bool = False):
        if self.engine and self.engine.is_running:
            return

        if hasattr(self, "_yt_cancel_event") and self._yt_cancel_event:
            try:
                self._yt_cancel_event.set()
            except Exception:
                pass

        url = self.entry_url.get().strip()
        dest = self.entry_dest.get().strip()

        if not url:
            self.show_safe_warning("Missing URL", "Please enter a valid HTTP/HTTPS download URL.")
            return
        if not dest:
            self.show_safe_warning("Missing Save Path", "Please select a valid destination file path.")
            return

        try:
            max_conn = int(self.conn_var.get())
        except ValueError:
            max_conn = 8

        try:
            kb_limit = float(self.entry_custom_speed.get().strip())
        except ValueError:
            kb_limit = 0.0

        bytes_limit = kb_limit * 1024.0 if kb_limit > 0 else 0.0

        if is_media_url(url, check_ytdlp_extractors=True) or skip_resolver:
            self._start_download_with_engine(url, dest, max_conn, bytes_limit, modal=None)
            return

        # Manually typed non-media URL: resolve in background thread before starting
        def _on_resolved(info: Dict[str, Any]):
            real_url = info.get("url") or url
            if info.get("resolved"):
                self.log(f"[LINK RESOLVER] Web page detected. Real file found: {real_url}")

            downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
            dest_dir = os.path.dirname(dest) if dest else downloads_dir
            if not os.path.isdir(dest_dir):
                dest_dir = downloads_dir

            real_fn = info.get("filename") or derive_download_filename(real_url)
            if getattr(self, "auto_categorize_folders", True) and self._is_downloads_or_category_subfolder(dest_dir, downloads_dir):
                final_dest = resolve_categorized_path(downloads_dir, real_fn, auto_categorize=True)
            else:
                final_dest = os.path.join(dest_dir, real_fn)

            try:
                self.entry_url.delete(0, tk.END)
                self.entry_url.insert(0, real_url)
                self.entry_dest.delete(0, tk.END)
                self.entry_dest.insert(0, final_dest)
            except Exception:
                pass

            self._start_download_with_engine(real_url, final_dest, max_conn, bytes_limit, modal=None)

        self._resolve_real_url_async(url, on_resolved=_on_resolved)

    def _start_download_with_engine(
        self,
        url: str,
        dest: str,
        max_conn: int = 8,
        bytes_limit: float = 0.0,
        modal: Optional[Any] = None
    ):
        """Starts download engine, optionally bridging metrics and controls to a standalone modal."""
        if self.engine and self.engine.is_running:
            return

        if hasattr(self, "_yt_cancel_event") and self._yt_cancel_event:
            try:
                self._yt_cancel_event.set()
            except Exception:
                pass

        # Populate GUI entry fields
        try:
            self.entry_url.delete(0, tk.END)
            self.entry_url.insert(0, url)
            self.entry_dest.delete(0, tk.END)
            self.entry_dest.insert(0, dest)
            self.conn_var.set(str(max_conn))
            if bytes_limit > 0:
                self.entry_custom_speed.delete(0, tk.END)
                self.entry_custom_speed.insert(0, str(int(bytes_limit / 1024.0)))
        except Exception:
            pass

        # UI state transitions in main window
        try:
            self.btn_start.configure(state="disabled")
            self.btn_pause.configure(state="normal", text=tr("btn_pause", "⏸ Pause"), bg=self.c_panel_light)
            self.btn_cancel.configure(state="normal")
            if hasattr(self, "btn_refresh_link"):
                self.btn_refresh_link.configure(state="normal", bg=self.c_panel_light, fg=self.c_accent)
            self.txt_log.delete("1.0", tk.END)
            for item in self.tree_chunks.get_children():
                self.tree_chunks.delete(item)
            self._draw_main_progress(0.0)
            self._draw_chunk_segments([])
        except Exception:
            pass

        # Check if URL is YouTube or supported social media
        if is_media_url(url, check_ytdlp_extractors=True):
            self._start_youtube_download(url, dest, max_conn, bytes_limit, modal=modal)
            return

        # Wrapped callbacks for modal + main UI
        def _comb_progress(downloaded: int, total: int, speed: float, eta: str, active_chunks: int):
            if modal:
                try:
                    if modal.winfo_exists():
                        modal.update_progress(downloaded, total, speed, eta, active_chunks)
                except Exception:
                    pass
            self._engine_progress_cb(downloaded, total, speed, eta, active_chunks)

        def _comb_complete(path: str, total_bytes: int, elapsed: float):
            has_modal = False
            if modal:
                try:
                    if modal.winfo_exists():
                        modal.on_download_complete(path, total_bytes, elapsed)
                        has_modal = True
                except Exception:
                    pass
            self._engine_complete_cb(path, total_bytes, elapsed, suppress_dialog=has_modal)

        def _comb_error(err: str):
            if modal:
                try:
                    if modal.winfo_exists():
                        modal.on_download_error(err)
                except Exception:
                    pass
            self._engine_error_cb(err)

        self.engine = TurboDownloadEngine(
            url=url,
            destination_path=dest,
            max_connections=max_conn,
            rate_limit_bytes_per_sec=bytes_limit,
            on_progress=_comb_progress,
            on_chunk_update=self._engine_chunk_update_cb,
            on_log=self.log,
            on_complete=_comb_complete,
            on_error=_comb_error
        )
        if modal and hasattr(modal, "attach_engine"):
            modal.attach_engine(self.engine)

        self.engine.start()

    def _start_youtube_download(
        self,
        url: str,
        dest: str,
        max_conn: int = 8,
        bytes_limit: float = 0.0,
        modal: Optional[Any] = None
    ):
        """Resolves available YouTube qualities and displays modern format selection modal."""
        if hasattr(self, "_yt_cancel_event") and self._yt_cancel_event:
            try:
                self._yt_cancel_event.set()
            except Exception:
                pass
        self._yt_cancel_event = threading.Event()
        try:
            self.btn_start.configure(state="disabled")
            self.btn_pause.configure(state="disabled")
            self.btn_cancel.configure(state="normal")
            if hasattr(self, "btn_refresh_link"):
                self.btn_refresh_link.configure(state="normal", bg=self.c_panel_light, fg=self.c_accent)
            self.txt_log.delete("1.0", tk.END)

            for item in self.tree_chunks.get_children():
                self.tree_chunks.delete(item)
            self._draw_main_progress(0.0)
            self._draw_chunk_segments([])
            self.card_size.configure(text="Fetching available formats...")
        except Exception:
            pass

        plat = extract_media_platform(url)
        tag = plat.upper().replace(" / X", "")
        self.log(f"[{tag}] Detected {plat} stream URL: {url}")
        self.log(f"[{tag}] Querying available video resolutions and formats via yt-dlp...")

        # In < 50ms, display sleek frameless fetching toast indicator if main window is hidden or minimized
        if self.is_window_hidden_or_minimized():
            try:
                self._show_fetching_toast(url)
            except Exception:
                pass

        def _resolve_and_prompt():
            try:
                resolver = YouTubeResolver(
                    on_log=self.log,
                    cookies_from_browser=self.cookies_browser,
                    cookies_file=self.cookies_file
                )
                info, options = resolver.extract_format_options(url)

                if self._yt_cancel_event.is_set():
                    self.log(f"[{tag}] Quality analysis cancelled.")
                    return

                if not options:
                    raise RuntimeError(f"No downloadable media formats found for this {plat} video.")

                raw_title = info.get("title") or f"{plat}_Video"
                clean_title = sanitize_filename(raw_title)
                duration = int(info.get("duration") or 0)

                dest_dir = os.path.dirname(dest) or os.path.join(os.path.expanduser("~"), "Downloads")
                try:
                    os.makedirs(dest_dir, exist_ok=True)
                except Exception:
                    pass

                initial_ext = options[0].ext or "mp4"
                initial_fn = f"{clean_title}.{initial_ext}"
                downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
                if getattr(self, "auto_categorize_folders", True) and self._is_downloads_or_category_subfolder(dest_dir, downloads_dir):
                    initial_dest = resolve_categorized_path(downloads_dir, initial_fn, auto_categorize=True)
                else:
                    initial_dest = os.path.join(dest_dir, initial_fn)

                def _show_modal():
                    try:
                        self._close_fetching_toast()
                        if self._yt_cancel_event.is_set():
                            return

                        self.card_size.configure(text="Select Quality")

                        def _start_coordinator(selected_opt: VideoFormatOption, final_dest: str, yt_modal: Optional[Any] = None):
                            stream_info = resolver.build_stream_info(info, selected_opt)

                            try:
                                self.entry_dest.delete(0, tk.END)
                                self.entry_dest.insert(0, final_dest)
                                self.btn_pause.configure(state="normal", text=tr("btn_pause", "⏸ Pause"), bg=self.c_panel_light)
                                self.btn_cancel.configure(state="normal")
                            except Exception:
                                pass

                            def _comb_progress(downloaded, total, speed, eta, active):
                                if yt_modal:
                                    try:
                                        if yt_modal.winfo_exists():
                                            yt_modal.update_progress(downloaded, total, speed, eta, active)
                                    except Exception:
                                        pass
                                self._engine_progress_cb(downloaded, total, speed, eta, active)

                            def _comb_complete(path, total_bytes, elapsed):
                                has_yt_modal = False
                                if yt_modal:
                                    try:
                                        if yt_modal.winfo_exists():
                                            yt_modal.on_download_complete(path, total_bytes, elapsed)
                                            has_yt_modal = True
                                    except Exception:
                                        pass
                                self._engine_complete_cb(path, total_bytes, elapsed, suppress_dialog=has_yt_modal)

                            def _comb_error(err):
                                if yt_modal:
                                    try:
                                        if yt_modal.winfo_exists():
                                            yt_modal.on_download_error(err)
                                    except Exception:
                                        pass
                                self._engine_error_cb(err)

                            coordinator = StreamDownloadCoordinator(
                                stream_info=stream_info,
                                destination_path=final_dest,
                                max_connections=max_conn,
                                rate_limit_bytes_per_sec=bytes_limit,
                                on_progress=_comb_progress,
                                on_chunk_update=self._engine_chunk_update_cb,
                                on_log=self.log,
                                on_complete=_comb_complete,
                                on_error=_comb_error
                            )
                            self.engine = coordinator
                            if yt_modal and hasattr(yt_modal, "attach_engine"):
                                yt_modal.attach_engine(coordinator)
                            coordinator.start()

                        def _on_confirm(selected_opt: VideoFormatOption, final_dest: str):
                            self._quality_modal = None
                            self.clear_last_clipboard_url()
                            try:
                                is_hidden = self.is_window_hidden_or_minimized()
                                yt_prog_modal = None
                                if is_hidden:
                                    yt_prog_modal = DownloadConfirmationModal(
                                        parent=self.root,
                                        url=url,
                                        default_dest_path=final_dest,
                                        theme=self._theme_dict(),
                                        parent_app=self,
                                        show_progress_immediately=True
                                    )
                                _start_coordinator(selected_opt, final_dest, yt_modal=yt_prog_modal)
                            except Exception as e:
                                self._quality_modal = None
                                self.log(f"[{tag} START ERROR] {e}")
                                self._engine_error_cb(str(e))

                        def _on_open_in_main(selected_opt: VideoFormatOption, final_dest: str):
                            self._quality_modal = None
                            self.clear_last_clipboard_url()
                            self.restore_window()
                            try:
                                _start_coordinator(selected_opt, final_dest, yt_modal=None)
                            except Exception as e:
                                self._quality_modal = None
                                self.log(f"[{tag} START ERROR] {e}")
                                self._engine_error_cb(str(e))

                        def _on_cancel():
                            self._quality_modal = None
                            self.clear_last_clipboard_url()
                            try:
                                self.btn_start.configure(state="normal")
                                self.btn_pause.configure(state="disabled")
                                self.btn_cancel.configure(state="disabled")
                                self.card_size.configure(text=tr("status_ready", "Ready"))
                            except Exception:
                                pass
                            self.log(f"[{tag}] Video quality selection cancelled.")

                        theme_dict = {
                            "c_bg": self.c_bg,
                            "c_panel": self.c_panel,
                            "c_panel_light": self.c_panel_light,
                            "c_border": self.c_border,
                            "c_accent": self.c_accent,
                            "c_accent_dark": self.c_accent_dark,
                            "c_success": self.c_success,
                            "c_danger": self.c_danger,
                            "c_text_bright": self.c_text_bright,
                            "c_text_muted": self.c_text_muted,
                            "c_input_bg": self.c_input_bg
                        }

                        # Dismiss any previously open quality modal
                        if hasattr(self, "_quality_modal") and self._quality_modal:
                            try:
                                if self._quality_modal.winfo_exists():
                                    self._quality_modal.destroy()
                            except Exception:
                                pass
                            self._quality_modal = None

                        self._quality_modal = QualitySelectionModal(
                            parent=self.root,
                            video_title=raw_title,
                            duration=duration,
                            options=options,
                            default_dest_path=initial_dest,
                            theme=theme_dict,
                            on_confirm=_on_confirm,
                            on_cancel=_on_cancel,
                            on_open_in_main=_on_open_in_main,
                            parent_app=self
                        )
                    except Exception as e:
                        self._quality_modal = None
                        self.clear_last_clipboard_url()
                        self.log(f"[{tag} MODAL ERROR] {e}")
                        self._engine_error_cb(str(e))

                try:
                    self.dispatch_to_main_thread(_show_modal)
                except Exception:
                    pass

            except Exception as e:
                self.clear_last_clipboard_url()
                try:
                    self.dispatch_to_main_thread(self._close_fetching_toast)
                except Exception:
                    pass
                if not self._yt_cancel_event.is_set():
                    self.log(f"[{tag} ERROR] {e}")
                    try:
                        self.dispatch_to_main_thread(lambda: self._engine_error_cb(str(e)))
                    except Exception:
                        pass

        resolve_thread = threading.Thread(target=_resolve_and_prompt, daemon=True)
        resolve_thread.start()

    _start_media_download = _start_youtube_download

    # ----------------------------------------------------------------------------------
    # TDM-Style Automatic Clipboard Sniffer / URL Monitor
    # ----------------------------------------------------------------------------------

    def _init_clipboard_sniffer(self):
        """Initializes clipboard monitor state to current clipboard content so existing text doesn't trigger."""
        if IS_WINDOWS:
            try:
                self._last_clipboard_seq = ctypes.windll.user32.GetClipboardSequenceNumber()
            except Exception:
                self._last_clipboard_seq = None
        try:
            cur = get_clipboard_text(self.root)
            if cur:
                self._last_clipboard_url = cur.strip()
        except Exception:
            pass

        if hasattr(self, "root") and self.root:
            try:
                self._clipboard_job = self.root.after(self._clipboard_poll_interval, self._check_clipboard_tick)
            except Exception:
                pass

    def _check_clipboard_tick(self):
        """Periodic timer polling system clipboard for downloadable URLs."""
        if self._closing or not hasattr(self, "root") or not self.root:
            return
        try:
            if not self.root.winfo_exists():
                return
        except Exception:
            return

        if self._clipboard_sniffer_active:
            try:
                self._check_clipboard_now()
            except Exception:
                pass

        if not self._closing:
            try:
                if self.root.winfo_exists():
                    self._clipboard_job = self.root.after(self._clipboard_poll_interval, self._check_clipboard_tick)
            except Exception:
                pass

    def _check_clipboard_now(self, force: bool = False):
        """Checks if current clipboard contains a new downloadable URL and processes it."""
        seq = None
        if IS_WINDOWS and not force:
            try:
                seq = ctypes.windll.user32.GetClipboardSequenceNumber()
            except Exception:
                seq = None

            # Fast path: sequence number unchanged -> nothing was copied
            if seq is not None and self._last_clipboard_seq is not None:
                if seq == self._last_clipboard_seq:
                    return

        text = get_clipboard_text(self.root)

        seq_changed = (seq is not None and self._last_clipboard_seq is not None and seq != self._last_clipboard_seq)

        if seq is not None:
            self._last_clipboard_seq = seq

        if not text or not isinstance(text, str):
            return

        url = text.strip()
        if not url:
            return

        # Prevent duplicate prompt if URL matches last processed clipboard string and sequence unchanged.
        # But if sequence number changed (user explicitly copied the link again) or last URL was cleared, allow processing.
        if not seq_changed and (url == self._last_clipboard_url):
            return

        self._last_clipboard_url = url

        if is_downloadable_url(url):
            self._on_clipboard_url_detected(url)

    def clear_last_clipboard_url(self):
        """Clears cached last clipboard URL string so re-copying or re-checking triggers immediately."""
        self._last_clipboard_url = None
        self._last_clipboard_seq = None

    def _resolve_real_url_async(
        self,
        url: str,
        on_resolved: Callable[[Dict[str, Any]], None],
        show_toast: bool = True,
        modal_to_close: Optional[Any] = None
    ):
        """Asynchronously probes and resolves a candidate download URL, handling HTML landing pages."""
        if show_toast:
            try:
                self._show_fetching_toast(url)
            except Exception:
                pass

        def _worker():
            info = resolve_real_download_url(url, ssl_context=getattr(self, "ssl_context", None))

            def _dispatch():
                try:
                    self._close_fetching_toast()
                except Exception:
                    pass

                candidates = info.get("candidates") or []

                if info.get("is_html") and not info.get("resolved"):
                    if len(candidates) > 1:
                        self.clear_last_clipboard_url()
                        if modal_to_close:
                            try:
                                modal_to_close.destroy()
                            except Exception:
                                pass
                            if getattr(self, "_confirm_modal", None) is modal_to_close:
                                self._confirm_modal = None
                        self.log(f"[LINK RESOLVER] Multiple download candidates ({len(candidates)}) detected on page: {url}")
                        self._show_multiple_candidates_dialog(url, candidates, page_title=info.get("page_title", ""))
                        return

                    self.clear_last_clipboard_url()
                    if modal_to_close:
                        try:
                            modal_to_close.destroy()
                        except Exception:
                            pass
                        if getattr(self, "_confirm_modal", None) is modal_to_close:
                            self._confirm_modal = None
                    try:
                        self.btn_start.configure(state="normal")
                        self.btn_pause.configure(state="disabled")
                        self.btn_cancel.configure(state="disabled")
                    except Exception:
                        pass
                    self.log(f"[LINK RESOLVER] Web page detected (not a download link): {url}")
                    msg = tr("dialog_not_download_msg")
                    SafeModalDialog(
                        self.root,
                        title=tr("dialog_not_download_title"),
                        message=msg,
                        dialog_type="warning",
                        theme=self._theme_dict()
                    )
                    return

                if len(candidates) > 1:
                    self.clear_last_clipboard_url()
                    if modal_to_close:
                        try:
                            modal_to_close.destroy()
                        except Exception:
                            pass
                        if getattr(self, "_confirm_modal", None) is modal_to_close:
                            self._confirm_modal = None
                    self.log(f"[LINK RESOLVER] Multiple download candidates ({len(candidates)}) detected on page: {url}")
                    self._show_multiple_candidates_dialog(url, candidates, page_title=info.get("page_title", ""))
                    return

                if len(candidates) == 1 and info.get("is_html"):
                    cand = candidates[0]
                    info["url"] = cand["url"]
                    if cand.get("filename"):
                        info["filename"] = cand["filename"]
                    info["resolved"] = True
                    info["is_html"] = False

                on_resolved(info)

            self.dispatch_to_main_thread(_dispatch)

        t = threading.Thread(target=_worker, daemon=True, name="LinkResolverThread")
        t.start()

    def _on_clipboard_url_detected(self, url: str):
        """Dispatches an intercepted downloadable URL from the clipboard."""
        self.log(f"[CLIPBOARD] Intercepted downloadable link from clipboard: {url}")

        # Populate URL entry
        try:
            self.entry_url.delete(0, tk.END)
            self.entry_url.insert(0, url)
        except Exception:
            pass

        # Derive and populate destination
        downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
        cur_dest = ""
        try:
            cur_dest = self.entry_dest.get().strip()
        except Exception:
            pass
        dest_dir = os.path.dirname(cur_dest) if cur_dest else downloads_dir
        if not os.path.isdir(dest_dir):
            dest_dir = downloads_dir

        url_fn = derive_download_filename(url)
        if getattr(self, "auto_categorize_folders", True) and self._is_downloads_or_category_subfolder(dest_dir, downloads_dir):
            new_dest = resolve_categorized_path(downloads_dir, url_fn, auto_categorize=True)
        else:
            new_dest = os.path.join(dest_dir, url_fn)
        try:
            self.entry_dest.delete(0, tk.END)
            self.entry_dest.insert(0, new_dest)
        except Exception:
            pass

        # DO NOT force-restore the main window if hidden or minimized in tray
        if not self.is_window_hidden_or_minimized():
            try:
                self.root.lift()
                self.root.focus_force()
            except Exception:
                pass

        # Non-blocking TDM-style download handling (no blocking modal dialogs / grab_set traps)
        if is_media_url(url):
            plat = extract_media_platform(url)
            if self.engine and self.engine.is_running:
                self.log(f"[CLIPBOARD] Note: Active task is running. {plat} stream queued in URL field.")
            elif getattr(self, "_auto_start_clipboard", True):
                self.log(f"[CLIPBOARD] {plat} stream detected: {url}. Starting format analysis...")
                try:
                    max_conn = int(self.conn_var.get())
                except Exception:
                    max_conn = 8
                try:
                    kb_limit = float(self.entry_custom_speed.get().strip())
                except Exception:
                    kb_limit = 0.0
                bytes_limit = kb_limit * 1024.0 if kb_limit > 0 else 0.0
                self._start_youtube_download(url, new_dest, max_conn, bytes_limit)
            else:
                self.log(f"[CLIPBOARD] {plat} stream populated: {url}. Ready for one-click start.")
        else:
            if self.engine and self.engine.is_running:
                self.log(f"[CLIPBOARD] Note: Active transfer in progress. URL '{url_fn}' populated in inputs.")
            elif is_potential_html_url(url):
                def _on_clipboard_resolved(info: Dict[str, Any]):
                    if self.engine and self.engine.is_running:
                        return

                    real_url = info.get("url") or url
                    if info.get("resolved"):
                        self.log(f"[LINK RESOLVER] Web page detected. Real file found: {real_url}")

                    downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
                    cur_d = ""
                    try:
                        cur_d = self.entry_dest.get().strip()
                    except Exception:
                        pass
                    dest_dir = os.path.dirname(cur_d) if cur_d else downloads_dir
                    if not os.path.isdir(dest_dir):
                        dest_dir = downloads_dir

                    resolved_fn = info.get("filename") or derive_download_filename(real_url)
                    if getattr(self, "auto_categorize_folders", True) and self._is_downloads_or_category_subfolder(dest_dir, downloads_dir):
                        final_dest = resolve_categorized_path(downloads_dir, resolved_fn, auto_categorize=True)
                    else:
                        final_dest = os.path.join(dest_dir, resolved_fn)

                    try:
                        self.entry_url.delete(0, tk.END)
                        self.entry_url.insert(0, real_url)
                        self.entry_dest.delete(0, tk.END)
                        self.entry_dest.insert(0, final_dest)
                    except Exception:
                        pass

                    if not self.is_window_hidden_or_minimized():
                        try:
                            self.root.lift()
                            self.root.focus_force()
                        except Exception:
                            pass

                    if getattr(self, "_auto_start_clipboard", True):
                        self.log(f"[CLIPBOARD] Intercepted link ready: '{resolved_fn}'. Showing TDM confirmation dialog...")
                        self._show_download_confirmation_dialog(real_url, final_dest)
                    else:
                        self.log(f"[CLIPBOARD] Intercepted link populated: '{resolved_fn}'. Ready for one-click start.")

                self._resolve_real_url_async(url, on_resolved=_on_clipboard_resolved, show_toast=True)
            elif getattr(self, "_auto_start_clipboard", True):
                self.log(f"[CLIPBOARD] Intercepted link ready: '{url_fn}'. Showing TDM confirmation dialog...")
                self._show_download_confirmation_dialog(url, new_dest)
            else:
                self.log(f"[CLIPBOARD] Intercepted link populated: '{url_fn}'. Ready for one-click start.")

    def _show_download_confirmation_dialog(self, url: str, default_dest: str):
        """Displays the TDM-style download confirmation dialog for intercepted URLs."""
        if threading.current_thread() != threading.main_thread():
            if hasattr(self, "root") and self.root:
                try:
                    self.root.after(0, lambda: self._show_download_confirmation_dialog(url, default_dest))
                except Exception:
                    pass
            return

        self._close_fetching_toast()

        if hasattr(self, "_confirm_modal") and self._confirm_modal:
            try:
                if self._confirm_modal.winfo_exists():
                    if getattr(self._confirm_modal, "is_in_progress_view", False) or getattr(self._confirm_modal, "is_completed", False):
                        # Modal is actively downloading or displaying completion actions; keep it intact
                        self.log(f"[CLIPBOARD] Active standalone download in progress; queued '{derive_download_filename(url)}' in inputs.")
                        return
                    self._confirm_modal.destroy()
            except Exception:
                pass
            self._confirm_modal = None

        def _on_start_in_window(final_dest: str, max_conn: int, bytes_limit: float, modal: DownloadConfirmationModal):
            # Keeps the main window hidden/minimized
            def _proceed_start(info: Dict[str, Any]):
                resolved_url = info.get("url") or url
                resolved_fn = info.get("filename") or derive_download_filename(resolved_url)
                dest_dir = os.path.dirname(final_dest) if final_dest else os.path.join(os.path.expanduser("~"), "Downloads")
                downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
                if getattr(self, "auto_categorize_folders", True) and self._is_downloads_or_category_subfolder(dest_dir, downloads_dir):
                    act_dest = resolve_categorized_path(downloads_dir, resolved_fn, auto_categorize=True)
                else:
                    act_dest = os.path.join(dest_dir, resolved_fn)
                self.log(f"[CLIPBOARD] Download started in standalone window: {os.path.basename(act_dest)} (Threads: {max_conn}, Speed Limit: {bytes_limit} B/s)")
                self._start_download_with_engine(resolved_url, act_dest, max_conn, bytes_limit, modal=modal)

            if is_potential_html_url(url):
                self._resolve_real_url_async(url, on_resolved=_proceed_start, modal_to_close=modal)
            else:
                self.log(f"[CLIPBOARD] Download started in standalone window: {os.path.basename(final_dest)} (Threads: {max_conn}, Speed Limit: {bytes_limit} B/s)")
                self._start_download_with_engine(url, final_dest, max_conn, bytes_limit, modal=modal)

        def _on_open_in_main(final_dest: str, max_conn: int, bytes_limit: float):
            self._confirm_modal = None
            self.restore_window()
            try:
                self.entry_url.delete(0, tk.END)
                self.entry_url.insert(0, url)
                self.entry_dest.delete(0, tk.END)
                self.entry_dest.insert(0, final_dest)
                self.conn_var.set(str(max_conn))
                if bytes_limit > 0:
                    self.entry_custom_speed.delete(0, tk.END)
                    self.entry_custom_speed.insert(0, str(int(bytes_limit / 1024.0)))
                else:
                    self.entry_custom_speed.delete(0, tk.END)
            except Exception:
                pass
            self.log(f"[CLIPBOARD] Download opened in main app: {os.path.basename(final_dest)}")
            self._on_start_download(skip_resolver=True)

        def _on_confirm(final_dest: str, *args):
            self._confirm_modal = None
            self.clear_last_clipboard_url()
            try:
                self.entry_dest.delete(0, tk.END)
                self.entry_dest.insert(0, final_dest)
            except Exception:
                pass
            self.log(f"[CLIPBOARD] Download confirmed by user: {os.path.basename(final_dest)}. Starting download...")
            self._on_start_download()

        def _on_cancel():
            self._confirm_modal = None
            self.clear_last_clipboard_url()
            self.log(f"[CLIPBOARD] Download cancelled by user for: {derive_download_filename(url)}")

        try:
            default_conn = 8
            try:
                default_conn = int(self.conn_var.get())
            except Exception:
                pass
            default_speed = 0.0
            try:
                kb = float(self.entry_custom_speed.get().strip())
                default_speed = kb * 1024.0 if kb > 0 else 0.0
            except Exception:
                pass

            self._confirm_modal = DownloadConfirmationModal(
                parent=self.root,
                url=url,
                default_dest_path=default_dest,
                theme=self._theme_dict(),
                on_confirm=_on_confirm,
                on_cancel=_on_cancel,
                on_start_in_window=_on_start_in_window,
                on_open_in_main=_on_open_in_main,
                parent_app=self,
                default_connections=default_conn,
                default_speed_limit=default_speed
            )
        except Exception as e:
            self._confirm_modal = None
            self.log(f"[CONFIRM MODAL ERROR] {e}")

    def _update_sniffer_btn(self):
        """Refreshes the visual state of the clipboard sniffer button."""
        if not hasattr(self, "btn_clipboard_sniffer"):
            return
        try:
            if not self.btn_clipboard_sniffer.winfo_exists():
                return
        except Exception:
            return
        if getattr(self, "_clipboard_sniffer_active", True):
            self.btn_clipboard_sniffer.configure(
                text=tr("btn_sniffer_active"),
                fg=self.c_success,
                bg=self.c_panel_light
            )
        else:
            self.btn_clipboard_sniffer.configure(
                text=tr("btn_sniffer_paused"),
                fg=self.c_text_muted,
                bg=self.c_panel
            )

    def toggle_clipboard_sniffer(self):
        """Toggles automatic clipboard URL monitoring on or off."""
        self._clipboard_sniffer_active = not self._clipboard_sniffer_active
        self._update_sniffer_btn()
        if self._clipboard_sniffer_active:
            self.log("[CLIPBOARD] Sniffer Active: Monitoring system clipboard for downloadable links.")
            if getattr(self, "_clipboard_job", None) is None and hasattr(self, "root") and self.root:
                try:
                    if self.root.winfo_exists():
                        self._clipboard_job = self.root.after(self._clipboard_poll_interval, self._check_clipboard_tick)
                except Exception:
                    pass
        else:
            self.log("[CLIPBOARD] Sniffer Paused: Clipboard monitoring paused.")

        if hasattr(self, "tray_manager") and self.tray_manager:
            try:
                self.tray_manager.update_menu()
            except Exception:
                pass

    def _update_startup_btn(self):
        """Refreshes the visual state of the Windows auto-start button."""
        if hasattr(self, "btn_startup"):
            try:
                if not self.btn_startup.winfo_exists():
                    return
            except Exception:
                return
            enabled = is_startup_enabled()
            self._startup_enabled = enabled
            if enabled:
                self.btn_startup.configure(
                    text=tr("btn_startup_on"),
                    fg=self.c_success,
                    bg=self.c_panel_light
                )
            else:
                self.btn_startup.configure(
                    text=tr("btn_startup_off"),
                    fg=self.c_text_muted,
                    bg=self.c_panel
                )

    def _get_cookies_btn_text(self) -> str:
        """Returns the display label for the cookies setting button."""
        if self.cookies_file and os.path.isfile(self.cookies_file):
            return "🍪 Cookies: File"
        cb = (self.cookies_browser or "auto").lower()
        if cb in ("none", "off"):
            return "🍪 Cookies: Off"
        display_names = {
            "auto": "Auto",
            "edge": "Edge",
            "chrome": "Chrome",
            "firefox": "Firefox",
            "brave": "Brave",
            "opera": "Opera",
            "vivaldi": "Vivaldi",
        }
        return f"🍪 Cookies: {display_names.get(cb, cb.capitalize())}"

    def _update_cookies_btn(self):
        """Refreshes the visual text and theme colors of the cookies button."""
        if not hasattr(self, "btn_cookies"):
            return
        try:
            if not self.btn_cookies.winfo_exists():
                return
        except Exception:
            return

        btn_text = self._get_cookies_btn_text()
        cb = (self.cookies_browser or "auto").lower()
        has_cookies = not (cb in ("none", "off") and not (self.cookies_file and os.path.isfile(self.cookies_file)))

        self.btn_cookies.configure(
            text=btn_text,
            fg=self.c_accent if has_cookies else self.c_text_muted,
            bg=self.c_panel_light if has_cookies else self.c_panel
        )

    def cycle_cookies_setting(self):
        """
        Cycles through cookie options:
        ('auto', 'edge', 'chrome', 'firefox', 'brave', 'file...', 'none')
        Saves chosen setting to app configuration.
        """
        cycle_options = ["auto", "edge", "chrome", "firefox", "brave", "file...", "none"]
        current = "file..." if (self.cookies_file and os.path.isfile(self.cookies_file)) else (self.cookies_browser or "auto").lower()
        try:
            cur_idx = cycle_options.index(current)
        except ValueError:
            cur_idx = 0

        next_idx = (cur_idx + 1) % len(cycle_options)
        next_val = cycle_options[next_idx]

        if next_val == "file...":
            chosen = filedialog.askopenfilename(
                parent=self.root,
                title="Select Netscape cookies.txt file",
                filetypes=[("Text / Cookie files", "*.txt;*.cookies"), ("All files", "*.*")]
            )
            if chosen and os.path.isfile(chosen):
                self.cookies_file = chosen
                self.cookies_browser = "file"
                set_setting("cookies_file", self.cookies_file)
                set_setting("cookies_browser", "file")
                self.log(f"[COOKIES] Loaded cookie file: {chosen}")
            else:
                # Cancelled file dialog -> skip to 'none'
                self.cookies_file = ""
                self.cookies_browser = "none"
                set_setting("cookies_file", "")
                set_setting("cookies_browser", "none")
                self.log("[COOKIES] Browser cookies disabled.")
        else:
            self.cookies_file = ""
            self.cookies_browser = next_val
            set_setting("cookies_file", "")
            set_setting("cookies_browser", next_val)
            if next_val == "none":
                self.log("[COOKIES] Browser cookies disabled.")
            else:
                self.log(f"[COOKIES] Cookie browser set to: {next_val.capitalize()}")

        self._update_cookies_btn()

    def toggle_startup_setting(self) -> bool:
        """Toggles Windows startup on boot registry entry with live feedback."""
        current = is_startup_enabled()
        if current:
            success = disable_startup()
            if success:
                self._startup_enabled = False
                self.log("[STARTUP] Windows Run on Boot: Disabled.")
            else:
                self.log("[STARTUP ERROR] Failed to disable Windows Run on Boot.")
        else:
            success = enable_startup(minimized=True)
            if success:
                self._startup_enabled = True
                self.log("[STARTUP] Windows Run on Boot: Enabled (Silent background mode).")
            else:
                self.log("[STARTUP ERROR] Failed to enable Windows Run on Boot.")

        self._update_startup_btn()
        if hasattr(self, "_update_dlg_startup_ui") and callable(self._update_dlg_startup_ui):
            try:
                self._update_dlg_startup_ui()
            except Exception:
                pass
        if hasattr(self, "tray_manager") and self.tray_manager:
            try:
                self.tray_manager.update_menu()
            except Exception:
                pass
        return self._startup_enabled

    def toggle_minimize_to_tray_setting(self) -> bool:
        """Toggles the 'minimize to tray on close' preference and persists to settings."""
        self.minimize_to_tray = not getattr(self, "minimize_to_tray", True)
        set_setting("minimize_to_tray", self.minimize_to_tray)
        if self.minimize_to_tray:
            self.log("[SETTINGS] Close button action set to: Minimize to System Tray.")
        else:
            self.log("[SETTINGS] Close button action set to: Exit Completely.")
        if hasattr(self, "_update_dlg_tray_ui") and callable(self._update_dlg_tray_ui):
            try:
                self._update_dlg_tray_ui()
            except Exception:
                pass
        return self.minimize_to_tray

    def set_minimize_to_tray(self, enabled: bool):
        """Explicitly sets and persists the 'minimize to tray on close' preference."""
        self.minimize_to_tray = bool(enabled)
        set_setting("minimize_to_tray", self.minimize_to_tray)
        if hasattr(self, "_update_dlg_tray_ui") and callable(self._update_dlg_tray_ui):
            try:
                self._update_dlg_tray_ui()
            except Exception:
                pass

    # ----------------------------------------------------------------------------------
    # Browser Bridge Integration Callbacks & Modal Dialog
    # ----------------------------------------------------------------------------------

    def dispatch_to_main_thread(self, fn: Callable, *args, **kwargs):
        """Safely queues a callable to be executed on the Tkinter main thread."""
        if hasattr(self, "_gui_dispatch_queue"):
            self._gui_dispatch_queue.put((fn, args, kwargs))
        if threading.current_thread() == threading.main_thread():
            self._drain_dispatch_queue()

    def _drain_dispatch_queue(self):
        """Executes all pending dispatch tasks on the main thread."""
        _drain_bg_tk_callbacks()
        if hasattr(self, "_gui_dispatch_queue"):
            while not self._gui_dispatch_queue.empty():
                try:
                    action, a_args, a_kwargs = self._gui_dispatch_queue.get_nowait()
                    action(*a_args, **a_kwargs)
                except Exception:
                    pass
        _drain_bg_tk_callbacks()

    def _on_browser_download_received(self, download_info: Dict[str, Any]):
        """Dispatches intercepted download from browser bridge thread to Tkinter main thread."""
        self.dispatch_to_main_thread(self._apply_browser_download, download_info)

    def _apply_browser_download(self, download_info: Dict[str, Any]):
        """Applies intercepted download parameters to the GUI and starts transfer if requested."""
        url = download_info.get("url", "").strip()
        filename = download_info.get("filename", "").strip()
        start_immediately = download_info.get("start_immediately", True)

        if not url:
            return

        self.log(f"[BROWSER] Intercepted download from browser extension: {url}")

        # Populate URL entry
        self.entry_url.delete(0, tk.END)
        self.entry_url.insert(0, url)

        # Populate Destination entry
        downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
        cur_dest = self.entry_dest.get().strip()
        dest_dir = os.path.dirname(cur_dest) if cur_dest else downloads_dir
        if not os.path.isdir(dest_dir):
            dest_dir = downloads_dir

        target_fn = sanitize_filename(urllib.parse.unquote(filename)) if filename else derive_download_filename(url)
        if getattr(self, "auto_categorize_folders", True) and self._is_downloads_or_category_subfolder(dest_dir, downloads_dir):
            new_dest = resolve_categorized_path(downloads_dir, target_fn, auto_categorize=True)
        else:
            new_dest = os.path.join(dest_dir, target_fn)

        self.entry_dest.delete(0, tk.END)
        self.entry_dest.insert(0, new_dest)

        # DO NOT force-restore the main window if hidden or minimized in tray
        if not self.is_window_hidden_or_minimized():
            try:
                self.root.lift()
                self.root.focus_force()
            except Exception:
                pass

        # Handle Media (YouTube / Social media) vs regular file downloads
        if is_media_url(url):
            plat = extract_media_platform(url)
            if self.engine and self.engine.is_running:
                self.log(f"[BROWSER] Note: Active task is running. {plat} stream queued in URL field.")
            else:
                self.log(f"[BROWSER] {plat} stream detected: {url}. Starting format analysis...")
                try:
                    max_conn = int(self.conn_var.get())
                except Exception:
                    max_conn = 8
                try:
                    kb_limit = float(self.entry_custom_speed.get().strip())
                except Exception:
                    kb_limit = 0.0
                bytes_limit = kb_limit * 1024.0 if kb_limit > 0 else 0.0
                self._start_youtube_download(url, new_dest, max_conn, bytes_limit)
        else:
            if self.engine and self.engine.is_running:
                self.log(f"[BROWSER] Note: Active transfer in progress. URL '{os.path.basename(new_dest)}' queued in inputs.")
                return

            if is_potential_html_url(url):
                def _on_browser_resolved(info: Dict[str, Any]):
                    if self.engine and self.engine.is_running:
                        return

                    real_url = info.get("url") or url
                    if info.get("resolved"):
                        self.log(f"[LINK RESOLVER] Web page detected. Real file found: {real_url}")

                    downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
                    cur_d = self.entry_dest.get().strip()
                    dest_dir = os.path.dirname(cur_d) if cur_d else downloads_dir
                    if not os.path.isdir(dest_dir):
                        dest_dir = downloads_dir

                    target_fn = info.get("filename") or (sanitize_filename(urllib.parse.unquote(filename)) if filename else derive_download_filename(real_url))
                    if getattr(self, "auto_categorize_folders", True) and self._is_downloads_or_category_subfolder(dest_dir, downloads_dir):
                        resolved_dest = resolve_categorized_path(downloads_dir, target_fn, auto_categorize=True)
                    else:
                        resolved_dest = os.path.join(dest_dir, target_fn)

                    try:
                        self.entry_url.delete(0, tk.END)
                        self.entry_url.insert(0, real_url)
                        self.entry_dest.delete(0, tk.END)
                        self.entry_dest.insert(0, resolved_dest)
                    except Exception:
                        pass

                    if not self.is_window_hidden_or_minimized():
                        try:
                            self.root.lift()
                            self.root.focus_force()
                        except Exception:
                            pass

                    if self.is_window_hidden_or_minimized() or not start_immediately or getattr(self, "_auto_start_clipboard", True) or getattr(self, "_was_started_hidden", False):
                        self._show_download_confirmation_dialog(real_url, resolved_dest)
                    else:
                        self._on_start_download(skip_resolver=True)

                self._resolve_real_url_async(url, on_resolved=_on_browser_resolved, show_toast=True)
            elif self.is_window_hidden_or_minimized() or not start_immediately or getattr(self, "_auto_start_clipboard", True) or getattr(self, "_was_started_hidden", False):
                self._show_download_confirmation_dialog(url, new_dest)
            else:
                self._on_start_download(skip_resolver=True)

    def _open_browser_integration_dialog(self):
        """Displays settings, connection status, and extension installation instructions."""
        if hasattr(self, "_browser_integration_dlg") and self._browser_integration_dlg:
            try:
                if hasattr(self._browser_integration_dlg, "_browser_icon_photo"):
                    _detach_photo_tk(self._browser_integration_dlg._browser_icon_photo)
                    self._browser_integration_dlg._browser_icon_photo = None
                if self._browser_integration_dlg.winfo_exists():
                    self._browser_integration_dlg.destroy()
            except Exception:
                pass
            self._browser_integration_dlg = None

        dlg = tk.Toplevel(self.root)
        self._browser_integration_dlg = dlg
        dlg.title(tr("browser_dlg_title", "🌐 Browser Integration & WebExtension Setup"))
        dlg.transient(self.root)
        dlg.grab_set = lambda: None
        dlg.grab_set_global = lambda: None
        try:
            dlg.lift()
            dlg.attributes("-topmost", True)
            dlg.focus_force()
        except Exception:
            pass

        dpi_scale = getattr(self, "dpi_scale", 1.0)
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        dlg_w = min(int(680 * dpi_scale), max(600, int(sw * 0.92)))
        dlg_h = min(int(740 * dpi_scale), max(640, int(sh * 0.90)))
        try:
            px = self.root.winfo_x()
            py = self.root.winfo_y()
            pw = self.root.winfo_width() or self.width
            ph = self.root.winfo_height() or self.height
        except Exception:
            px, py, pw, ph = 0, 0, self.width, self.height
        x = max(0, px + (pw - dlg_w) // 2)
        y = max(0, py + (ph - dlg_h) // 2)
        dlg.geometry(f"{dlg_w}x{dlg_h}+{x}+{y}")
        dlg.minsize(min(580, dlg_w), min(540, dlg_h))
        dlg.configure(bg=self.c_bg)

        # Apply application icon to dialog window
        ico_path = get_resource_path("app_icon.ico")
        png_path = get_resource_path("app_icon.png")
        if os.path.isfile(ico_path):
            try:
                dlg.iconbitmap(ico_path)
            except Exception:
                pass
        if os.path.isfile(png_path):
            try:
                from PIL import ImageTk
                dlg._browser_icon_photo = ImageTk.PhotoImage(file=png_path)
                dlg.iconphoto(True, dlg._browser_icon_photo)
                dlg.bind(
                    "<Destroy>",
                    lambda e: _detach_photo_tk(getattr(dlg, "_browser_icon_photo", None)) if e.widget == dlg else None,
                    add="+"
                )
            except Exception:
                pass

        # Header
        header = tk.Frame(dlg, bg=self.c_panel, height=44, padx=16)
        header.pack(fill=tk.X)
        header.pack_propagate(False)

        lbl_head = tk.Label(
            header,
            text=tr("browser_dlg_header", "🌐 BROWSER INTEGRATION & EXTENSION SETUP"),
            font=("Segoe UI", 10, "bold"),
            bg=self.c_panel,
            fg=self.c_accent
        )
        lbl_head.pack(side=tk.LEFT)

        btn_dlg_updates = tk.Button(
            header,
            text=tr("btn_check_updates", "🔄 Check for Updates"),
            font=("Segoe UI", 8, "bold"),
            bg=self.c_panel_light,
            fg=self.c_accent,
            relief="flat",
            activebackground=self.c_accent_dark,
            activeforeground="white",
            cursor="hand2",
            padx=10,
            pady=2,
            command=self.check_for_updates_manual
        )
        btn_dlg_updates.pack(side=tk.RIGHT, pady=8)

        # Main Body
        body = tk.Frame(dlg, bg=self.c_bg, padx=16, pady=12)
        body.pack(fill=tk.BOTH, expand=True)

        # 0. Zero-Install Universal Clipboard Sniffer Card (TDM Style)
        card_sniff = tk.Frame(body, bg=self.c_panel, padx=12, pady=10, highlightbackground=self.c_border, highlightthickness=1)
        card_sniff.pack(fill=tk.X, pady=(0, 10))

        lbl_sniff_t = tk.Label(card_sniff, text=tr("browser_card_sniffer_title", "📋 ZERO-INSTALL CLIPBOARD MONITOR (SD SMART CAPTURE — ALL BROWSERS)"), font=("Segoe UI", 8, "bold"), bg=self.c_panel, fg=self.c_success)
        lbl_sniff_t.pack(anchor="w")

        sniff_row = tk.Frame(card_sniff, bg=self.c_panel)
        sniff_row.pack(fill=tk.X, pady=(6, 0))

        lbl_sniff_desc = tk.Label(
            sniff_row,
            text=tr("browser_card_sniffer_desc", "Works 100% across ALL browsers (Chrome, Edge, Firefox, Brave, Opera, Safari) without any extension.\nJust right-click any link or video and choose 'Copy Link Address' — Smart Download catches it instantly!"),
            font=("Segoe UI", 8),
            bg=self.c_panel,
            fg=self.c_text_bright,
            justify="left"
        )
        lbl_sniff_desc.pack(side=tk.LEFT)

        def _update_dlg_sniff_btn():
            if self._clipboard_sniffer_active:
                btn_dlg_sniff.configure(text=tr("btn_sniffer_active", "📋 Sniffer: Active"), fg=self.c_success, bg=self.c_panel_light)
            else:
                btn_dlg_sniff.configure(text=tr("btn_sniffer_paused", "📋 Sniffer: Paused"), fg=self.c_text_muted, bg=self.c_panel)

        def _on_dlg_sniff_toggle():
            self.toggle_clipboard_sniffer()
            _update_dlg_sniff_btn()

        btn_dlg_sniff = tk.Button(
            sniff_row,
            text="",
            font=("Segoe UI", 8, "bold"),
            relief="flat",
            cursor="hand2",
            padx=10,
            command=_on_dlg_sniff_toggle
        )
        btn_dlg_sniff.pack(side=tk.RIGHT)
        _update_dlg_sniff_btn()

        # 1. Server Status Card
        card_server = tk.Frame(body, bg=self.c_panel, padx=12, pady=10, highlightbackground=self.c_border, highlightthickness=1)
        card_server.pack(fill=tk.X, pady=(0, 10))

        lbl_s_title = tk.Label(card_server, text=tr("browser_card_server_title", "LOCAL IPC LOOPBACK LISTENER"), font=("Segoe UI", 8, "bold"), bg=self.c_panel, fg=self.c_text_muted)
        lbl_s_title.pack(anchor="w")

        s_row = tk.Frame(card_server, bg=self.c_panel)
        s_row.pack(fill=tk.X, pady=(6, 0))

        lbl_status = tk.Label(s_row, text="", font=("Segoe UI", 9, "bold"), bg=self.c_panel)
        lbl_status.pack(side=tk.LEFT)

        def _update_server_status_label():
            if self.bridge_server and self.bridge_server.is_running:
                lbl_status.configure(text=tr("browser_server_active", f"● Active on http://{self.bridge_server.host}:{self.bridge_server.port}").format(host=self.bridge_server.host, port=self.bridge_server.port), fg=self.c_success)
                btn_toggle_server.configure(text=tr("browser_btn_stop_server", "⏹ Stop Server"), bg=self.c_danger)
            else:
                lbl_status.configure(text=tr("browser_server_stopped", "● Listener Stopped / Offline"), fg=self.c_danger)
                btn_toggle_server.configure(text=tr("browser_btn_start_server", "▶ Start Server"), bg=self.c_success)

        def _toggle_bridge():
            if self.bridge_server and self.bridge_server.is_running:
                self.bridge_server.stop()
            else:
                if not self.bridge_server:
                    self.bridge_server = BrowserBridgeServer(
                        port=DEFAULT_BRIDGE_PORT,
                        on_download=self._on_browser_download_received,
                        on_log=self.log
                    )
                self.bridge_server.start()
            _update_server_status_label()

        def _test_ping():
            port = self.bridge_server.port if self.bridge_server else DEFAULT_BRIDGE_PORT
            try:
                req = urllib.request.Request(f"http://127.0.0.1:{port}/ping")
                with urllib.request.urlopen(req, timeout=1.5) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode())
                        self.show_safe_info("Ping Successful", f"Loopback server is responding perfectly!\n\nApp: {data.get('app')}\nVersion: {data.get('version')}")
                        return
            except Exception as e:
                self.show_safe_error("Ping Failed", f"Could not reach loopback server:\n\n{e}")

        btn_test = tk.Button(
            s_row,
            text=tr("browser_btn_test_ping", "⚡ Test Ping"),
            font=("Segoe UI", 8, "bold"),
            bg=self.c_panel_light,
            fg=self.c_text_bright,
            relief="flat",
            cursor="hand2",
            command=_test_ping
        )
        btn_test.pack(side=tk.RIGHT, padx=(6, 0))

        btn_toggle_server = tk.Button(
            s_row,
            text="",
            font=("Segoe UI", 8, "bold"),
            fg="white",
            relief="flat",
            cursor="hand2",
            padx=10,
            command=_toggle_bridge
        )
        btn_toggle_server.pack(side=tk.RIGHT)
        _update_server_status_label()

        # 2. Windows Registry Native Messaging Integration Card
        card_reg = tk.Frame(body, bg=self.c_panel, padx=12, pady=10, highlightbackground=self.c_border, highlightthickness=1)
        card_reg.pack(fill=tk.X, pady=(0, 10))

        lbl_reg_title = tk.Label(card_reg, text=tr("browser_card_reg_title", "WINDOWS REGISTRY DIRECT BROWSER LINK (NATIVE MESSAGING)"), font=("Segoe UI", 8, "bold"), bg=self.c_panel, fg=self.c_accent)
        lbl_reg_title.pack(anchor="w")

        reg_row = tk.Frame(card_reg, bg=self.c_panel)
        reg_row.pack(fill=tk.X, pady=(6, 0))

        lbl_reg_status = tk.Label(reg_row, text="", font=("Segoe UI", 9, "bold"), bg=self.c_panel)
        lbl_reg_status.pack(side=tk.LEFT)

        def _update_reg_status_label():
            status = get_browser_reg_status()
            if status.get("is_registered"):
                chrome_str = "Chrome ✓" if status.get("chrome_registered") else "Chrome ✕"
                edge_str = "Edge ✓" if status.get("edge_registered") else "Edge ✕"
                lbl_reg_status.configure(text=tr("browser_reg_active", f"● Registry Active: {chrome_str}  {edge_str} (com.smartdownload.host)").format(chrome=chrome_str, edge=edge_str), fg=self.c_success)
                btn_reg.configure(text=tr("browser_btn_reregister", "🔄 Re-Register"), bg=self.c_panel_light)
            else:
                lbl_reg_status.configure(text=tr("browser_reg_inactive", "● Not Registered in Windows Registry"), fg=self.c_warning)
                btn_reg.configure(text=tr("browser_btn_register", "🔗 1-Click Register (Chrome & Edge)"), bg=self.c_success)

        def _on_register_click():
            res = register_native_host()
            _update_reg_status_label()
            if res.get("success"):
                self.show_safe_info(
                    "Registration Successful! 🚀",
                    "Native Messaging Host successfully linked in Windows Registry for Google Chrome and Microsoft Edge!\n\n"
                    f"Host Name: com.smartdownload.host\n"
                    f"Manifest: {res.get('manifest_path')}"
                )
            else:
                self.show_safe_error("Registration Error", f"Failed to register in Windows Registry:\n\n{res.get('error', 'Unknown error')}")

        def _on_unregister_click():
            unregister_native_host()
            _update_reg_status_label()
            self.show_safe_info("Unregistered", "Removed Native Messaging Host registry entries for Chrome & Edge.")

        btn_unreg = tk.Button(
            reg_row,
            text=tr("browser_btn_unregister", "Unregister"),
            font=("Segoe UI", 8),
            bg=self.c_panel_light,
            fg=self.c_text_muted,
            relief="flat",
            cursor="hand2",
            padx=8,
            command=_on_unregister_click
        )
        btn_unreg.pack(side=tk.RIGHT, padx=(6, 0))

        btn_reg = tk.Button(
            reg_row,
            text="",
            font=("Segoe UI", 8, "bold"),
            fg="white",
            relief="flat",
            cursor="hand2",
            padx=12,
            command=_on_register_click
        )
        btn_reg.pack(side=tk.RIGHT)
        _update_reg_status_label()

        # 3. Windows Startup Auto-Boot Card (Silent Background Mode)
        card_boot = tk.Frame(body, bg=self.c_panel, padx=12, pady=10, highlightbackground=self.c_border, highlightthickness=1)
        card_boot.pack(fill=tk.X, pady=(0, 10))

        lbl_boot_title = tk.Label(card_boot, text=tr("browser_card_boot_title", "🚀 WINDOWS STARTUP AUTO-BOOT (SILENT BACKGROUND MODE)"), font=("Segoe UI", 8, "bold"), bg=self.c_panel, fg=self.c_accent)
        lbl_boot_title.pack(anchor="w")

        boot_row = tk.Frame(card_boot, bg=self.c_panel)
        boot_row.pack(fill=tk.X, pady=(6, 0))

        lbl_boot_status = tk.Label(boot_row, text="", font=("Segoe UI", 9, "bold"), bg=self.c_panel)
        lbl_boot_status.pack(side=tk.LEFT)

        def _update_dlg_boot_status():
            try:
                if not dlg.winfo_exists() or not lbl_boot_status.winfo_exists():
                    return
            except Exception:
                return
            enabled = is_startup_enabled()
            if enabled:
                lbl_boot_status.configure(text=tr("browser_boot_enabled", "● Start with Windows: Enabled (Silent Background)"), fg=self.c_success)
                btn_dlg_boot.configure(text=tr("browser_btn_boot_enabled", "🚀 Start on Boot: Enabled"), fg=self.c_success, bg=self.c_panel_light)
            else:
                lbl_boot_status.configure(text=tr("browser_boot_disabled", "● Start with Windows: Disabled"), fg=self.c_warning)
                btn_dlg_boot.configure(text=tr("browser_btn_boot_disabled", "🚀 Start on Boot: Disabled"), fg=self.c_text_muted, bg=self.c_panel)

        self._update_dlg_startup_ui = _update_dlg_boot_status
        try:
            dlg.bind("<Destroy>", lambda e: setattr(self, "_update_dlg_startup_ui", None) if e.widget == dlg else None, add="+")
        except Exception:
            pass

        def _on_dlg_boot_toggle():
            self.toggle_startup_setting()
            _update_dlg_boot_status()

        btn_dlg_boot = tk.Button(
            boot_row,
            text="",
            font=("Segoe UI", 8, "bold"),
            relief="flat",
            cursor="hand2",
            padx=10,
            command=_on_dlg_boot_toggle
        )
        btn_dlg_boot.pack(side=tk.RIGHT)
        _update_dlg_boot_status()

        # 3b. Windows System Tray & Background Minimization Card
        card_tray = tk.Frame(body, bg=self.c_panel, padx=12, pady=10, highlightbackground=self.c_border, highlightthickness=1)
        card_tray.pack(fill=tk.X, pady=(0, 10))

        lbl_tray_title = tk.Label(card_tray, text=tr("browser_card_tray_title", "🔔 WINDOWS SYSTEM TRAY & BACKGROUND MINIMIZATION"), font=("Segoe UI", 8, "bold"), bg=self.c_panel, fg=self.c_accent)
        lbl_tray_title.pack(anchor="w")

        tray_row = tk.Frame(card_tray, bg=self.c_panel)
        tray_row.pack(fill=tk.X, pady=(6, 0))

        lbl_tray_status = tk.Label(tray_row, text="", font=("Segoe UI", 9, "bold"), bg=self.c_panel)
        lbl_tray_status.pack(side=tk.LEFT)

        def _update_dlg_tray_status():
            try:
                if not dlg.winfo_exists() or not lbl_tray_status.winfo_exists():
                    return
            except Exception:
                return
            enabled = getattr(self, "minimize_to_tray", True)
            if enabled:
                lbl_tray_status.configure(text=tr("browser_tray_enabled", "● Close (✕) Action: Minimize to System Tray"), fg=self.c_success)
                btn_dlg_tray.configure(text=tr("browser_btn_tray_enabled", "[✓] Minimize to System Tray on Close (✕)"), fg=self.c_success, bg=self.c_panel_light)
            else:
                lbl_tray_status.configure(text=tr("browser_tray_disabled", "● Close (✕) Action: Exit Application Completely"), fg=self.c_warning)
                btn_dlg_tray.configure(text=tr("browser_btn_tray_disabled", "[  ] Minimize to System Tray on Close (✕)"), fg=self.c_text_muted, bg=self.c_panel)

        self._update_dlg_tray_ui = _update_dlg_tray_status
        try:
            dlg.bind("<Destroy>", lambda e: (setattr(self, "_update_dlg_startup_ui", None), setattr(self, "_update_dlg_tray_ui", None)) if e.widget == dlg else None, add="+")
        except Exception:
            pass

        def _on_dlg_tray_toggle():
            self.toggle_minimize_to_tray_setting()
            _update_dlg_tray_status()

        btn_dlg_tray = tk.Button(
            tray_row,
            text="",
            font=("Segoe UI", 8, "bold"),
            relief="flat",
            cursor="hand2",
            padx=10,
            command=_on_dlg_tray_toggle
        )
        btn_dlg_tray.pack(side=tk.RIGHT)
        _update_dlg_tray_status()

        # 3c. Auto-Unpack Archives Card (AeroArchive Engine)
        card_unpack = tk.Frame(body, bg=self.c_panel, padx=12, pady=10, highlightbackground=self.c_border, highlightthickness=1)
        card_unpack.pack(fill=tk.X, pady=(0, 10))

        lbl_unpack_title = tk.Label(card_unpack, text=tr("browser_card_unpack_title", "📦 AUTOMATIC ARCHIVE EXTRACTION (AEROARCHIVE ENGINE)"), font=("Segoe UI", 8, "bold"), bg=self.c_panel, fg=self.c_accent)
        lbl_unpack_title.pack(anchor="w")

        unpack_row = tk.Frame(card_unpack, bg=self.c_panel)
        unpack_row.pack(fill=tk.X, pady=(6, 0))

        lbl_unpack_status = tk.Label(unpack_row, text="", font=("Segoe UI", 9, "bold"), bg=self.c_panel)
        lbl_unpack_status.pack(side=tk.LEFT)

        def _update_dlg_unpack_status():
            try:
                if not dlg.winfo_exists() or not lbl_unpack_status.winfo_exists():
                    return
            except Exception:
                return
            enabled = get_setting("auto_unpack_archives", False)
            if enabled:
                lbl_unpack_status.configure(text=tr("browser_unpack_enabled", "● Auto-Unpack: Enabled"), fg=self.c_success)
                btn_dlg_unpack.configure(text=tr("browser_btn_unpack_enabled", "[✓] Auto-Unpack Archives after Download"), fg=self.c_success, bg=self.c_panel_light)
            else:
                lbl_unpack_status.configure(text=tr("browser_unpack_disabled", "● Auto-Unpack: Disabled"), fg=self.c_warning)
                btn_dlg_unpack.configure(text=tr("browser_btn_unpack_disabled", "[  ] Auto-Unpack Archives after Download"), fg=self.c_text_muted, bg=self.c_panel)

        def _on_dlg_unpack_toggle():
            cur = get_setting("auto_unpack_archives", False)
            set_setting("auto_unpack_archives", not cur)
            _update_dlg_unpack_status()

        btn_dlg_unpack = tk.Button(
            unpack_row,
            text="",
            font=("Segoe UI", 8, "bold"),
            relief="flat",
            cursor="hand2",
            padx=10,
            command=_on_dlg_unpack_toggle
        )
        btn_dlg_unpack.pack(side=tk.RIGHT)
        _update_dlg_unpack_status()

        # 4. Extension Directory Card
        if getattr(sys, "frozen", False):
            exe_dir = os.path.dirname(os.path.abspath(sys.executable))
            persistent_ext_dir = os.path.join(exe_dir, "extension")
            if hasattr(sys, "_MEIPASS"):
                bundled_ext = os.path.join(sys._MEIPASS, "extension")
                if os.path.isdir(bundled_ext):
                    try:
                        shutil.copytree(bundled_ext, persistent_ext_dir, dirs_exist_ok=True)
                    except Exception:
                        pass
            ext_dir = persistent_ext_dir if os.path.isdir(persistent_ext_dir) else os.path.join(getattr(sys, "_MEIPASS", exe_dir), "extension")
        else:
            base_app_dir = os.path.dirname(os.path.abspath(__file__))
            ext_dir = os.path.join(base_app_dir, "extension")

        card_ext = tk.Frame(body, bg=self.c_panel, padx=12, pady=10, highlightbackground=self.c_border, highlightthickness=1)
        card_ext.pack(fill=tk.X, pady=(0, 10))

        lbl_e_title = tk.Label(card_ext, text=tr("browser_card_ext_title", "WEBEXTENSION ARTIFACT (MANIFEST V3)"), font=("Segoe UI", 8, "bold"), bg=self.c_panel, fg=self.c_text_muted)
        lbl_e_title.pack(anchor="w")

        e_row = tk.Frame(card_ext, bg=self.c_panel)
        e_row.pack(fill=tk.X, pady=(4, 0))

        lbl_path = tk.Label(e_row, text=ext_dir, font=("Consolas", 8), bg=self.c_input_bg, fg=self.c_accent, padx=6, pady=4, anchor="w")
        lbl_path.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))

        def _open_folder():
            if os.path.exists(ext_dir):
                if IS_WINDOWS:
                    os.startfile(ext_dir)
                else:
                    import subprocess
                    subprocess.Popen(["xdg-open", ext_dir])

        btn_open = tk.Button(
            e_row,
            text=tr("browser_btn_open_folder", "📂 Open Folder"),
            font=("Segoe UI", 8, "bold"),
            bg=self.c_accent_dark,
            fg="white",
            relief="flat",
            cursor="hand2",
            command=_open_folder
        )
        btn_open.pack(side=tk.RIGHT)

        # 3. Installation Guide Notebook
        nb = ttk.Notebook(body, style="Custom.TNotebook")
        nb.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # Chrome / Brave tab
        tab_chrome = tk.Frame(nb, bg=self.c_panel, padx=12, pady=10)
        nb.add(tab_chrome, text=tr("browser_tab_chrome", " Chrome & Brave "))

        chrome_txt = tr(
            "browser_guide_chrome",
            "1. Open Chrome or Brave and type chrome://extensions in the address bar.\n"
            "2. Turn ON 'Developer mode' using the toggle in the top-right corner.\n"
            "3. Click the 'Load unpacked' button at the top-left.\n"
            "4. Select the extension directory displayed above.\n"
            "5. The ⚡ Smart Download icon will appear in your extensions bar!"
        )
        tk.Label(tab_chrome, text=chrome_txt, font=("Segoe UI", 9), bg=self.c_panel, fg=self.c_text_bright, justify="left").pack(anchor="w")

        # Edge tab
        tab_edge = tk.Frame(nb, bg=self.c_panel, padx=12, pady=10)
        nb.add(tab_edge, text=tr("browser_tab_edge", " Microsoft Edge "))

        edge_txt = tr(
            "browser_guide_edge",
            "1. Open Edge and navigate to edge://extensions in the address bar.\n"
            "2. Turn ON 'Developer mode' in the left-hand navigation sidebar.\n"
            "3. Click the 'Load unpacked' button.\n"
            "4. Select the extension directory displayed above.\n"
            "5. Pin the extension to your toolbar for one-click access."
        )
        tk.Label(tab_edge, text=edge_txt, font=("Segoe UI", 9), bg=self.c_panel, fg=self.c_text_bright, justify="left").pack(anchor="w")

        # Firefox tab
        tab_firefox = tk.Frame(nb, bg=self.c_panel, padx=12, pady=10)
        nb.add(tab_firefox, text=tr("browser_tab_firefox", " Mozilla Firefox "))

        firefox_txt = tr(
            "browser_guide_firefox",
            "1. Open Firefox and type about:debugging#/runtime/this-firefox in the address bar.\n"
            "2. Click the 'Load Temporary Add-on...' button.\n"
            "3. Select the 'manifest.json' file inside the extension folder.\n"
            "4. The extension is immediately loaded and connects to Smart Download."
        )
        tk.Label(tab_firefox, text=firefox_txt, font=("Segoe UI", 9), bg=self.c_panel, fg=self.c_text_bright, justify="left").pack(anchor="w")

        # Close button
        btn_close = tk.Button(
            body,
            text=tr("browser_btn_close", "Close"),
            font=("Segoe UI", 9, "bold"),
            bg=self.c_panel_light,
            fg=self.c_text_bright,
            relief="flat",
            cursor="hand2",
            padx=16,
            pady=4,
            command=dlg.destroy
        )
        btn_close.pack(side=tk.RIGHT)

    def _on_pause_resume(self):
        if not self.engine:
            return
        if self.engine.is_paused:
            self.engine.resume()
            self.btn_pause.configure(text=tr("btn_pause", "⏸ Pause"), bg=self.c_panel_light)
        else:
            self.engine.pause()
            self.btn_pause.configure(text=tr("btn_resume", "▶ Resume"), bg=self.c_warning)
            if hasattr(self, "btn_refresh_link"):
                self.btn_refresh_link.configure(state="normal", bg=self.c_panel_light, fg=self.c_accent)
            try:
                dl_url = (self.engine.url if self.engine and getattr(self.engine, "url", None) else self.entry_url.get()).strip()
                dl_dest = (self.engine.dest_path if self.engine and getattr(self.engine, "dest_path", None) else self.entry_dest.get()).strip()
                if dl_url and dl_dest and hasattr(self, "history_manager") and self.history_manager:
                    self.history_manager.add_or_update_entry(
                        url=dl_url,
                        file_path=dl_dest,
                        size_bytes=0,
                        status="Paused",
                        elapsed_sec=0.0
                    )
                    self._refresh_history_table()
            except Exception:
                pass

    def _on_cancel_download(self):
        if hasattr(self, "_yt_cancel_event"):
            self._yt_cancel_event.set()
        if hasattr(self, "_quality_modal") and self._quality_modal:
            try:
                if self._quality_modal.winfo_exists():
                    try:
                        self._quality_modal.grab_release()
                    except Exception:
                        pass
                    self._quality_modal.destroy()
            except Exception:
                pass
            self._quality_modal = None
        if hasattr(self, "_active_modal_dialog") and self._active_modal_dialog:
            try:
                if self._active_modal_dialog.winfo_exists():
                    try:
                        self._active_modal_dialog.grab_release()
                    except Exception:
                        pass
                    self._active_modal_dialog.destroy()
            except Exception:
                pass
            self._active_modal_dialog = None
        if hasattr(self, "_refresh_modal") and self._refresh_modal:
            try:
                if self._refresh_modal.winfo_exists():
                    self._refresh_modal.destroy()
            except Exception:
                pass
            self._refresh_modal = None
        if self.engine:
            self.engine.cancel()
        self.btn_start.configure(state="normal")
        self.btn_pause.configure(state="disabled", text=tr("btn_pause", "⏸ Pause"), bg=self.c_panel_light)
        self.btn_cancel.configure(state="disabled")
        if hasattr(self, "btn_refresh_link"):
            self.btn_refresh_link.configure(state="disabled", bg=self.c_panel_light, fg=self.c_text_muted)
        self.card_size.configure(text=tr("status_ready", "Ready"))
        self.log("[CANCEL] Operation cancelled by user.")

    def _engine_progress_cb(self, downloaded: int, total: int, speed: float, eta: str, active_chunks: int):
        def _update():
            # Percentage
            pct = (downloaded / total * 100.0) if total > 0 else 0.0
            self._draw_main_progress(pct)

            # Speed
            if speed >= 1024 * 1024:
                speed_str = f"{speed / (1024*1024):.2f} MB/s"
            elif speed >= 1024:
                speed_str = f"{speed / 1024:.1f} KB/s"
            else:
                speed_str = f"{int(speed)} B/s"
            self.card_speed.configure(text=speed_str)

            # Size
            def _fmt_size(b):
                if b >= 1024 * 1024 * 1024:
                    return f"{b / (1024**3):.2f} GB"
                if b >= 1024 * 1024:
                    return f"{b / (1024**2):.1f} MB"
                if b >= 1024:
                    return f"{b / 1024:.1f} KB"
                return f"{b} B"

            if total > 0:
                size_str = f"{_fmt_size(downloaded)} / {_fmt_size(total)} ({pct:.1f}%)"
            else:
                size_str = f"{_fmt_size(downloaded)} (Streaming...)"
            self.card_size.configure(text=size_str)

            # ETA
            self.card_eta.configure(text=eta)

            # Active Threads
            if hasattr(self.engine, "get_chunks_snapshot"):
                total_chunks = len(self.engine.get_chunks_snapshot())
            elif self.engine:
                total_chunks = len(self.engine.chunks)
            else:
                total_chunks = 0
            self.card_threads.configure(text=f"{active_chunks} Active ({total_chunks} Total)")

        try:
            if self.root.winfo_exists():
                self.root.after(0, _update)
        except Exception:
            pass

    def _engine_chunk_update_cb(self):
        # Triggered on chunk state transitions or splits
        try:
            if self.root.winfo_exists():
                self.root.after(0, self._refresh_chunk_displays)
        except Exception:
            pass

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

    def _gui_refresh_tick(self):
        """Periodic tick ensuring smooth chunk visualization animation and processing queued thread tasks."""
        if getattr(self, "_closing", False):
            return
        try:
            if not hasattr(self, "root") or not self.root or not self.root.winfo_exists():
                return
        except Exception:
            return

        self._drain_dispatch_queue()

        if self.engine and self.engine.is_running and not self.engine.is_paused:
            try:
                self._refresh_chunk_displays()
            except Exception:
                pass
        try:
            if not getattr(self, "_closing", False) and self.root.winfo_exists():
                self._refresh_job = self.root.after(250, self._gui_refresh_tick)
        except Exception:
            pass

    def _engine_complete_cb(self, path: str, total_bytes: int, elapsed: float, suppress_dialog: bool = False):
        def _done():
            self._draw_main_progress(100.0)
            self._refresh_chunk_displays()
            self.btn_start.configure(state="normal")
            self.btn_pause.configure(state="disabled", text=tr("btn_pause", "⏸ Pause"), bg=self.c_panel_light)
            self.btn_cancel.configure(state="disabled")
            if hasattr(self, "btn_refresh_link"):
                self.btn_refresh_link.configure(state="disabled", bg=self.c_panel_light, fg=self.c_text_muted)
            self.log(f"[COMPLETE] Download complete: {os.path.basename(path)} ({total_bytes:,} bytes in {elapsed:.1f}s)")
            try:
                dl_url = (self.engine.url if self.engine and getattr(self.engine, "url", None) else self.entry_url.get()).strip()
                if hasattr(self, "history_manager") and self.history_manager:
                    self.history_manager.add_or_update_entry(
                        url=dl_url,
                        file_path=path,
                        size_bytes=total_bytes,
                        status="Completed",
                        elapsed_sec=elapsed
                    )
                    self._refresh_history_table()
            except Exception:
                pass
            if hasattr(self, "_download_queue") and self._download_queue:
                q_url, q_dest, q_conn, q_limit = self._download_queue.pop(0)
                self.log(f"[QUEUE] Launching next queued download: {os.path.basename(q_dest)} ({len(self._download_queue)} remaining)")
                self._start_download_with_engine(q_url, q_dest, q_conn, q_limit)

            if suppress_dialog:
                return
            msg = (
                f"{tr('dialog_complete_msg_verified', 'File verified & assembled without corruption!')}\n\n"
                f"{tr('dialog_complete_msg_saved', 'Saved to:')} {path}\n"
                f"{tr('dialog_complete_msg_size', 'Size:')} {total_bytes:,} bytes\n"
                f"{tr('dialog_complete_msg_time', 'Total Time:')} {elapsed:.1f} seconds"
            )
            complete_title = tr("toast_completed_title", "Download Completed Successfully! 🚀")
            if hasattr(self, "show_safe_info"):
                self.show_safe_info(complete_title, msg)
            elif getattr(messagebox.showinfo, "_mock_name", None) or hasattr(messagebox.showinfo, "mock"):
                messagebox.showinfo(complete_title, msg)
            else:
                try:
                    if hasattr(self, "root") and self.root and self.root.winfo_exists():
                        SafeModalDialog(
                            self.root,
                            title=complete_title,
                            message=msg,
                            dialog_type="info",
                            theme=getattr(self, "_theme_dict", lambda: None)()
                        )
                except Exception:
                    pass
        try:
            if self.root.winfo_exists():
                self.root.after(0, _done)
        except Exception:
            pass

    def _engine_error_cb(self, error_msg: str):
        def _err():
            if hasattr(self, "_quality_modal") and self._quality_modal:
                try:
                    if self._quality_modal.winfo_exists():
                        try:
                            self._quality_modal.grab_release()
                        except Exception:
                            pass
                        self._quality_modal.destroy()
                except Exception:
                    pass
                self._quality_modal = None
            if hasattr(self, "btn_start"):
                try:
                    self.btn_start.configure(state="normal")
                except Exception:
                    pass
            if hasattr(self, "btn_pause"):
                try:
                    self.btn_pause.configure(state="disabled", text=tr("btn_pause", "⏸ Pause"), bg=getattr(self, "c_panel_light", "#334155"))
                except Exception:
                    pass
            if hasattr(self, "btn_cancel"):
                try:
                    self.btn_cancel.configure(state="disabled")
                except Exception:
                    pass
            is_expired = any(k in str(error_msg) for k in ("401", "403", "410", "Forbidden", "Expired", "Unauthorized"))
            if hasattr(self, "btn_refresh_link"):
                try:
                    if is_expired:
                        self.btn_refresh_link.configure(state="normal", bg=getattr(self, "c_warning", "#f59e0b"), fg="#0f172a")
                    else:
                        self.btn_refresh_link.configure(state="normal", bg=getattr(self, "c_panel_light", "#334155"), fg=getattr(self, "c_accent", "#38bdf8"))
                except Exception:
                    pass
            if hasattr(self, "card_size"):
                try:
                    self.card_size.configure(text=tr("status_ready", "Ready"))
                except Exception:
                    pass
            if hasattr(self, "log"):
                try:
                    self.log(f"[ERROR] Download Error: {error_msg}")
                except Exception:
                    pass

            try:
                dl_url = (self.engine.url if self.engine and getattr(self.engine, "url", None) else self.entry_url.get()).strip()
                dl_dest = (self.engine.dest_path if self.engine and getattr(self.engine, "dest_path", None) else self.entry_dest.get()).strip()
                if dl_url and dl_dest and hasattr(self, "history_manager") and self.history_manager:
                    self.history_manager.add_or_update_entry(
                        url=dl_url,
                        file_path=dl_dest,
                        size_bytes=0,
                        status="Failed",
                        elapsed_sec=0.0
                    )
                    self._refresh_history_table()
            except Exception:
                pass

            if is_expired:
                msg = (
                    f"{tr('dialog_expired_msg1', 'Download stopped: Server rejected session (HTTP 401/403/410).')}\n\n"
                    f"{tr('dialog_expired_details', 'Details:')} {error_msg}\n\n"
                    f"{tr('dialog_expired_msg2', '💡 All partially downloaded chunk files are safely preserved on disk.')}\n"
                    f"{tr('dialog_expired_msg3', 'Would you like to refresh the download link now to resume?')}"
                )
                if hasattr(self, "ask_safe_yesno"):
                    def _on_yes_refresh():
                        self._open_refresh_link_dialog()
                    self.ask_safe_yesno(
                        tr("dialog_expired_title", "Download Link Expired ⚠️"),
                        msg,
                        on_yes=_on_yes_refresh
                    )
                    return

            msg = f"{tr('dialog_error_prefix', 'Encountered error during download:')}\n\n{error_msg}"
            err_title = tr("dialog_error_title", "Download Error")
            if hasattr(self, "show_safe_error"):
                self.show_safe_error(err_title, msg)
            elif getattr(messagebox.showerror, "_mock_name", None) or hasattr(messagebox.showerror, "mock"):
                messagebox.showerror(err_title, msg)
            else:
                try:
                    if hasattr(self, "root") and self.root and self.root.winfo_exists():
                        SafeModalDialog(
                            self.root,
                            title=err_title,
                            message=msg,
                            dialog_type="error",
                            theme=getattr(self, "_theme_dict", lambda: None)()
                        )
                except Exception:
                    pass
        try:
            if hasattr(self, "root") and self.root and self.root.winfo_exists():
                self.root.after(0, _err)
            else:
                _err()
        except Exception:
            pass

    def _open_refresh_link_dialog(self):
        """Displays sleek, dark-themed, grab-free Refresh Link modal dialog."""
        current_url = ""
        if self.engine and getattr(self.engine, "url", None):
            current_url = self.engine.url
        elif hasattr(self, "entry_url"):
            current_url = self.entry_url.get().strip()

        total_size = 0
        downloaded_bytes = 0
        if self.engine:
            total_size = getattr(self.engine, "total_size", 0)
            chunks = getattr(self.engine, "chunks", [])
            downloaded_bytes = sum(c.downloaded_bytes for c in chunks) if chunks else 0

        dest_path = self.entry_dest.get().strip() if hasattr(self, "entry_dest") else ""
        filename = os.path.basename(dest_path) if dest_path else "download.bin"
        expected_ranges = getattr(self.engine, "supports_ranges", True) if self.engine else True

        if hasattr(self, "_refresh_modal") and self._refresh_modal:
            try:
                if self._refresh_modal.winfo_exists():
                    self._refresh_modal.destroy()
            except Exception:
                pass
            self._refresh_modal = None

        self._refresh_modal = RefreshLinkModal(
            parent=self.root,
            old_url=current_url,
            total_size=total_size,
            downloaded_bytes=downloaded_bytes,
            filename=filename,
            theme=self._theme_dict(),
            on_success=self._on_link_refreshed_success,
            expected_ranges=expected_ranges
        )

    def _on_link_refreshed_success(self, new_url: str, headers: Optional[Dict[str, str]] = None):
        """Callback invoked when user confirms a validated new download URL."""
        try:
            if hasattr(self, "entry_url"):
                self.entry_url.delete(0, tk.END)
                self.entry_url.insert(0, new_url)

            if self.engine:
                self.engine.refresh_link(new_url, headers=headers, auto_resume=True)
                if hasattr(self, "btn_start"):
                    self.btn_start.configure(state="disabled")
                if hasattr(self, "btn_pause"):
                    self.btn_pause.configure(state="normal", text=tr("btn_pause", "⏸ Pause"), bg=self.c_panel_light)
                if hasattr(self, "btn_cancel"):
                    self.btn_cancel.configure(state="normal")
                if hasattr(self, "btn_refresh_link"):
                    self.btn_refresh_link.configure(state="normal", bg=self.c_panel_light, fg=self.c_accent)
                self.log(f"[REFRESH] Link refreshed successfully: {new_url}")
                self.show_safe_info(
                    "Link Refreshed Successfully 🔄",
                    f"Download address updated to:\n{new_url}\n\nResuming download seamlessly from existing progress without losing data!"
                )
            else:
                self.log(f"[REFRESH] URL updated: {new_url}")
                self.show_safe_info("URL Updated", f"Download URL updated to:\n{new_url}\n\nClick '▶ Start Download' to begin.")
        except Exception as e:
            self.show_safe_error("Refresh Link Failed", f"Could not refresh download link:\n{e}")

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
                self.log(f"Failed to open folder: {e}")

    # ==================================================================================
    # AUTO-UPDATER & MANUAL UPDATE CHECK (Smart Download & yt-dlp Engine)
    # ==================================================================================

    def _start_auto_update_check(self):
        """Runs a non-blocking background check for yt-dlp and Smart Download updates on startup."""
        self._update_check_job = None
        if getattr(self, "_closing", False) or os.environ.get("SD_DISABLE_AUTO_UPDATE") == "1":
            return

        weak_self = weakref.ref(self)

        def _safe_log(msg: str):
            g = weak_self()
            if g is not None and not getattr(g, "_closing", False):
                g.log(msg)

        def _worker():
            g = weak_self()
            if g is None or getattr(g, "_closing", False):
                return
            del g
            try:
                # 1. Silently check & update yt-dlp engine in background
                YtDlpAutoUpdater(on_log=_safe_log).update()
            except Exception:
                pass
            g = weak_self()
            if g is None or getattr(g, "_closing", False):
                return
            del g
            try:
                # 2. Check GitHub Releases for newer Smart Download (SD) version
                info = AppAutoUpdater(current_version=APP_VERSION, on_log=_safe_log).check_for_update()
                g = weak_self()
                if g is not None and info.get("update_available") and not getattr(g, "_closing", False):
                    latest = info.get("latest_version", "")
                    g.log(f"[UPDATER] New Smart Download version v{latest} is available (current: v{APP_VERSION}).")
                    g.dispatch_to_main_thread(lambda: (weak_self() and weak_self()._show_update_dialog(info)))
                del g
            except Exception:
                pass

        t = threading.Thread(target=_worker, daemon=True, name="AutoUpdateCheckThread")
        t.start()

    def check_for_updates_manual(self):
        """Triggered manually by user clicking '🔄 Check for Updates'."""
        if getattr(self, "_closing", False):
            return
        self.log("[UPDATER] Checking for Smart Download and yt-dlp updates...")
        if hasattr(self, "btn_check_updates") and self.btn_check_updates:
            try:
                if self.btn_check_updates.winfo_exists():
                    self.btn_check_updates.configure(text=tr("btn_checking_updates", "⏳ Checking..."), state="disabled")
            except Exception:
                pass

        weak_self = weakref.ref(self)

        def _safe_log(msg: str):
            g = weak_self()
            if g is not None and not getattr(g, "_closing", False):
                g.log(msg)

        def _worker():
            app_info = AppAutoUpdater(current_version=APP_VERSION, on_log=_safe_log).check_for_update()
            yt_res = None
            try:
                yt_updater = YtDlpAutoUpdater(on_log=_safe_log)
                yt_info = yt_updater.check_for_update()
                if yt_info.get("update_available"):
                    yt_res = yt_updater.update()
                else:
                    yt_res = {
                        "updated": False,
                        "version": yt_info.get("latest_version") or yt_info.get("current_version", get_ytdlp_version()),
                    }
            except Exception:
                yt_res = {"updated": False, "version": get_ytdlp_version()}

            def _on_done():
                g = weak_self()
                if g is None or getattr(g, "_closing", False):
                    return
                if hasattr(g, "btn_check_updates") and g.btn_check_updates:
                    try:
                        if g.btn_check_updates.winfo_exists():
                            g.btn_check_updates.configure(text=tr("btn_check_updates", "🔄 Check for Updates"), state="normal")
                    except Exception:
                        pass

                if app_info.get("update_available"):
                    g._show_update_dialog(app_info)
                    return

                if app_info.get("error"):
                    g.show_safe_error(
                        "Update Check Failed",
                        f"Could not check GitHub Releases for updates:\n\n{app_info.get('error')}"
                    )
                    return

                yt_ver = (yt_res or {}).get("version") or (yt_res or {}).get("new_version") or get_ytdlp_version()
                if (yt_res or {}).get("updated"):
                    yt_line = f"🎬 YouTube Engine (yt-dlp): Updated to v{yt_ver} ✅"
                else:
                    yt_line = f"🎬 YouTube Engine (yt-dlp): v{yt_ver} (Up to Date ✅)"

                g.show_safe_info(
                    "Up to Date ✅",
                    f"You are running the latest version of Smart Download (SD)!\n\n"
                    f"🚀 Application Version: v{APP_VERSION}\n"
                    f"{yt_line}"
                )

            g = weak_self()
            if g is not None and not getattr(g, "_closing", False):
                g.dispatch_to_main_thread(_on_done)
            del g

        t = threading.Thread(target=_worker, daemon=True, name="ManualUpdateCheckThread")
        t.start()

    def _show_update_dialog(self, update_info: Dict[str, Any]) -> Optional[AppUpdateModal]:
        """Displays the non-intrusive dark-themed AppUpdateModal when a newer version is found."""
        if getattr(self, "_closing", False):
            return None
        try:
            if not hasattr(self, "root") or not self.root or not self.root.winfo_exists():
                return None
        except Exception:
            return None

        if hasattr(self, "_update_modal") and self._update_modal:
            try:
                if self._update_modal.winfo_exists():
                    self._update_modal.destroy()
            except Exception:
                pass
            self._update_modal = None

        self._update_modal = AppUpdateModal(
            parent=self.root,
            update_info=update_info,
            theme=self._theme_dict(),
            parent_app=self,
            on_log=self.log,
            on_exit_app=lambda: self._on_close(force_exit=True)
        )
        return self._update_modal


def main():
    import multiprocessing
    multiprocessing.freeze_support()

    # CLI handler for test mode or binary verification
    if "--test-startup" in sys.argv:
        try:
            from ..services import updater_service as updater
            from ..services import youtube_service as youtube_resolver
            from ..services.browser import bridge_server as browser_bridge
            from ..services.browser import native_host as native_messaging_host
            from ..services.browser import registry as register_browser
        except ImportError:
            import updater
            import youtube_resolver
            import browser_bridge
            import native_messaging_host
            import register_browser
        import yt_dlp
        ico = get_resource_path("app_icon.ico")
        png = get_resource_path("app_icon.png")
        if not os.path.isfile(ico) or not os.path.isfile(png):
            os._exit(2)
        if not youtube_resolver.is_ytdlp_available():
            os._exit(1)
        os._exit(0)

    # CLI handler for Chrome/Edge Native Messaging Host execution
    if (
        "--native-host" in sys.argv
        or "--native-messaging-host" in sys.argv
        or any(arg.startswith("chrome-extension://") or arg.startswith("edge-extension://") for arg in sys.argv[1:])
    ):
        try:
            from ..services.browser.native_host import run_host
        except ImportError:
            from native_messaging_host import run_host
        run_host()
        return

    # CLI handler for browser registration
    if "--register-browser" in sys.argv:
        res = check_and_register_browser(force=True)
        print(json.dumps(res, indent=2))
        return

    if "--unregister-browser" in sys.argv:
        res = unregister_native_host()
        print(json.dumps(res, indent=2))
        return

    # Check for CLI download URLs (e.g. TurboDownloader.exe https://example.com/file.zip)
    cli_url = None
    for arg in sys.argv[1:]:
        if not arg.startswith("-") and not arg.startswith("/"):
            if arg.startswith("http://") or arg.startswith("https://") or arg.startswith("ftp://"):
                cli_url = arg.strip()
                break

    # Check for background / minimized startup (case-insensitive)
    start_in_background = any(arg.lower() in ("--background", "-background", "/background",
                                              "--minimized", "-minimized", "/minimized")
                              for arg in sys.argv[1:])

    # Single-instance check: if already running, forward URL or wake window, then exit
    if not any(arg in sys.argv for arg in ("--force-new-instance", "--multi-instance")):
        if start_in_background:
            if notify_running_instance(url=cli_url, show=False):
                sys.exit(0)
        else:
            if notify_running_instance(url=cli_url, show=True):
                sys.exit(0)

    # Ensure Windows High-DPI Awareness is active before root creation
    enable_high_dpi_awareness()

    root = tk.Tk()
    root.title("Smart Download (SD)")

    # Set application icon on root window
    ico_path = get_resource_path("app_icon.ico")
    png_path = get_resource_path("app_icon.png")
    if os.path.isfile(ico_path):
        try:
            root.iconbitmap(ico_path)
        except Exception:
            pass
    if os.path.isfile(png_path):
        try:
            from PIL import ImageTk
            _ico_img = ImageTk.PhotoImage(file=png_path)
            root.iconphoto(True, _ico_img)
        except Exception:
            pass

    if start_in_background:
        try:
            root.withdraw()
        except Exception:
            pass

    app = ModernFramelessGUI(root, start_hidden=start_in_background, initial_url=cli_url)
    if start_in_background:
        try:
            root.withdraw()
        except Exception:
            pass

    root.mainloop()

if __name__ == "__main__":
    main()



# Backward-compatible and modern engine/GUI aliases
SmartDownloadEngine = TurboDownloadEngine
TurboDownloaderGUI = ModernFramelessGUI
DownloaderApp = ModernFramelessGUI
SmartDownloadGUI = ModernFramelessGUI

