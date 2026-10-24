"""
Backward compatibility entry-point for Smart Download (SD).
The application logic has been refactored into modular packages under src/smart_download/.
This entry-point re-exports all symbols to maintain 100% backward compatibility
with all existing tests, build scripts, and external tools.
"""
import sys
import os
import time

# Fast-path for --test-startup verification
if "--test-startup" in sys.argv:
    t0 = time.time()
    _src_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
    if os.path.isdir(_src_dir) and _src_dir not in sys.path:
        sys.path.insert(0, _src_dir)
    import smart_download.services.youtube_service as youtube_resolver
    t1 = time.time()
    import smart_download.services.browser.bridge_server as browser_bridge
    t2 = time.time()
    import smart_download.services.browser.native_host as native_messaging_host
    t3 = time.time()
    import smart_download.services.browser.registry as register_browser
    t4 = time.time()
    import yt_dlp
    t5 = time.time()
    avail = youtube_resolver.is_ytdlp_available()
    t6 = time.time()
    try:
        import tempfile
        log_path = os.path.join(tempfile.gettempdir(), "test_startup_timing.txt")
        with open(log_path, "w") as f:
            f.write(f"ytdlp_res={t1-t0:.2f}s, bridge={t2-t1:.2f}s, nat={t3-t2:.2f}s, reg={t4-t3:.2f}s, ytdlp={t5-t4:.2f}s, avail={t6-t5:.2f}s, total={t6-t0:.2f}s\n")
    except Exception:
        pass
    if not avail:
        os._exit(1)
    os._exit(0)

_src_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if os.path.isdir(_src_dir) and _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

# Initialize DPI awareness
from smart_download.utils.dpi import enable_high_dpi_awareness, get_windows_work_area
enable_high_dpi_awareness()

# Re-export all config & constants
from smart_download.config import (
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
    get_resource_path,
    get_config_dir,
    get_app_config_dir,
    get_settings_file_path,
    load_settings,
    save_settings,
    get_setting,
    set_setting,
)

# Re-export i18n
from smart_download.locales.i18n import (
    LocalizationManager,
    tr,
    get_current_language,
    set_current_language,
    TRANSLATIONS,
)

# Re-export utils
from smart_download.utils.clipboard import _win32_clipboard_get, get_clipboard_text
from smart_download.utils.url_utils import (
    COMMON_DOWNLOAD_EXTENSIONS,
    WEB_SCRIPT_EXTENSIONS,
    is_downloadable_url,
    clean_download_filename,
    derive_download_filename,
    is_potential_html_url,
    parse_filename_from_cd_header,
    parse_speed_limit,
)
from smart_download.utils.file_ops import (
    MagicBytesDetector,
    calculate_file_integrity,
    auto_unpack_archive,
    get_file_category_and_icon,
    CATEGORY_SUBFOLDERS,
    resolve_categorized_path,
    open_downloaded_file,
    open_containing_folder,
)
from smart_download.utils.tk_helpers import (
    _detach_photo_tk,
    _detach_widget_tk_refs,
    _drain_bg_tk_callbacks,
)

# Re-export core
from smart_download.core.rate_limiter import TokenBucketRateLimiter
from smart_download.core.chunk import DownloadChunk, get_permissive_ssl_context, _SSL_CONTEXT_LOCK
from smart_download.core.html_resolver import (
    _HtmlCandidateExtractor,
    resolve_all_download_candidates,
    _HtmlLinkCandidateParser,
    resolve_real_download_url,
    validate_refresh_url,
)
from smart_download.core.engine import TurboDownloadEngine
from smart_download.core.stream_coordinator import StreamDownloadCoordinator
from smart_download.core.history import DownloadHistoryManager

# Re-export services
from smart_download.services.startup_service import (
    IS_WINDOWS,
    WINDOWS_RUN_KEY,
    STARTUP_REG_KEY_NAME,
    LEGACY_STARTUP_REG_KEY_NAME,
    TASK_NAME,
    LEGACY_TASK_NAME,
    get_installed_exe_path,
    get_startup_folder,
    get_startup_dir,
    _parse_startup_cmd,
    _extract_exe_from_cmd,
    _create_startup_shortcut,
    get_startup_command,
    is_startup_enabled,
    enable_startup,
    disable_startup,
    get_startup_entry,
)
from smart_download.services.single_instance import notify_running_instance
from smart_download.services.youtube_service import (
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
from smart_download.services.updater_service import (
    parse_version,
    is_newer_version,
    YtDlpAutoUpdater,
    AppAutoUpdater,
    get_ytdlp_plugin_dir,
)
from smart_download.services.browser.bridge_server import BrowserBridgeServer, DEFAULT_BRIDGE_PORT
from smart_download.services.browser.registry import (
    register_native_host,
    unregister_native_host,
    check_and_register_browser,
    register_browser_extensions,
    unregister_browser_extensions,
    is_registered as is_browser_registered,
    get_status as get_browser_reg_status,
)

# Re-export UI
from smart_download.ui.components.base_modal import SafeModalDialog
from smart_download.ui.components.tooltip import ToolTip
from smart_download.ui.modals.toasts import FetchingLinkToast, StartupWelcomeToast
from smart_download.ui.modals.quality_modal import QualitySelectionModal
from smart_download.ui.modals.confirm_modal import (
    DownloadConfirmationModal,
    DownloadConfirmationDialog,
    DownloadConfirmModal,
)
from smart_download.ui.modals.candidates_modal import MultipleCandidatesModal
from smart_download.ui.modals.refresh_modal import RefreshLinkModal, RefreshLinkDialog
from smart_download.ui.modals.update_modal import AppUpdateModal
from smart_download.ui.system_tray import SystemTrayManager, PYSTRAY_AVAILABLE
from smart_download.ui.main_window import (
    ModernFramelessGUI,
    main,
    SmartDownloadEngine,
    TurboDownloaderGUI,
    DownloaderApp,
    SmartDownloadGUI,
)

import types

_SYNC_ACTIVE = False

class _TurboDownloaderShim(types.ModuleType):
    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        global _SYNC_ACTIVE
        if _SYNC_ACTIVE or name.startswith("__"):
            return
        try:
            _SYNC_ACTIVE = True
            for mod in list(sys.modules.values()):
                if mod is not None and getattr(mod, "__name__", "").startswith("smart_download"):
                    if hasattr(mod, name):
                        try:
                            setattr(mod, name, value)
                        except Exception:
                            pass
            yr = sys.modules.get("youtube_resolver")
            if yr is not None and hasattr(yr, name):
                try:
                    setattr(yr, name, value)
                except Exception:
                    pass
        finally:
            _SYNC_ACTIVE = False

sys.modules[__name__].__class__ = _TurboDownloaderShim

if __name__ == "__main__":
    main()
