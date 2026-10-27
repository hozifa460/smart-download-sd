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
    Image = None  # type: ignore
    ImageTk = None  # type: ignore

from ..config import (
    get_resource_path,
    get_config_dir,
    get_app_config_dir,
    get_settings_file_path,
    is_test_environment,
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

from .modals.browser_settings_modal import BrowserSettingsModalMixin
from .panels.history_panel import HistoryPanelMixin
from .panels.chunks_panel import ChunksPanelMixin
from .panels.inputs_panel import InputsPanelMixin
from .panels.media_options_bar import MediaOptionsBarMixin
from .controllers.clipboard_controller import ClipboardControllerMixin
from .controllers.update_controller import UpdateControllerMixin
from .controllers.download_controller import DownloadControllerMixin
from .controllers.settings_controller import SettingsControllerMixin
from .controllers.window_controller import WindowChromeMixin


class ModernFramelessGUI(
    BrowserSettingsModalMixin,
    HistoryPanelMixin,
    ChunksPanelMixin,
    InputsPanelMixin,
    MediaOptionsBarMixin,
    ClipboardControllerMixin,
    UpdateControllerMixin,
    DownloadControllerMixin,
    SettingsControllerMixin,
    WindowChromeMixin,
):
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
        self._fetch_cancel_event = threading.Event()
        self._quality_modal: Optional[tk.Toplevel] = None
        self._confirm_modal: Optional[tk.Toplevel] = None
        self._candidates_modal: Optional[tk.Toplevel] = None
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
        if os.environ.get("SD_DISABLE_AUTO_REGISTER") != "1" and not is_test_environment():
            self._start_browser_self_registration()

        self._download_queue: List[Tuple[str, str, int, float]] = []
        self._candidates_modal: Optional[tk.Toplevel] = None
        LocalizationManager.get_instance().register_observer(self._update_ui_language)

        # Non-blocking background check for application and yt-dlp updates
        if os.environ.get("SD_DISABLE_AUTO_UPDATE") != "1" and not is_test_environment():
            try:
                self._update_check_job = self.root.after(2500, self._start_auto_update_check)
            except Exception:
                pass

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
            import updater  # type: ignore
            import youtube_resolver  # type: ignore
            import browser_bridge  # type: ignore
            import native_messaging_host  # type: ignore
            import register_browser  # type: ignore
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
            from native_messaging_host import run_host  # type: ignore
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
SmartDownloadApp = ModernFramelessGUI
