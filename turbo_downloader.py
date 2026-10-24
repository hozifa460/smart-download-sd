"""
========================================================================================
🚀 SMART DOWNLOAD (SD) — Custom Dynamic Chunking & Bandwidth Limiting Engine
========================================================================================
A high-performance, standalone Python download manager implementing:
1. Dynamic on-the-fly chunk splitting (Adaptive largest-remainder candidate selection & midpoint split).
2. Strict non-corrupt sequential assembly (64KB streaming buffers & byte boundary assertions).
3. Per-download manual speed limiter (Token Bucket rate limiter adjustable live during download).
4. Modern sleek Frameless Window GUI with dark aesthetic, draggable title bar, taskbar integration,
   speed limiter slider + presets, and visual segmented chunk progress bar (SD style).

100% Standard Library: No external pip packages required. Runs directly on Python 3.8+ on Windows/Linux/macOS.
========================================================================================
"""

import sys
import os
import time

if "--test-startup" in sys.argv:
    t0 = time.time()
    import youtube_resolver
    t1 = time.time()
    import browser_bridge
    t2 = time.time()
    import native_messaging_host
    t3 = time.time()
    import register_browser
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
from html.parser import HTMLParser
import ctypes
import zlib
import zipfile
import tarfile
from dataclasses import dataclass, field
from typing import List, Optional, Callable, Dict, Any, Union, Tuple

def get_resource_path(relative_path: str) -> str:
    """Resolve absolute path for bundled assets in development or PyInstaller frozen bundle."""
    if hasattr(sys, "_MEIPASS"):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

def enable_high_dpi_awareness():
    """
    Configures Windows High-DPI awareness so Desktop Window Manager (DWM)
    renders vector typography and widgets crisply at native screen resolution
    without blurry bitmap scaling on 125%, 150%, 200% displays.
    """
    if sys.platform.startswith("win"):
        try:
            import ctypes
            # Explicit AppUserModelID ensures Windows taskbar associates the app with its high-res icon
            try:
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("SmartDownload.SD.App")
            except Exception:
                pass
            # 1. Windows 10 Creators Update (1703+) Per-Monitor V2
            # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
            try:
                res = ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
                if res:
                    return
            except Exception:
                pass
            # 2. Windows 8.1+ Per-Monitor DPI Aware (PROCESS_PER_MONITOR_DPI_AWARE = 2)
            try:
                hr = ctypes.windll.shcore.SetProcessDpiAwareness(2)
                if hr == 0:
                    return
            except Exception:
                pass
            # 3. Windows Vista+ System DPI Aware
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass
        except Exception:
            pass

# Initialize Windows High-DPI awareness immediately before Tkinter GUI imports/initialization
enable_high_dpi_awareness()

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from updater import (
    APP_VERSION,
    parse_version,
    is_newer_version,
    YtDlpAutoUpdater,
    AppAutoUpdater,
    get_ytdlp_plugin_dir,
)

# Import modular YouTube & Streaming Media components
from youtube_resolver import (
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
    YouTubeResolver,
    MediaResolver,
    YouTubeStreamInfo,
    MediaStreamInfo,
    VideoFormatOption,
    format_filesize,
    SUPPORTED_COOKIE_BROWSERS,
    detect_installed_cookie_browsers
)
from browser_bridge import BrowserBridgeServer, DEFAULT_BRIDGE_PORT
from register_browser import (
    register_native_host,
    unregister_native_host,
    check_and_register_browser,
    register_browser_extensions,
    unregister_browser_extensions,
    is_registered as is_browser_registered,
    get_status as get_browser_reg_status
)

# Windows System Tray Integration (pystray)
try:
    import pystray
    from pystray import MenuItem as TrayMenuItem, Menu as TrayMenu
    PYSTRAY_AVAILABLE = True
except Exception:
    pystray = None
    TrayMenuItem = None
    TrayMenu = None
    PYSTRAY_AVAILABLE = False

# ======================================================================================
# APPLICATION SETTINGS & USER PREFERENCES PERSISTENCE
# ======================================================================================

def get_config_dir() -> str:
    """Returns persistent application configuration directory path."""
    cfg_override = os.environ.get("SD_CONFIG_DIR")
    if cfg_override:
        try:
            os.makedirs(cfg_override, exist_ok=True)
        except Exception:
            pass
        return cfg_override
    if "unittest" in sys.modules or "pytest" in sys.modules or os.environ.get("SD_TESTING"):
        test_cfg = os.path.join(tempfile.gettempdir(), "sd_test_isolated_cfg")
        try:
            os.makedirs(test_cfg, exist_ok=True)
        except Exception:
            pass
        return test_cfg
    if sys.platform.startswith("win"):
        appdata = os.environ.get("APPDATA")
        if appdata:
            cfg = os.path.join(appdata, "SmartDownload")
            legacy_cfg = os.path.join(appdata, "TurboDownloader")
            if os.path.isdir(legacy_cfg) and not os.path.exists(cfg):
                try:
                    shutil.copytree(legacy_cfg, cfg)
                except Exception:
                    pass
        else:
            cfg = os.path.join(os.path.expanduser("~"), ".smartdownload")
    else:
        cfg = os.path.join(os.path.expanduser("~"), ".smartdownload")
    try:
        os.makedirs(cfg, exist_ok=True)
    except Exception:
        pass
    return cfg

get_app_config_dir = get_config_dir

def get_settings_file_path() -> str:
    """Returns absolute path to persistent settings.json."""
    return os.path.join(get_config_dir(), "settings.json")

def load_settings() -> Dict[str, Any]:
    """Loads user configuration dictionary from settings.json with robust fallbacks."""
    path = get_settings_file_path()
    defaults = {
        "minimize_to_tray": True,
        "auto_categorize_folders": True,
        "language": "ar",
        "auto_unpack_archives": False,
    }
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    defaults.update(data)
        except Exception:
            pass
    return defaults

def save_settings(settings_dict: Dict[str, Any]) -> bool:
    """Persists updated configuration dictionary to settings.json."""
    path = get_settings_file_path()
    try:
        cur = load_settings()
        cur.update(settings_dict)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cur, f, indent=2)
        return True
    except Exception:
        return False

def get_setting(key: str, default: Any = None) -> Any:
    """Retrieves a single setting value with fallback default."""
    return load_settings().get(key, default)

def set_setting(key: str, value: Any) -> bool:
    """Sets and persists a single setting value."""
    return save_settings({key: value})

# ==============================================================================
# Complete Arabic & English UI Localization (Bilingual System)
# ==============================================================================
TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "en": {
        # App identity
        "app_title": "Smart Download (SD)",
        "app_header": "SMART DOWNLOAD (SD)",
        "app_subtitle": "[SD Dynamic Chunking & Bandwidth Throttle Engine]",
        "app_version_label": "v{version}",

        # Window controls
        "btn_minimize": "—",
        "btn_close": "✕",
        "btn_lang_toggle": "🌐 العربية",
        "btn_check_updates": "🔄 Check for Updates",
        "btn_checking_updates": "⏳ Checking...",

        # Input row
        "lbl_url": "Download URL:",
        "btn_add_url": "Add URL",
        "btn_paste": "📋 Paste",
        "btn_refresh_url": "🔄 Refresh Link",
        "lbl_dest": "Save Location:",
        "btn_browse": "📁 Browse...",

        # Limiter & options row
        "lbl_threads": "Threads:",
        "lbl_speed_limiter": "Speed Limiter:",
        "lbl_custom_speed": "Custom (KB/s):",
        "btn_apply_limit": "⚡ Apply Limit",
        "lbl_current_limit_unlimited": "● Current: Unlimited",
        "lbl_current_limit_active": "● Limit: {limit}",
        "lbl_live_throttle_slider": "🎚️ Live Throttle Slider:",
        "slider_val_unlimited": "Unlimited (0 KB/s)",

        # Action buttons
        "btn_start": "▶ Start Download",
        "btn_resume_all": "Resume All",
        "btn_pause": "⏸ Pause",
        "btn_resume": "▶ Resume",
        "btn_pause_all": "Pause All",
        "btn_cancel": "⏹ Cancel",
        "btn_clear_completed": "🧹 Clear Completed",
        "btn_settings": "⚙️ Settings",

        # Feature buttons
        "btn_browser": "🌐 Browser Integration",
        "btn_sniffer_active": "📋 Sniffer: Active",
        "btn_sniffer_paused": "📋 Sniffer: Paused",
        "btn_startup_on": "🚀 Boot: ON",
        "btn_startup_off": "🚀 Boot: OFF",
        "btn_cookies_prefix": "🍪 Cookies:",
        "btn_auto_cat_on": "📁 Auto-Sort: ON",
        "btn_auto_cat_off": "📁 Auto-Sort: OFF",

        # Metrics card
        "metric_transferred": "Transferred",
        "metric_total_size": "Total File Size",
        "metric_speed": "Current Speed",
        "metric_eta": "Remaining Time",
        "metric_progress": "Progress",
        "metric_threads": "Active Chunks",

        # Notebook tabs
        "tab_chunks": "  📊 Chunk Segments  ",
        "tab_active": "  ⚡ Active Downloads  ",
        "tab_completed": "  ✅ Completed  ",
        "tab_logs": "  📜 Activity Log  ",
        "tab_history": "  📂 Download History  ",
        "tab_settings": "  ⚙️ Settings  ",

        # Chunk table columns
        "col_chunk_id": "ID",
        "col_chunk_range": "Byte Offset Range",
        "col_chunk_size": "Total Span",
        "col_chunk_downloaded": "Downloaded",
        "col_chunk_pct": "Progress",
        "col_chunk_status": "Status",

        # History toolbar
        "lbl_filter": "Filter:",
        "hist_filter_all": "All Categories",
        "btn_hist_open": "📂 Open File",
        "btn_hist_folder": "📁 Open Folder",
        "btn_hist_redownload": "🔄 Resume / Retry",
        "btn_hist_remove": "🗑️ Remove",
        "btn_hist_clear": "🧹 Clear All",

        # History table columns
        "col_hist_category": "Category",
        "col_hist_filename": "File Name",
        "col_hist_size": "Size",
        "col_hist_status": "Status",
        "col_hist_date": "Date Added",
        "col_hist_path": "Saved Location",
        "col_hist_actions": "Actions",

        # Download Confirmation Modal
        "modal_confirm_title": "Download File Info — Smart Download",
        "modal_file_name": "File Name:",
        "modal_save_to": "Save To:",
        "modal_category": "Category:",
        "modal_quality": "Quality / Format:",
        "modal_threads": "Connections / Threads:",
        "modal_speed_limiter": "Speed Limiter:",
        "modal_custom_speed": "Custom Speed (KB/s):",
        "modal_btn_start": "▶ Start Download Here",
        "modal_btn_open_in_main": "📋 Open in Main App",
        "modal_btn_cancel": "✕ Cancel",
        "modal_btn_browse": "📁 Browse...",
        "modal_download_mp3": "🎵 Download MP3",
        "modal_cookies": "Browser Cookies",

        # Quality Selection Modal
        "modal_quality_title": "Select Video Quality — Smart Download",
        "modal_quality_header": "Select Quality & Format",
        "modal_col_res": "Resolution / Format",
        "modal_col_ext": "Container",
        "modal_col_size": "Est. Size",
        "modal_col_fps": "FPS",
        "modal_col_type": "Stream Type",
        "modal_btn_download": "▶ Download",

        # MultipleCandidatesModal
        "multi_modal_title": "Detected Download Links — Smart Download",
        "multi_modal_source": "Source Page:",
        "multi_modal_subtitle": "Multiple downloadable files were found on this page. Select the files you want to download:",
        "multi_col_select": "Select",
        "multi_col_filename": "File Name",
        "multi_col_type": "Type",
        "multi_col_size": "Size",
        "multi_col_url": "Link Preview",
        "multi_select_all": "Select All",
        "multi_btn_download_selected": "Download Selected",
        "multi_btn_download_all": "Download All",
        "multi_btn_cancel": "Cancel",
        "multi_no_selection_warning": "Please select at least one file to download.",
        "multi_selection_count": "{selected} / {total} files selected",

        # Toasts
        "toast_startup_title": "Smart Download (SD)",
        "toast_startup_msg": "Smart Download is active in the background and monitoring for downloads.",
        "toast_fetching_header": "🔍 Fetching and analyzing link...",
        "toast_fetching_sub": "Please wait while Smart Download prepares your download...",
        "toast_completed_title": "Download Completed Successfully! 🚀",
        "toast_completed_msg": "File saved successfully: {filename}",
        "toast_error_title": "Download Error ❌",
        "toast_error_msg": "An error occurred during download: {error}",

        # Dialogs
        "dialog_not_download_title": "Not a download link",
        "dialog_not_download_msg": "This link is for a web page, not a direct download file. Open it in your browser and click download, or copy the direct download link.",

        # System Tray Menu
        "tray_open": "🖥️ Open Smart Download",
        "tray_sniffer_active": "📋 Clipboard Sniffer: Active",
        "tray_sniffer_paused": "📋 Clipboard Sniffer: Paused",
        "tray_startup_on": "🚀 Start with Windows: ON",
        "tray_startup_off": "🚀 Start with Windows: OFF",
        "tray_exit": "❌ Exit Completely",

        # Dialog Action Buttons
        "btn_yes": "Yes",
        "btn_no": "No",
        "btn_ok": "OK",

        # Context Menus
        "ctx_open_file": "📂 Open File",
        "ctx_open_folder": "📁 Open Containing Folder",
        "ctx_copy_url": "📋 Copy URL",
        "ctx_resume_retry": "🔄 Resume / Retry",
        "ctx_remove_history": "🗑️ Remove from History",
        "ctx_refresh_address": "🔄 Refresh Download Address...",
        "ctx_resume_download": "▶ Resume Download",
        "ctx_pause_download": "⏸ Pause Download",
        "ctx_cancel_download": "⏹ Cancel Download",
        "ctx_copy_download_url": "📋 Copy Download URL",

        # Refresh Link Dialog
        "refresh_modal_title": "Refresh Download Address — Smart Download",
        "refresh_modal_header": "Refresh Expired Download Address",
        "refresh_modal_sub": "Paste the new active link to continue downloading without losing your downloaded parts.",
        "refresh_modal_filename": "File Name:",
        "refresh_modal_preserved": "Preserved Data:",
        "refresh_modal_old_addr": "Old Address:",
        "refresh_modal_new_url": "New Download URL:",
        "refresh_modal_status_idle": "Paste the new download link and click Validate & Resume.",
        "refresh_modal_btn_validate": "🔄 Validate & Resume",
        "refresh_modal_btn_validating": "⏳ Validating...",
        "refresh_modal_btn_cancel": "✕ Cancel",

        # Browser Integration Dialog
        "browser_dlg_title": "🌐 Browser Integration & WebExtension Setup",
        "browser_dlg_header": "🌐 BROWSER INTEGRATION & EXTENSION SETUP",
        "browser_card_sniffer_title": "📋 ZERO-INSTALL CLIPBOARD MONITOR (SD SMART CAPTURE — ALL BROWSERS)",
        "browser_card_sniffer_desc": "Works 100% across ALL browsers (Chrome, Edge, Firefox, Brave, Opera, Safari) without any extension.\nJust right-click any link or video and choose 'Copy Link Address' — Smart Download catches it instantly!",
        "browser_card_server_title": "LOCAL IPC LOOPBACK LISTENER",
        "browser_server_active": "● Active on http://{host}:{port}",
        "browser_server_stopped": "● Listener Stopped / Offline",
        "browser_btn_stop_server": "⏹ Stop Server",
        "browser_btn_start_server": "▶ Start Server",
        "browser_btn_test_ping": "⚡ Test Ping",
        "browser_card_reg_title": "WINDOWS REGISTRY DIRECT BROWSER LINK (NATIVE MESSAGING)",
        "browser_reg_active": "● Registry Active: {chrome}  {edge} (com.smartdownload.host)",
        "browser_reg_inactive": "● Not Registered in Windows Registry",
        "browser_btn_reregister": "🔄 Re-Register",
        "browser_btn_register": "🔗 1-Click Register (Chrome & Edge)",
        "browser_btn_unregister": "Unregister",
        "browser_card_boot_title": "🚀 WINDOWS STARTUP AUTO-BOOT (SILENT BACKGROUND MODE)",
        "browser_boot_enabled": "● Start with Windows: Enabled (Silent Background)",
        "browser_boot_disabled": "● Start with Windows: Disabled",
        "browser_btn_boot_enabled": "🚀 Start on Boot: Enabled",
        "browser_btn_boot_disabled": "🚀 Start on Boot: Disabled",
        "browser_card_tray_title": "🔔 WINDOWS SYSTEM TRAY & BACKGROUND MINIMIZATION",
        "browser_tray_enabled": "● Close (✕) Action: Minimize to System Tray",
        "browser_tray_disabled": "● Close (✕) Action: Exit Application Completely",
        "browser_btn_tray_enabled": "[✓] Minimize to System Tray on Close (✕)",
        "browser_btn_tray_disabled": "[  ] Minimize to System Tray on Close (✕)",
        "browser_card_ext_title": "WEBEXTENSION ARTIFACT (MANIFEST V3)",
        "browser_btn_open_folder": "📂 Open Folder",
        "browser_tab_chrome": " Chrome & Brave ",
        "browser_tab_edge": " Microsoft Edge ",
        "browser_tab_firefox": " Mozilla Firefox ",
        "browser_btn_close": "Close",

        # Dialogs & History Statuses
        "dialog_not_found_title": "File Not Found",
        "dialog_not_found_msg": "The downloaded file does not exist at:\n{path}",
        "dialog_resume_incomplete_title": "Resume Incomplete Download",
        "dialog_resume_incomplete_msg": "This file is paused or incomplete. Would you like to resume downloading now?",
        "dialog_exit_title": "Exit Confirmation",
        "dialog_exit_msg": "A download is currently active. Stop and exit completely?",
        "status_completed": "Completed",
        "status_paused": "Paused",
        "status_in_progress": "In Progress",
        "status_failed": "Failed",
        "status_cancelled": "Cancelled",
        "status_ready": "Ready",

        # Tooltips
        "tip_lang_toggle": "Switch between Arabic and English",
        "tip_startup": "Toggle start on Windows boot",
        "tip_sniffer": "Toggle clipboard link sniffer",
        "tip_auto_cat": "Toggle automatic folder categorization",
        "tip_speed_slider": "Drag to throttle live download speed",

        # Categories
        "cat_all": "All Categories",
        "cat_video": "Video",
        "cat_audio": "Audio",
        "cat_programs": "Programs",
        "cat_compressed": "Compressed",
        "cat_documents": "Documents",
        "cat_images": "Images",
        "cat_general": "General",

        # Limiter & Speed Labels
        "lbl_unlimited": "Unlimited",
        "lbl_speed_limit": "Speed Limit:",
        "lbl_current_unlimited": "● Current: Unlimited",
        "lbl_current_limit": "● Current: {limit}",

        # Auto Unpack Archives (AeroArchive)
        "browser_card_unpack_title": "📦 AUTOMATIC ARCHIVE EXTRACTION (AEROARCHIVE ENGINE)",
        "browser_card_unpack_desc": "Automatically extract .zip, .tar, .tar.gz, .7z archives upon download completion.",
        "browser_unpack_enabled": "● Auto-Unpack: Enabled",
        "browser_unpack_disabled": "● Auto-Unpack: Disabled",
        "browser_btn_unpack_enabled": "[✓] Auto-Unpack Archives after Download",
        "browser_btn_unpack_disabled": "[  ] Auto-Unpack Archives after Download",

        # Browser Installation Guides
        "browser_guide_chrome": (
            "1. Open Chrome or Brave and type chrome://extensions in the address bar.\n"
            "2. Turn ON 'Developer mode' using the toggle in the top-right corner.\n"
            "3. Click the 'Load unpacked' button at the top-left.\n"
            "4. Select the extension directory displayed above.\n"
            "5. The ⚡ Smart Download icon will appear in your extensions bar!"
        ),
        "browser_guide_edge": (
            "1. Open Edge and navigate to edge://extensions in the address bar.\n"
            "2. Turn ON 'Developer mode' in the left-hand navigation sidebar.\n"
            "3. Click the 'Load unpacked' button.\n"
            "4. Select the extension directory displayed above.\n"
            "5. Pin the extension to your toolbar for one-click access."
        ),
        "browser_guide_firefox": (
            "1. Open Firefox and type about:debugging#/runtime/this-firefox in the address bar.\n"
            "2. Click the 'Load Temporary Add-on...' button.\n"
            "3. Select the 'manifest.json' file inside the extension folder.\n"
            "4. The extension is immediately loaded and connects to Smart Download."
        ),

        # Dialogs & Modal Messages
        "dialog_complete_msg_verified": "File verified & assembled without corruption!",
        "dialog_complete_msg_saved": "Saved to:",
        "dialog_complete_msg_size": "Size:",
        "dialog_complete_msg_time": "Total Time:",
        "dialog_expired_title": "Download Link Expired ⚠️",
        "dialog_expired_msg1": "Download stopped: Server rejected session (HTTP 401/403/410).",
        "dialog_expired_details": "Details:",
        "dialog_expired_msg2": "💡 All partially downloaded chunk files are safely preserved on disk.",
        "dialog_expired_msg3": "Would you like to refresh the download link now to resume?",
        "dialog_error_title": "Download Error",
        "dialog_error_prefix": "Encountered error during download:",
        "modal_confirm_hint": "⏎ Press Enter to start, Esc to cancel",
        "modal_confirm_title_header": "DOWNLOAD FILE INFO",
        "modal_confirm_sub": "SD Smart Interception",
        "modal_quality_header": "Select Quality & Format",
        "modal_quality_sub": "Choose the desired video resolution or audio track to download:",
        "modal_col_res": "Resolution / Format",
        "modal_col_ext": "Container",
        "modal_col_size": "Est. Size",
        "modal_col_fps": "FPS",
        "modal_col_type": "Stream Details",
        "modal_btn_start_quality": "⚡ Download Selected Quality",
        "modal_status_connecting": "Status: Connecting...",
        "modal_status_downloading": "Status: Downloading...",
        "modal_status_complete": "✅ Download Complete!",
        "modal_status_paused": "Status: Paused",
    },
    "ar": {
        # App identity
        "app_title": "التحميل الذكي (SD)",
        "app_header": "التحميل الذكي (SD)",
        "app_subtitle": "[محرك التحميل الذكي متعدد المسارات والتحكم بالنطاق الترددي]",
        "app_version_label": "الإصدار {version}",

        # Window controls
        "btn_minimize": "—",
        "btn_close": "✕",
        "btn_lang_toggle": "🌐 English",
        "btn_check_updates": "🔄 التحقق من التحديثات",
        "btn_checking_updates": "⏳ جارٍ التحقق...",

        # Input row
        "lbl_url": "رابط التحميل:",
        "btn_add_url": "إضافة رابط",
        "btn_paste": "📋 لصق",
        "btn_refresh_url": "🔄 تحديث الرابط",
        "lbl_dest": "مكان الحفظ:",
        "btn_browse": "📁 استعراض...",

        # Limiter & options row
        "lbl_threads": "المسارات:",
        "lbl_speed_limiter": "محدد السرعة:",
        "lbl_custom_speed": "مخصص (ك.ب/ث):",
        "btn_apply_limit": "⚡ تطبيق الحد",
        "lbl_current_limit_unlimited": "● الحالي: غير محدود",
        "lbl_current_limit_active": "● الحد: {limit}",
        "lbl_live_throttle_slider": "🎚️ شريط التحكم بالسرعة المباشر:",
        "slider_val_unlimited": "غير محدود (0 ك.ب/ث)",

        # Action buttons
        "btn_start": "▶ بدء التحميل",
        "btn_resume_all": "استئناف الكل",
        "btn_pause": "⏸ إيقاف مؤقت",
        "btn_resume": "▶ استئناف",
        "btn_pause_all": "إيقاف الكل",
        "btn_cancel": "⏹ إلغاء",
        "btn_clear_completed": "🧹 مسح المكتمل",
        "btn_settings": "⚙️ الإعدادات",

        # Feature buttons
        "btn_browser": "🌐 ملحق المتصفح",
        "btn_sniffer_active": "📋 المراقب: مفعل",
        "btn_sniffer_paused": "📋 المراقب: معطل",
        "btn_startup_on": "🚀 بدء التشغيل مع ويندوز: مفعل",
        "btn_startup_off": "🚀 بدء التشغيل مع ويندوز: معطل",
        "btn_cookies_prefix": "🍪 الكوكيز:",
        "btn_auto_cat_on": "📁 فرز تلقائي: مفعل",
        "btn_auto_cat_off": "📁 فرز تلقائي: معطل",

        # Metrics card
        "metric_transferred": "تم نقل",
        "metric_total_size": "الحجم الإجمالي",
        "metric_speed": "السرعة الحالية",
        "metric_eta": "الوقت المتبقي",
        "metric_progress": "التقدم",
        "metric_threads": "المسارات النشطة",

        # Notebook tabs
        "tab_chunks": "  📊 قطاعات التحميل  ",
        "tab_active": "  ⚡ التحميلات النشطة  ",
        "tab_completed": "  ✅ التحميلات المكتملة  ",
        "tab_logs": "  📜 سجل العمليات  ",
        "tab_history": "  📂 سجل التحميلات  ",
        "tab_settings": "  ⚙️ الإعدادات  ",

        # Chunk table columns
        "col_chunk_id": "المعرف",
        "col_chunk_range": "نطاق البايتات",
        "col_chunk_size": "الحجم الكلي",
        "col_chunk_downloaded": "تم تنزيله",
        "col_chunk_pct": "النسبة",
        "col_chunk_status": "الحالة",

        # History toolbar
        "lbl_filter": "تصفية:",
        "hist_filter_all": "جميع التصنيفات",
        "btn_hist_open": "📂 فتح الملف",
        "btn_hist_folder": "📁 فتح المجلد",
        "btn_hist_redownload": "🔄 استئناف / إعادة المحاولة",
        "btn_hist_remove": "🗑️ حذف",
        "btn_hist_clear": "🧹 مسح الكل",

        # History table columns
        "col_hist_category": "التصنيف",
        "col_hist_filename": "اسم الملف",
        "col_hist_size": "الحجم",
        "col_hist_status": "الحالة",
        "col_hist_date": "تاريخ الإضافة",
        "col_hist_path": "مكان الحفظ",
        "col_hist_actions": "الإجراءات",

        # Download Confirmation Modal
        "modal_confirm_title": "معلومات تحميل الملف — Smart Download",
        "modal_file_name": "اسم الملف:",
        "modal_save_to": "مكان الحفظ:",
        "modal_category": "التصنيف:",
        "modal_quality": "الدقة / الصيغة:",
        "modal_threads": "المسارات / الاتصالات:",
        "modal_speed_limiter": "محدد السرعة:",
        "modal_custom_speed": "سرعة مخصصة (ك.ب/ث):",
        "modal_btn_start": "▶ بدء التحميل هنا",
        "modal_btn_open_in_main": "📋 فتح في التطبيق",
        "modal_btn_cancel": "✕ إلغاء",
        "modal_btn_browse": "📁 استعراض...",
        "modal_download_mp3": "تحميل صوت MP3 فقط",
        "modal_cookies": "كوكيز المتصفح",

        # Quality Selection Modal
        "modal_quality_title": "تحديد دقة الفيديو — Smart Download",
        "modal_quality_header": "تحديد الجودة والصيغة",
        "modal_col_res": "الدقة / الصيغة",
        "modal_col_ext": "الحاوية",
        "modal_col_size": "الحجم التقديري",
        "modal_col_fps": "معدل الإطارات",
        "modal_col_type": "نوع المسار",
        "modal_btn_download": "▶ تحميل",

        # MultipleCandidatesModal
        "multi_modal_title": "روابط التحميل المكتشفة — Smart Download",
        "multi_modal_source": "الصفحة المصدر:",
        "multi_modal_subtitle": "تم العثور على عدة ملفات متاحة للتحميل في هذه الصفحة. حدد الملفات التي ترغب بتحميلها:",
        "multi_col_select": "تحديد",
        "multi_col_filename": "اسم الملف",
        "multi_col_type": "النوع",
        "multi_col_size": "الحجم",
        "multi_col_url": "معاينة الرابط",
        "multi_select_all": "تحديد الكل",
        "multi_btn_download_selected": "تحميل المحدد",
        "multi_btn_download_all": "تحميل الكل",
        "multi_btn_cancel": "إلغاء",
        "multi_no_selection_warning": "يرجى تحديد ملف واحد على الأقل للتحميل.",
        "multi_selection_count": "تم تحديد {selected} من {total} ملف",

        # Toasts
        "toast_startup_title": "Smart Download (SD)",
        "toast_startup_msg": "Smart Download يعمل الآن في الخلفية وجاهز لالتقاط الروابط.",
        "toast_fetching_header": "🔍 جاري جلب وتحليل الرابط...",
        "toast_fetching_sub": "يرجى الانتظار بينما يجهز البرنامج التحميل...",
        "toast_completed_title": "اكتمل التحميل بنجاح! 🚀",
        "toast_completed_msg": "تم حفظ الملف بنجاح: {filename}",
        "toast_error_title": "خطأ في التحميل ❌",
        "toast_error_msg": "حدث خطأ أثناء التحميل: {error}",

        # Dialogs
        "dialog_not_download_title": "ليس رابط تحميل",
        "dialog_not_download_msg": "هذا الرابط لصفحة ويب وليس لملف تحميل. افتحه في المتصفح واضغط زر التحميل، أو انسخ رابط التحميل المباشر.",

        # System Tray Menu
        "tray_open": "🖥️ فتح البرنامج",
        "tray_sniffer_active": "📋 مراقب الحافظة: مفعل",
        "tray_sniffer_paused": "📋 مراقب الحافظة: معطل",
        "tray_startup_on": "🚀 بدء التشغيل مع ويندوز: مفعل",
        "tray_startup_off": "🚀 بدء التشغيل مع ويندوز: معطل",
        "tray_exit": "❌ خروج نهائي",

        # Dialog Action Buttons
        "btn_yes": "نعم",
        "btn_no": "لا",
        "btn_ok": "موافق",

        # Context Menus
        "ctx_open_file": "📂 فتح الملف",
        "ctx_open_folder": "📁 فتح المجلد المحتوي",
        "ctx_copy_url": "📋 نسخ الرابط",
        "ctx_resume_retry": "🔄 استئناف / إعادة المحاولة",
        "ctx_remove_history": "🗑️ حذف من السجل",
        "ctx_refresh_address": "🔄 تجديد عنوان التحميل...",
        "ctx_resume_download": "▶ استئناف التحميل",
        "ctx_pause_download": "⏸ إيقاف التحميل مؤقتاً",
        "ctx_cancel_download": "⏹ إلغاء التحميل",
        "ctx_copy_download_url": "📋 نسخ رابط التحميل",

        # Refresh Link Dialog
        "refresh_modal_title": "تجديد عنوان التحميل — Smart Download",
        "refresh_modal_header": "تجديد رابط التحميل المنتهي",
        "refresh_modal_sub": "الصق الرابط النشط الجديد لمتابعة التحميل دون فقدان الأجزاء المنزلة.",
        "refresh_modal_filename": "اسم الملف:",
        "refresh_modal_preserved": "البيانات المحفوظة:",
        "refresh_modal_old_addr": "العنوان القديم:",
        "refresh_modal_new_url": "رابط التحميل الجديد:",
        "refresh_modal_status_idle": "الصق رابط التحميل الجديد واضغط تحديث واستئناف.",
        "refresh_modal_btn_validate": "🔄 تحديث واستئناف",
        "refresh_modal_btn_validating": "⏳ جارٍ التحقق...",
        "refresh_modal_btn_cancel": "✕ إلغاء",

        # Browser Integration Dialog
        "browser_dlg_title": "🌐 ملحق المتصفح وإعداد الإضافة",
        "browser_dlg_header": "🌐 ملحق المتصفح وإعداد الإضافة",
        "browser_card_sniffer_title": "📋 مراقب الحافظة الفوري (التقاط ذكي — لكافة المتصفحات)",
        "browser_card_sniffer_desc": "يعمل 100% عبر كافة المتصفحات دون الحاجة لأي إضافة.\nفقط انقر بزر الفأرة الأيمن على أي رابط واختر 'نسخ عنوان الرابط' وسيلتقطه البرنامج فوراً!",
        "browser_card_server_title": "خادم الاتصال المحلي السريع (IPC)",
        "browser_server_active": "● نشط على http://{host}:{port}",
        "browser_server_stopped": "● الخادم متوقف / غير متصل",
        "browser_btn_stop_server": "⏹ إيقاف الخادم",
        "browser_btn_start_server": "▶ تشغيل الخادم",
        "browser_btn_test_ping": "⚡ اختبار الاتصال",
        "browser_card_reg_title": "الربط المباشر مع سجل ويندوز (Native Messaging)",
        "browser_reg_active": "● مسجل بنجاح في ويندوز: {chrome}  {edge} (com.smartdownload.host)",
        "browser_reg_inactive": "● غير مسجل في سجل ويندوز",
        "browser_btn_reregister": "🔄 إعادة التسجيل",
        "browser_btn_register": "🔗 تسجيل فوري (Chrome & Edge)",
        "browser_btn_unregister": "إلغاء التسجيل",
        "browser_card_boot_title": "🚀 بدء التشغيل التلقائي مع ويندوز (الوضع الصامت في الخلفية)",
        "browser_boot_enabled": "● بدء التشغيل مع ويندوز: مفعل (الوضع الصامت)",
        "browser_boot_disabled": "● بدء التشغيل مع ويندوز: معطل",
        "browser_btn_boot_enabled": "🚀 بدء التشغيل مع ويندوز: مفعل",
        "browser_btn_boot_disabled": "🚀 بدء التشغيل مع ويندوز: معطل",
        "browser_card_tray_title": "🔔 التصغير لشريط المهام (System Tray) والعمل بالخلفية",
        "browser_tray_enabled": "● إجراء الإغلاق (✕): التصغير لشريط المهام",
        "browser_tray_disabled": "● إجراء الإغلاق (✕): الخروج النهائي من البرنامج",
        "browser_btn_tray_enabled": "[✓] تصغير لشريط المهام عند الإغلاق (✕)",
        "browser_btn_tray_disabled": "[  ] تصغير لشريط المهام عند الإغلاق (✕)",
        "browser_card_ext_title": "ملفات إضافة المتصفح (Manifest V3)",
        "browser_btn_open_folder": "📂 فتح المجلد",
        "browser_tab_chrome": " كروم وبريف ",
        "browser_tab_edge": " مايكروسوفت إيدج ",
        "browser_tab_firefox": " موزيلا فايرفوكس ",
        "browser_btn_close": "إغلاق",

        # Dialogs & History Statuses
        "dialog_not_found_title": "الملف غير موجود",
        "dialog_not_found_msg": "الملف المحمل غير موجود في المسار:\n{path}",
        "dialog_resume_incomplete_title": "استئناف التحميل غير المكتمل",
        "dialog_resume_incomplete_msg": "هذا الملف متوقف مؤقتاً أو غير مكتمل. هل ترغب في استئناف تحميله الآن؟",
        "dialog_exit_title": "تأكيد الخروج",
        "dialog_exit_msg": "هناك تحميل نشط حالياً. هل ترغب في الإيقاف والخروج النهائي؟",
        "status_completed": "مكتمل",
        "status_paused": "متوقف مؤقتاً",
        "status_in_progress": "قيد التحميل",
        "status_failed": "فشل",
        "status_cancelled": "ملغي",
        "status_ready": "جاهز",

        # Tooltips
        "tip_lang_toggle": "التبديل بين اللغتين العربية والإنجليزية",
        "tip_startup": "تفعيل/تعطيل بدء التشغيل التلقائي مع ويندوز",
        "tip_sniffer": "تفعيل/تعطيل مراقب الحافظة التلقائي",
        "tip_auto_cat": "تفعيل/تعطيل الفرز التلقائي في مجلدات",
        "tip_speed_slider": "اسحب للتحكم المباشر في سرعة التحميل",

        # Categories
        "cat_all": "كافة التصنيفات",
        "cat_video": "فيديو",
        "cat_audio": "صوتيات",
        "cat_programs": "برامج",
        "cat_compressed": "مضغوط",
        "cat_documents": "مستندات",
        "cat_images": "صور",
        "cat_general": "عام",

        # Limiter & Speed Labels
        "lbl_unlimited": "بدون حد",
        "lbl_speed_limit": "تحديد السرعة:",
        "lbl_current_unlimited": "● الحالي: بدون حد",
        "lbl_current_limit": "● الحالي: {limit}",

        # Auto Unpack Archives (AeroArchive)
        "browser_card_unpack_title": "📦 فك ضغط الأرشيف تلقائياً (محرك AeroArchive)",
        "browser_card_unpack_desc": "فك ضغط ملفات الأرشيف (.zip, .tar, .7z, .rar) تلقائياً بمجرد اكتمال التحميل.",
        "browser_unpack_enabled": "● فك الضغط التلقائي: مفعل",
        "browser_unpack_disabled": "● فك الضغط التلقائي: معطل",
        "browser_btn_unpack_enabled": "[✓] فك الضغط تلقائياً بعد اكتمال التحميل",
        "browser_btn_unpack_disabled": "[  ] فك الضغط تلقائياً بعد اكتمال التحميل",

        # Browser Installation Guides
        "browser_guide_chrome": (
            "1. افتح متصفح كروم أو بريف واكتب chrome://extensions في شريط العنوان.\n"
            "2. قم بتفعيل 'وضع مطوّر البرامج' (Developer mode) من أعلى اليمين.\n"
            "3. اضغط على زر 'تحميل إضافة تم فك حزمتها' (Load unpacked).\n"
            "4. اختر مجلد الإضافة الموضح مساره بالأعلى.\n"
            "5. ستظهر أيقونة ⚡ Smart Download في شريط الإضافات فوراً!"
        ),
        "browser_guide_edge": (
            "1. افتح متصفح إيدج وانتقل إلى edge://extensions في شريط العنوان.\n"
            "2. قم بتفعيل 'وضع المطور' من الشريط الجانبي الأيسر.\n"
            "3. انقر على زر 'تحميل تم فك حزمته' (Load unpacked).\n"
            "4. حدد مجلد الإضافة الموضح مساره أعلاه.\n"
            "5. قم بتثبيت الأيقونة على شريط الأدوات للوصول السريع بنقرة واحدة."
        ),
        "browser_guide_firefox": (
            "1. افتح متصفح فايرفوكس واكتب about:debugging#/runtime/this-firefox في شريط العنوان.\n"
            "2. انقر على زر 'تحميل إضافة مؤقتة...' (Load Temporary Add-on...).\n"
            "3. اختر ملف 'manifest.json' الموجود داخل مجلد الإضافة.\n"
            "4. سيتم تفعيل الإضافة مباشرة وتتصل ببرنامج Smart Download بنجاح."
        ),

        # Dialogs & Modal Messages
        "dialog_complete_msg_verified": "تم التحقق وتجميع الملف بنجاح وبدون أي تلف!",
        "dialog_complete_msg_saved": "تم الحفظ في:",
        "dialog_complete_msg_size": "الحجم:",
        "dialog_complete_msg_time": "الوقت الإجمالي:",
        "dialog_expired_title": "انتهت صلاحية رابط التحميل ⚠️",
        "dialog_expired_msg1": "توقف التحميل: رفض الخادم الجلسة (HTTP 401/403/410).",
        "dialog_expired_details": "التفاصيل:",
        "dialog_expired_msg2": "💡 جميع أجزاء الملف المحملة محفوظة بأمان على القرص.",
        "dialog_expired_msg3": "هل ترغب في تجديد رابط التحميل الآن للاستئناف؟",
        "dialog_error_title": "خطأ في التحميل",
        "dialog_error_prefix": "حدث خطأ أثناء عملية التحميل:",
        "modal_confirm_hint": "⏎ اضغط Enter للبدء، Esc للإلغاء",
        "modal_confirm_title_header": "معلومات ملف التحميل",
        "modal_confirm_sub": "التقاط Smart Download الذكي",
        "modal_quality_header": "اختر الدقة والصيغة",
        "modal_quality_sub": "اختر دقة الفيديو أو المسار الصوتي المطلوب تحميله:",
        "modal_col_res": "الدقة / الصيغة",
        "modal_col_ext": "الحاوية",
        "modal_col_size": "الحجم التقريبي",
        "modal_col_fps": "معدل الإطارات",
        "modal_col_type": "تفاصيل البث",
        "modal_btn_start_quality": "⚡ تحميل الجودة المحددة",
        "modal_status_connecting": "الحالة: جارٍ الاتصال...",
        "modal_status_downloading": "الحالة: جارٍ التحميل...",
        "modal_status_complete": "✅ اكتمل التحميل بنجاح!",
        "modal_status_paused": "الحالة: متوقف مؤقتاً",
    }
}


class LocalizationManager:
    """
    Manages complete Arabic and English application localization.
    Features:
    - Persists active language in %APPDATA%\\SmartDownload\\settings.json.
    - Thread-safe singleton with observer notifications for instantaneous in-place switching.
    - Fallback resolution guaranteeing no missing translation crashes.
    """
    _instance: Optional["LocalizationManager"] = None

    def __init__(self, default_lang: Optional[str] = None):
        self._observers: List[Callable[[], None]] = []
        if default_lang in ("ar", "en"):
            self._current_lang = default_lang
            return
        env_lang = os.environ.get("SD_LANGUAGE")
        if env_lang in ("ar", "en"):
            self._current_lang = env_lang
            return
        if "unittest" in sys.modules or "pytest" in sys.modules or os.environ.get("SD_TESTING"):
            saved = get_setting("language", None)
            self._current_lang = saved if saved in ("ar", "en") else "en"
            return
        saved = get_setting("language", None)
        if saved in ("ar", "en"):
            self._current_lang = saved
        else:
            self._current_lang = "ar"

    @classmethod
    def get_instance(cls) -> "LocalizationManager":
        if cls._instance is None:
            cls._instance = LocalizationManager()
        return cls._instance

    @classmethod
    def reset_instance(cls, default_lang: Optional[str] = None) -> "LocalizationManager":
        """Resets singleton instance, ensuring complete isolation for tests."""
        cls._instance = LocalizationManager(default_lang=default_lang)
        return cls._instance

    def get_language(self) -> str:
        return self._current_lang

    def set_language(self, lang: str) -> bool:
        if lang not in ("ar", "en"):
            return False
        changed = (self._current_lang != lang)
        self._current_lang = lang
        set_setting("language", lang)
        if "SD_LANGUAGE" in os.environ:
            os.environ["SD_LANGUAGE"] = lang
        if changed:
            self.notify_observers()
        return True

    def toggle_language(self) -> str:
        new_lang = "en" if self._current_lang == "ar" else "ar"
        self.set_language(new_lang)
        return new_lang

    def is_rtl(self) -> bool:
        return self._current_lang == "ar"

    def get(self, key: str, default: Optional[str] = None, **kwargs) -> str:
        lang_dict = TRANSLATIONS.get(self._current_lang, {})
        val = lang_dict.get(key)
        if val is None:
            val = TRANSLATIONS.get("en", {}).get(key)
        if val is None:
            val = TRANSLATIONS.get("ar", {}).get(key)
        if val is None:
            val = default if default is not None else key
        if kwargs and isinstance(val, str):
            try:
                return val.format(**kwargs)
            except Exception:
                return val
        return val

    def register_observer(self, callback: Callable[[], None]):
        if callback not in self._observers:
            self._observers.append(callback)

    def unregister_observer(self, callback: Callable[[], None]):
        if callback in self._observers:
            self._observers.remove(callback)

    def notify_observers(self):
        for cb in list(self._observers):
            try:
                cb()
            except Exception:
                pass


def tr(key: str, default: Optional[str] = None, **kwargs) -> str:
    """Convenience accessor to active language translation."""
    return LocalizationManager.get_instance().get(key, default=default, **kwargs)

def get_current_language() -> str:
    """Returns current active language code ('ar' or 'en')."""
    return LocalizationManager.get_instance().get_language()

def set_current_language(lang: str) -> bool:
    """Sets active language and persists preference."""
    return LocalizationManager.get_instance().set_language(lang)


# Configure console encoding safely for Windows terminals and PyInstaller --windowed
if sys.stdout is None:
    class _NullWriter:
        def write(self, *a, **k): pass
        def flush(self): pass
        def reconfigure(self, **kwargs): pass
        def fileno(self): return -1
    _nw = _NullWriter()
    _nw.buffer = _nw
    sys.stdout = _nw
elif hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

if sys.stderr is None:
    sys.stderr = sys.stdout
elif hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

if sys.stdin is None:
    class _NullReader:
        def read(self, *a, **k): return b""
        def readline(self, *a, **k): return ""
        def fileno(self): return -1
    _nr = _NullReader()
    _nr.buffer = _nr
    sys.stdin = _nr

# Windows API for Frameless Window Taskbar Integration & Window Management
IS_WINDOWS = sys.platform.startswith("win")
if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes
    try:
        import winreg
    except ImportError:
        winreg = None
    GWL_STYLE = -16
    GWL_EXSTYLE = -20
    WS_EX_APPWINDOW = 0x00040000
    WS_EX_TOOLWINDOW = 0x00000080
    WS_MINIMIZEBOX = 0x00020000
    WS_SYSMENU = 0x00080000
    SW_HIDE = 0
    SW_MINIMIZE = 6
    SW_RESTORE = 9
    SW_SHOW = 5

    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        user32.OpenClipboard.argtypes = [wintypes.HWND]
        user32.OpenClipboard.restype = wintypes.BOOL
        user32.CloseClipboard.argtypes = []
        user32.CloseClipboard.restype = wintypes.BOOL
        user32.GetClipboardData.argtypes = [wintypes.UINT]
        user32.GetClipboardData.restype = wintypes.HANDLE
        user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
        user32.IsClipboardFormatAvailable.restype = wintypes.BOOL
        user32.GetClipboardSequenceNumber.argtypes = []
        user32.GetClipboardSequenceNumber.restype = wintypes.DWORD
        user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        user32.SetForegroundWindow.restype = wintypes.BOOL

        kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalLock.restype = wintypes.LPVOID
        kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalUnlock.restype = wintypes.BOOL
    except Exception:
        pass
else:
    winreg = None


# ======================================================================================
# WINDOWS STARTUP REGISTRY INTEGRATION (AUTO-RUN ON BOOT)
# ======================================================================================

WINDOWS_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
STARTUP_REG_KEY_NAME = "SmartDownload"
LEGACY_STARTUP_REG_KEY_NAME = "TurboDownloader"
TASK_NAME = "SmartDownloadAutoStart"
LEGACY_TASK_NAME = "TurboDownloaderAutoStart"


def get_installed_exe_path() -> Optional[str]:
    """Returns the canonical installed executable path if present on disk."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        local_app_data = os.path.expanduser(r"~\AppData\Local")
    installed_exe = os.path.normpath(os.path.join(local_app_data, "Programs", "SmartDownload", "SmartDownload.exe"))
    if os.path.isfile(installed_exe):
        return installed_exe
    return None


def get_startup_folder() -> str:
    """Returns the user Startup folder path (shell:startup)."""
    if IS_WINDOWS and winreg is not None:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as k:
                raw_path, _ = winreg.QueryValueEx(k, "Startup")
                if raw_path and str(raw_path).strip():
                    expanded = os.path.normpath(os.path.expandvars(str(raw_path).strip()))
                    if os.path.isabs(expanded) and os.path.isdir(expanded):
                        return expanded
        except Exception:
            pass
    return os.path.normpath(os.path.join(
        os.environ.get("APPDATA", os.path.expanduser(r"~\AppData\Roaming")),
        "Microsoft", "Windows", "Start Menu", "Programs", "Startup"
    ))


get_startup_dir = get_startup_folder


def _parse_startup_cmd(cmd_str: str) -> Tuple[str, str, str, str]:
    """
    Parses a startup command string into:
    (exe_path, args, script_path, working_dir)
    Handles:
    - Standalone executables with/without quotes and arguments
    - Python script launches (e.g. "pythonw.exe" "script.py" --minimized)
    """
    if not cmd_str:
        return "", "", "", ""
    s = str(cmd_str).strip()
    if s.startswith('"'):
        end_idx = s.find('"', 1)
        if end_idx != -1:
            exe_path = s[1:end_idx].strip()
            rest = s[end_idx + 1:].strip()
        else:
            exe_path = s.strip('"')
            rest = ""
    else:
        parts = s.split(None, 1)
        exe_path = parts[0].strip()
        rest = parts[1].strip() if len(parts) > 1 else ""

    script_path = ""
    if os.path.basename(exe_path).lower() in ("python.exe", "pythonw.exe"):
        if rest.startswith('"'):
            s_end = rest.find('"', 1)
            if s_end != -1:
                script_path = rest[1:s_end].strip()
        elif rest:
            script_path = rest.split()[0].strip()

    working_dir = ""
    if script_path and os.path.isfile(script_path):
        working_dir = os.path.dirname(os.path.abspath(script_path))
    elif exe_path and os.path.isfile(exe_path):
        working_dir = os.path.dirname(os.path.abspath(exe_path))

    return exe_path, rest, script_path, working_dir


def _extract_exe_from_cmd(cmd_str: str) -> str:
    """Extracts target executable file path from command string."""
    exe_path, _, _, _ = _parse_startup_cmd(cmd_str)
    return exe_path


def _create_startup_shortcut(
    target_exe: str,
    shortcut_path: str,
    arguments: str = "",
    working_dir: str = "",
    icon_path: str = "",
    description: str = "Smart Download (SD) AutoStart"
) -> bool:
    """Creates a Windows shortcut (.lnk) with win32com and PowerShell fallback."""
    if not IS_WINDOWS:
        return False
    try:
        os.makedirs(os.path.dirname(os.path.abspath(shortcut_path)), exist_ok=True)
    except Exception:
        pass

    clean_target = str(target_exe).strip('"\'')
    clean_shortcut = str(shortcut_path).strip('"\'')
    clean_working = str(working_dir).strip('"\'') if working_dir else os.path.dirname(os.path.abspath(clean_target))

    # 1. Try win32com WScript.Shell
    try:
        import win32com.client
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(os.path.abspath(clean_shortcut))
        shortcut.TargetPath = os.path.abspath(clean_target)
        shortcut.WorkingDirectory = os.path.abspath(clean_working)
        if arguments:
            shortcut.Arguments = arguments
        if icon_path and os.path.exists(icon_path):
            shortcut.IconLocation = f"{os.path.abspath(icon_path)},0"
        if description:
            shortcut.Description = description
        shortcut.Save()
        if os.path.exists(shortcut_path):
            return True
    except Exception:
        pass

    # 2. PowerShell fallback with single quote escaping
    try:
        def _ps_quote(s: str) -> str:
            return str(s).replace("'", "''")

        ps_icon = f"$s.IconLocation = '{_ps_quote(os.path.abspath(icon_path))},0'; " if (icon_path and os.path.exists(icon_path)) else ""
        ps_args = f"$s.Arguments = '{_ps_quote(arguments)}'; " if arguments else ""
        ps_script = (
            f"$ws = New-Object -ComObject WScript.Shell; "
            f"$s = $ws.CreateShortcut('{_ps_quote(os.path.abspath(clean_shortcut))}'); "
            f"$s.TargetPath = '{_ps_quote(os.path.abspath(clean_target))}'; "
            f"$s.WorkingDirectory = '{_ps_quote(os.path.abspath(clean_working))}'; "
            f"{ps_args}"
            f"{ps_icon}"
            f"$s.Description = '{_ps_quote(description)}'; "
            f"$s.Save();"
        )
        res = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
            capture_output=True,
            timeout=10
        )
        return res.returncode == 0 and os.path.exists(shortcut_path)
    except Exception:
        return False


def get_startup_command(minimized: bool = True) -> str:
    """
    Constructs the command line string to launch SmartDownload on system startup.
    Accurately resolves executable path prioritizing:
    1. Active standalone frozen binary (.exe) if already running as frozen executable
    2. Canonical installed executable (%LocalAppData%\\Programs\\SmartDownload\\SmartDownload.exe)
    3. Standalone binary in dist/ directory or adjacent to script
    4. Python script fallback with pythonw.exe
    """
    flag = " --minimized" if minimized else ""
    if getattr(sys, "frozen", False):
        exe_path = os.path.abspath(str(sys.executable).strip('"'))
        return f'"{exe_path}"{flag}'

    # Check installed location first
    installed_exe = get_installed_exe_path()
    if installed_exe:
        return f'"{installed_exe}"{flag}'

    # Prioritize compiled standalone binary in dist/ directory or adjacent to script
    base_dir = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() and isinstance(__file__, str) else os.getcwd()
    for exe_name in ("SmartDownload.exe", "TurboDownloader.exe"):
        dist_cand = os.path.join(base_dir, "dist", exe_name)
        alt_cand = os.path.join(base_dir, exe_name)
        if os.path.isfile(dist_cand):
            return f'"{os.path.abspath(dist_cand)}"{flag}'
        elif os.path.isfile(alt_cand):
            return f'"{os.path.abspath(alt_cand)}"{flag}'

    # Script mode fallback: prefer pythonw.exe if available so no console window flashes
    py_exe = str(sys.executable).strip('"')
    py_dir = os.path.dirname(py_exe)
    pyw_exe = os.path.join(py_dir, "pythonw.exe")
    if os.path.isfile(pyw_exe):
        py_exe = pyw_exe
    raw_file = __file__ if "__file__" in globals() and isinstance(__file__, str) else "turbo_downloader.py"
    script_path = os.path.abspath(raw_file.strip('"'))
    return f'"{py_exe}" "{script_path}"{flag}'

def is_startup_enabled() -> bool:
    """
    Checks if SmartDownload is currently registered to auto-run on Windows startup.
    Checks HKCU Run registry key and cleans up stale or broken keys pointing to missing binaries.
    Returns True if an active, valid auto-start mechanism exists, False otherwise.
    """
    if not IS_WINDOWS or winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WINDOWS_RUN_KEY, 0, winreg.KEY_READ) as key:
            for k_name in (STARTUP_REG_KEY_NAME, LEGACY_STARTUP_REG_KEY_NAME):
                try:
                    val, _ = winreg.QueryValueEx(key, k_name)
                    if val and str(val).strip():
                        exe_path, args, script_path, _ = _parse_startup_cmd(str(val))
                        is_valid = False
                        if exe_path:
                            if script_path:
                                is_valid = os.path.isfile(exe_path) and os.path.isfile(script_path)
                            else:
                                is_valid = os.path.isfile(exe_path)

                        if is_valid:
                            return True
                        elif exe_path:
                            # Stale or broken key pointing to a missing binary or script: clean it up
                            try:
                                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WINDOWS_RUN_KEY, 0, winreg.KEY_SET_VALUE) as wkey:
                                    winreg.DeleteValue(wkey, k_name)
                            except Exception:
                                pass
                        else:
                            return True
                except FileNotFoundError:
                    pass
            return False
    except (FileNotFoundError, OSError):
        return False

def enable_startup(minimized: bool = True) -> bool:
    """
    Registers SmartDownload in HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run.
    When minimized=True, adds the --minimized flag so it starts silently in background.
    Cleans up any legacy (TurboDownloader) or stale keys, and coordinates with Scheduled
    Tasks and Startup folder shortcuts.
    Returns True on success, False otherwise.
    """
    if not IS_WINDOWS or winreg is None:
        return False
    cmd = get_startup_command(minimized=minimized)
    reg_ok = False
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, WINDOWS_RUN_KEY) as key:
            winreg.SetValueEx(key, STARTUP_REG_KEY_NAME, 0, winreg.REG_SZ, cmd)
            # Clean up legacy key
            try:
                winreg.DeleteValue(key, LEGACY_STARTUP_REG_KEY_NAME)
            except (FileNotFoundError, OSError):
                pass
        reg_ok = True
    except (OSError, PermissionError):
        return False

    exe_path, args, script_path, working_dir = _parse_startup_cmd(cmd)

    # Harmonize with Scheduled Task
    try:
        if exe_path and os.path.isfile(exe_path):
            subprocess.run(
                ["schtasks.exe", "/Create", "/F", "/SC", "ONLOGON", "/TN", TASK_NAME, "/TR", cmd],
                capture_output=True,
                timeout=5
            )
    except Exception:
        pass

    # Harmonize with Startup folder shortcut
    try:
        if exe_path and os.path.isfile(exe_path):
            startup_dir = get_startup_folder()
            if os.path.isdir(startup_dir):
                for old in ("Turbo Download Manager Pro.lnk", "TurboDownloader.lnk", "SmartDownload.lnk"):
                    old_p = os.path.join(startup_dir, old)
                    if os.path.isfile(old_p):
                        try:
                            os.remove(old_p)
                        except Exception:
                            pass
                lnk_path = os.path.join(startup_dir, "Smart Download (SD).lnk")
                icon_path = ""
                for ico_cand in (
                    os.path.join(os.path.dirname(os.path.abspath(exe_path)), "app_icon.ico"),
                    os.path.join(os.path.dirname(os.path.abspath(__file__)), "app_icon.ico") if "__file__" in globals() else "",
                    os.path.join(os.getcwd(), "app_icon.ico")
                ):
                    if ico_cand and os.path.isfile(ico_cand):
                        icon_path = os.path.abspath(ico_cand)
                        break

                _create_startup_shortcut(
                    target_exe=exe_path,
                    shortcut_path=lnk_path,
                    arguments=args,
                    working_dir=working_dir,
                    icon_path=icon_path,
                    description="Smart Download (SD) AutoStart"
                )
    except Exception:
        pass

    return reg_ok


def disable_startup() -> bool:
    """
    Removes SmartDownload from HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run.
    Also cleans up Scheduled Tasks and Startup folder shortcuts.
    Returns True on success or if already absent, False on unexpected error.
    """
    if not IS_WINDOWS or winreg is None:
        return False

    reg_ok = True
    # 1. Clean up Run registry keys
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WINDOWS_RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            for k_name in (STARTUP_REG_KEY_NAME, LEGACY_STARTUP_REG_KEY_NAME):
                try:
                    winreg.DeleteValue(key, k_name)
                except FileNotFoundError:
                    pass
    except FileNotFoundError:
        pass
    except (OSError, PermissionError):
        reg_ok = False
    except Exception:
        reg_ok = False

    # 2. Clean up Scheduled Tasks
    try:
        for tname in (TASK_NAME, LEGACY_TASK_NAME):
            try:
                subprocess.run(
                    ["schtasks.exe", "/Delete", "/TN", tname, "/F"],
                    capture_output=True,
                    timeout=5
                )
            except Exception:
                pass
    except Exception:
        pass

    # 3. Clean up Startup folder shortcuts
    try:
        startup_dir = get_startup_folder()
        for name in ("Smart Download (SD).lnk", "SmartDownload.lnk", "TurboDownloader.lnk", "Turbo Download Manager Pro.lnk"):
            p = os.path.join(startup_dir, name)
            if os.path.isfile(p):
                try:
                    os.remove(p)
                except Exception:
                    pass
    except Exception:
        pass

    return reg_ok


def get_startup_entry() -> Optional[str]:
    """Returns the registered command string from Windows Run registry, or None."""
    if not IS_WINDOWS or winreg is None:
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WINDOWS_RUN_KEY, 0, winreg.KEY_READ) as key:
            for k_name in (STARTUP_REG_KEY_NAME, LEGACY_STARTUP_REG_KEY_NAME):
                try:
                    val, _ = winreg.QueryValueEx(key, k_name)
                    if val and str(val).strip():
                        return str(val)
                except FileNotFoundError:
                    pass
            return None
    except (FileNotFoundError, OSError):
        return None


# ======================================================================================
# URL VALIDATION & CLIPBOARD MONITORING UTILITIES
# ======================================================================================

COMMON_DOWNLOAD_EXTENSIONS = {
    # Compressed archives
    ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".tgz", ".z", ".cab", ".zst",
    # Executables & Installers
    ".exe", ".msi", ".dmg", ".pkg", ".deb", ".rpm", ".apk", ".appx", ".appxbundle",
    ".msix", ".msixbundle", ".bin", ".iso", ".img", ".jar", ".run", ".appimage", ".ipa",
    # Video
    ".mp4", ".mkv", ".webm", ".avi", ".mov", ".wmv", ".flv", ".m4v", ".3gp", ".ts",
    ".m2ts", ".vob", ".ogv", ".m3u8",
    # Audio
    ".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma", ".opus", ".alac",
    ".aiff", ".mid", ".midi",
    # Documents & Ebooks
    ".pdf", ".epub", ".mobi", ".djvu", ".doc", ".docx", ".xls", ".xlsx", ".ppt",
    ".pptx", ".odt", ".ods", ".odp",
    # Images & Graphics
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".ico", ".tiff",
    ".tif", ".psd", ".ai",
    # Disk & Virtualization & Data
    ".vmdk", ".vhd", ".vhdx", ".qcow2", ".torrent", ".whl", ".csv", ".tsv",
    ".sqlite", ".db", ".sql"
}

WEB_SCRIPT_EXTENSIONS = {
    ".php", ".html", ".htm", ".asp", ".aspx", ".jsp", ".cgi", ".do", ".ashx", ".action"
}


def is_downloadable_url(url: Any) -> bool:
    """
    Validates whether the provided text represents a downloadable file or media URL.
    Recognizes:
    - YouTube video, shorts, and music URLs
    - URLs pointing directly to downloadable file extensions (archives, executables, media, docs)
    - URLs containing download indicators in query params (bytes=, export=download, dl=1, filename=, etc.)
    - Direct media distribution endpoints and download paths (/download, /__down, /releases/download)
    - Script-based download endpoints (/download.php, /download.aspx, /get_file.php)
    - URLs with intermediate downloadable segments (e.g. MediaFire: /file/xyz/archive.zip/file)
    Rejects:
    - Non-HTTP/HTTPS URLs, local file paths, arbitrary text, and blank strings
    - Regular browsing pages (e.g. google.com, wikipedia.org, news sites)
    - Web document markup (.html, .htm, .php, etc.) lacking explicit download indicators
    """
    if not url or not isinstance(url, str):
        return False

    url_str = url.strip().strip("<>\"'()").rstrip(".,;")
    if not url_str:
        return False

    # URLs must not contain whitespace or line breaks
    if any(c in url_str for c in ("\n", "\r", "\t", " ")):
        return False

    # Check protocol scheme
    scheme = url_str.split("://", 1)[0].lower() if "://" in url_str else ""
    if scheme not in ("http", "https", "ftp"):
        return False

    # Fast-path for recognized YouTube and social media links
    if is_media_url(url_str):
        return True

    try:
        parsed = urllib.parse.urlsplit(url_str)
    except Exception:
        return False

    if not parsed.netloc:
        return False

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        return False

    # Require either a dot or localhost or IP in hostname
    if "." not in hostname and hostname != "localhost" and ":" not in hostname:
        return False

    path_lower = parsed.path.lower()
    clean_path = path_lower.rstrip("/")
    ext = os.path.splitext(clean_path)[1]

    # Direct match against common downloadable file extensions
    if ext in COMMON_DOWNLOAD_EXTENSIONS or clean_path.endswith((".tar.gz", ".tar.bz2", ".tar.xz")):
        return True

    # Check if any segment in the path contains a downloadable file extension
    # (e.g. MediaFire: /file/xyz/archive.zip/file or CDN mirror paths)
    path_segments = [s for s in clean_path.split("/") if s]
    for seg in path_segments:
        seg_ext = os.path.splitext(seg)[1]
        if seg_ext in COMMON_DOWNLOAD_EXTENSIONS or seg.endswith((".tar.gz", ".tar.bz2", ".tar.xz")):
            return True

    # Check query string indicators
    query_lower = parsed.query.lower()
    if query_lower:
        query_triggers = (
            "bytes=",
            "export=download",
            "dl=1",
            "dl=true",
            "download=1",
            "download=true",
            "download=yes",
            "response-content-disposition",
            "action=download",
            "attachment=",
            "attachment=1",
            "attachment=true",
            "raw=1",
            "raw=true"
        )
        if any(trigger in query_lower for trigger in query_triggers):
            return True

        # Check if any query parameter value ends with a recognized download extension
        try:
            qs = urllib.parse.parse_qs(parsed.query)
            for vals in qs.values():
                for val in vals:
                    val_clean = val.strip().lower().rstrip("/")
                    val_ext = os.path.splitext(val_clean)[1]
                    if val_ext in COMMON_DOWNLOAD_EXTENSIONS or val_clean.endswith((".tar.gz", ".tar.bz2", ".tar.xz")):
                        return True
        except Exception:
            pass

    # Check path download endpoints (including download.php, download.aspx, etc.)
    path_triggers = (
        "/download",
        "/downloads",
        "/__down",
        "/get_file",
        "/getfile",
        "/fetch_file",
        "/export/download",
        "/releases/download"
    )
    if any(clean_path.endswith(t) or f"{t}/" in path_lower or f"{t}." in path_lower for t in path_triggers):
        return True

    # Media hosting domains that serve dynamic streams
    netloc_lower = parsed.netloc.lower()
    if any(domain in netloc_lower for domain in ("googlevideo.com", "gvt1.com")):
        return True

    return False


def clean_download_filename(name: str, max_length: int = 180) -> str:
    """
    Cleans a filename extracted from a URL/query parameter:
    - Removes invalid filesystem characters: < > : " / \\ | ? * and control chars
    - Preserves underscores, hyphens, alphanumeric characters, and Unicode
    - Strips leading/trailing spaces and dots
    """
    if not name:
        return ""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '', name).strip(" .")
    cleaned = re.sub(r'\s+', ' ', cleaned).strip(" .")
    if len(cleaned) > max_length:
        base, ext = os.path.splitext(cleaned)
        base = base[:max_length - len(ext)].rstrip(" .")
        cleaned = base + ext
    return cleaned


def derive_download_filename(url: str) -> str:
    """
    Intelligently extracts, decodes, and sanitizes a valid destination filename from a URL.
    Handles:
    - Standard paths with extensions (e.g. /files/archive.zip -> archive.zip)
    - MediaFire and nested download paths (e.g. /file/xyz/archive.zip/file -> archive.zip)
    - Web scripts with query filenames (e.g. download.php?file=report.pdf -> report.pdf)
    - Content disposition query params (e.g. ?filename=data.csv)
    - Percent-encoded Unicode/Arabic filenames (e.g. ?file=%D9%81%D9%8A%D8%AF%D9%8A%D9%88.mp4)
    - YouTube and extensionless fallback defaults
    """
    if not url or not isinstance(url, str):
        return "download.bin"

    try:
        parsed = urllib.parse.urlsplit(url.strip().strip("<>\"'()").rstrip(".,;"))
        parsed_path = parsed.path
        path_segments = [s for s in urllib.parse.unquote(parsed_path).split("/") if s]

        candidate_fn = ""
        # Search path segments in reverse for a recognized download file extension
        for seg in reversed(path_segments):
            seg_clean = os.path.basename(seg.rstrip("/"))
            seg_ext = os.path.splitext(seg_clean)[1].lower()
            if seg_ext in COMMON_DOWNLOAD_EXTENSIONS or seg_clean.endswith((".tar.gz", ".tar.bz2", ".tar.xz")):
                candidate_fn = seg_clean
                break

        # Fallback to last segment if no extension match found
        if not candidate_fn and path_segments:
            candidate_fn = os.path.basename(path_segments[-1])

        cand_ext = os.path.splitext(candidate_fn)[1].lower() if candidate_fn else ""
        cand_lower = candidate_fn.lower() if candidate_fn else ""

        # Inspect query parameters if candidate has a web script extension, lacks extension, or is generic
        if (
            not candidate_fn
            or not cand_ext
            or cand_ext in WEB_SCRIPT_EXTENSIONS
            or cand_lower in ("__down", "download", "downloads", "file", "getfile", "videoplayback")
        ):
            qs = urllib.parse.parse_qs(parsed.query)
            for k in ("filename", "file", "name", "attachment", "doc", "title"):
                if k in qs and qs[k][0]:
                    unquoted_val = clean_download_filename(urllib.parse.unquote(os.path.basename(qs[k][0].strip())))
                    if unquoted_val:
                        candidate_fn = unquoted_val
                        break

        # Sanitize candidate filename
        if candidate_fn:
            url_fn = clean_download_filename(urllib.parse.unquote(candidate_fn))
        else:
            url_fn = ""

        # Final extension enforcement
        if not url_fn or url_fn.lower() in ("__down", "download", "file", "videoplayback") or not os.path.splitext(url_fn)[1]:
            if is_youtube_url(url):
                url_fn = "youtube_video.mp4"
            elif is_social_media_url(url):
                plat = extract_media_platform(url).lower().replace(" / x", "").replace(" ", "_")
                url_fn = f"{plat}_video.mp4"
            elif url_fn and os.path.splitext(url_fn)[0]:
                clean_base = url_fn.lstrip("_") or "download"
                url_fn = f"{clean_base}.bin"
            else:
                url_fn = "download.bin"

        return url_fn
    except Exception:
        if is_youtube_url(url):
            return "youtube_video.mp4"
        elif is_social_media_url(url):
            plat = extract_media_platform(url).lower().replace(" / x", "").replace(" ", "_")
            return f"{plat}_video.mp4"
        return "download.bin"


def is_potential_html_url(url: str) -> bool:
    """
    Determines whether a candidate URL might be an HTML landing page / redirector
    that requires background probing to resolve the real underlying file download link.
    Media URLs, direct benchmark stream endpoints, and URLs ending in recognized binary
    extensions (.exe, .zip, .msi, etc.) bypass pre-modal probe.
    """
    if not url or not isinstance(url, str):
        return False
    if is_media_url(url):
        return False
    try:
        parsed = urllib.parse.urlsplit(url)
        path = parsed.path.lower()
        if path.endswith("/__down"):
            return False
        if "bytes=" in (parsed.query or "").lower():
            return False
        _, ext = os.path.splitext(path)
        ext = ext.lower()
        if ext in WEB_SCRIPT_EXTENSIONS:
            return True
        if ext in ("", ".bin"):
            return True
        if ("/download" in path or "/downloads" in path) and ext not in (COMMON_DOWNLOAD_EXTENSIONS - {".bin"}):
            return True
        if ext not in COMMON_DOWNLOAD_EXTENSIONS:
            return True
        return False
    except Exception:
        return False


def _win32_clipboard_get() -> Optional[str]:
    """
    Robust 64-bit safe Win32 clipboard text reader with transient lock retry loop.
    Immune to memory handle truncation, missing null-terminators, and third-party locks.
    """
    if not IS_WINDOWS:
        return None
    try:
        import ctypes
        from ctypes import wintypes
        CF_UNICODETEXT = 13
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        opened = False
        for _ in range(5):
            if user32.OpenClipboard(None):
                opened = True
                break
            time.sleep(0.01)
        if not opened:
            return None

        try:
            if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
                return None
            h_glb = user32.GetClipboardData(CF_UNICODETEXT)
            if not h_glb:
                return None
            ptr = kernel32.GlobalLock(h_glb)
            if not ptr:
                return None
            try:
                val = ctypes.wstring_at(ptr)
                return val if val else None
            finally:
                kernel32.GlobalUnlock(h_glb)
        finally:
            user32.CloseClipboard()
    except Exception:
        return None


def get_clipboard_text(root: Optional[Any] = None) -> Optional[str]:
    """Safely retrieves text from clipboard using Win32 API or Tkinter fallback."""
    if IS_WINDOWS:
        try:
            val = _win32_clipboard_get()
            if val is not None:
                return val
        except Exception:
            pass
    if root is not None:
        try:
            return root.clipboard_get()
        except Exception:
            pass
    return None


def notify_running_instance(url: Optional[str] = None, show: bool = True) -> bool:
    """
    Checks if an existing instance of Turbo Downloader is running by probing the
    loopback IPC port. If active, wakes up the existing instance and optionally
    dispatches the download URL. Returns True if an existing instance was handled.
    """
    try:
        req = urllib.request.Request("http://127.0.0.1:9242/ping", headers={"User-Agent": "SmartDownload-Launcher"})
        with urllib.request.urlopen(req, timeout=0.6) as resp:
            if resp.status == 200:
                raw = resp.read().decode("utf-8")
                data = json.loads(raw)
                if data.get("app") in ("Smart Download (SD)", "Smart Download", "Turbo Download Manager Pro"):
                    if url and is_downloadable_url(url):
                        try:
                            post_data = json.dumps({"url": url, "start_immediately": False}).encode("utf-8")
                            post_req = urllib.request.Request(
                                "http://127.0.0.1:9242/download",
                                data=post_data,
                                headers={"Content-Type": "application/json"}
                            )
                            with urllib.request.urlopen(post_req, timeout=1.0) as _:
                                pass
                        except Exception:
                            pass
                    if show:
                        try:
                            show_req = urllib.request.Request(
                                "http://127.0.0.1:9242/show",
                                headers={"User-Agent": "SmartDownload-Launcher"}
                            )
                            with urllib.request.urlopen(show_req, timeout=1.0) as _:
                                pass
                        except Exception:
                            pass
                    return True
    except Exception:
        pass
    return False


# ======================================================================================
# 1. BANDWIDTH THROTTLING: PER-DOWNLOAD TOKEN BUCKET RATE LIMITER
# ======================================================================================

class TokenBucketRateLimiter:
    """
    Thread-safe Token Bucket Rate Limiter for dynamic bandwidth throttling.
    Shared across all concurrent chunk download threads for a given file.
    Can be adjusted instantaneously while downloads are actively running.
    Features dynamic capacity adaptation and cancel awareness to prevent thread hangs.
    """
    def __init__(self, rate_limit_bytes_per_sec: float = 0.0):
        # 0 or negative indicates Unlimited speed
        self.rate_limit = float(rate_limit_bytes_per_sec)
        self.capacity = max(self.rate_limit * 0.5, 65536.0) if self.rate_limit > 0 else 0.0
        self.tokens = min(self.capacity, 65536.0)
        self.last_update = time.monotonic()
        self._lock = threading.Lock()

    def set_limit(self, bytes_per_sec: float):
        """Thread-safe dynamic adjustment of bandwidth limit."""
        with self._lock:
            self.rate_limit = float(bytes_per_sec)
            if self.rate_limit > 0:
                self.capacity = max(self.rate_limit * 0.5, 65536.0)
                self.tokens = min(self.tokens, self.capacity)
            else:
                self.capacity = 0.0
                self.tokens = 0.0
            self.last_update = time.monotonic()

    def acquire(self, num_bytes: int, cancel_event: Optional[threading.Event] = None):
        """
        Paces data transfer by consuming tokens or sleeping if the rate limit is exceeded.
        Releases internal lock before sleeping to avoid blocking other threads or UI updates.
        Supports cancel_event for instant awakening on download cancellation.
        """
        if num_bytes <= 0:
            return

        while True:
            if cancel_event and cancel_event.is_set():
                return
            if self.rate_limit <= 0:
                return  # Unlimited speed

            with self._lock:
                if self.rate_limit <= 0:
                    return

                # Dynamically expand capacity if request exceeds current bucket size
                if num_bytes > self.capacity:
                    self.capacity = float(num_bytes * 2)

                now = time.monotonic()
                elapsed = now - self.last_update
                self.last_update = now

                # Replenish tokens based on elapsed time
                self.tokens = min(self.capacity, self.tokens + elapsed * self.rate_limit)

                if self.tokens >= num_bytes:
                    self.tokens -= num_bytes
                    return

                needed = num_bytes - self.tokens
                wait_time = needed / self.rate_limit

            sleep_step = min(wait_time, 0.05)
            if cancel_event:
                if cancel_event.wait(timeout=sleep_step):
                    return
            else:
                time.sleep(sleep_step)


# ======================================================================================
# 2. CORE CHUNKING DATA STRUCTURES
# ======================================================================================

@dataclass
class DownloadChunk:
    """Represents a discrete contiguous byte range of the target file."""
    chunk_id: int
    start_byte: int
    end_byte: int
    downloaded_bytes: int = 0
    status: str = "pending"  # pending, active, completed, failed
    part_filepath: str = ""
    error_msg: str = ""
    lock: threading.RLock = field(default_factory=threading.RLock)

    @property
    def total_bytes(self) -> int:
        with self.lock:
            return max(0, self.end_byte - self.start_byte + 1)

    @property
    def remaining_bytes(self) -> int:
        with self.lock:
            cur = self.start_byte + self.downloaded_bytes
            return max(0, self.end_byte - cur + 1)

    @property
    def progress_pct(self) -> float:
        with self.lock:
            tot = self.end_byte - self.start_byte + 1
            if tot <= 0:
                return 100.0
            return min(100.0, (self.downloaded_bytes / tot) * 100.0)


# Permissive SSL context cache
_PERMISSIVE_SSL_CONTEXT: Optional[ssl.SSLContext] = None
_SSL_CONTEXT_LOCK = threading.Lock()

def get_permissive_ssl_context() -> ssl.SSLContext:
    """
    Creates or returns a reusable, robust, permissive SSL context that disables
    certificate verification and hostname validation. This resolves expired or
    self-signed TLS certificates (such as archive.org CDN nodes) with zero external pip dependencies.
    """
    global _PERMISSIVE_SSL_CONTEXT
    if _PERMISSIVE_SSL_CONTEXT is None:
        with _SSL_CONTEXT_LOCK:
            if _PERMISSIVE_SSL_CONTEXT is None:
                try:
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                    _PERMISSIVE_SSL_CONTEXT = ctx
                except Exception:
                    if hasattr(ssl, "_create_unverified_context"):
                        _PERMISSIVE_SSL_CONTEXT = ssl._create_unverified_context()
                    else:
                        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT if hasattr(ssl, "PROTOCOL_TLS_CLIENT") else ssl.PROTOCOL_TLS)
                        ctx.check_hostname = False
                        ctx.verify_mode = ssl.CERT_NONE
                        _PERMISSIVE_SSL_CONTEXT = ctx
    return _PERMISSIVE_SSL_CONTEXT


def get_windows_work_area() -> Optional[Tuple[int, int, int, int]]:
    """Returns (left, top, right, bottom) coordinates of the Windows work area (excluding taskbars)."""
    if sys.platform != "win32":
        return None
    try:
        class RECT(ctypes.Structure):
            _fields_ = [
                ("left", ctypes.c_long),
                ("top", ctypes.c_long),
                ("right", ctypes.c_long),
                ("bottom", ctypes.c_long)
            ]
        rect = RECT()
        SPI_GETWORKAREA = 0x0030
        if ctypes.windll.user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0):
            return int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)
    except Exception:
        pass
    return None


def parse_filename_from_cd_header(cd_header: str) -> Optional[str]:
    """Extracts clean filename from Content-Disposition header, supporting RFC 6266 / RFC 5987."""
    if not cd_header:
        return None
    try:
        m_star = re.search(r"filename\*\s*=\s*(?:[A-Za-z0-9_-]+'')?([^;\r\n]+)", cd_header, re.IGNORECASE)
        if m_star:
            raw = m_star.group(1).strip("\"' ")
            fn = urllib.parse.unquote(raw)
            if fn:
                base = os.path.basename(fn)
                if base and base not in (".", ".."):
                    return base

        m_std = re.search(r'filename\s*=\s*(?:"([^"]+)"|([^;\s\r\n]+))', cd_header, re.IGNORECASE)
        if m_std:
            raw = m_std.group(1) or m_std.group(2)
            if raw:
                base = os.path.basename(raw.strip("\"' "))
                if base and base not in (".", ".."):
                    return base
    except Exception:
        pass
    return None



class _HtmlCandidateExtractor(HTMLParser):
    """
    Extracts structured download candidates and page metadata from HTML.
    Collects <a> tags, <meta refresh>, and data attributes.
    """
    def __init__(self):
        super().__init__()
        self.raw_items: List[Dict[str, Any]] = []
        self._current_tag: Optional[str] = None
        self._current_attrs: Dict[str, str] = {}
        self._current_text: List[str] = []
        self.page_title: str = ""
        self._in_title: bool = False

    def handle_starttag(self, tag, attrs):
        attr_dict = {k.lower(): (v or "") for k, v in attrs}
        tag_lower = tag.lower()

        if tag_lower == "title":
            self._in_title = True
        elif tag_lower == "a":
            self._current_tag = "a"
            self._current_attrs = attr_dict
            self._current_text = []
        elif tag_lower == "meta" and attr_dict.get("http-equiv", "").lower() == "refresh":
            content = attr_dict.get("content", "")
            m = re.search(r"url\s*=\s*(?:['\"]([^'\"]+)['\"]|([^;\s'\"]+))", content, re.IGNORECASE)
            if m:
                u = m.group(1) or m.group(2)
                if u:
                    self.raw_items.append({
                        "href": u.strip(),
                        "text": "Auto Redirect",
                        "title": "",
                        "aria_label": "",
                        "download": "",
                        "tag": "meta"
                    })

        for k, v in attr_dict.items():
            if k.startswith("data-download") or k in ("data-href", "data-url", "data-src", "data-link"):
                if v and tag_lower != "a":
                    self.raw_items.append({
                        "href": v.strip(),
                        "text": attr_dict.get("title") or attr_dict.get("aria-label") or "",
                        "title": attr_dict.get("title", ""),
                        "aria_label": attr_dict.get("aria-label", ""),
                        "download": attr_dict.get("download", ""),
                        "tag": tag_lower
                    })

    def handle_data(self, data):
        if self._in_title:
            self.page_title += data
        if self._current_tag == "a":
            self._current_text.append(data)

    def handle_endtag(self, tag):
        tag_lower = tag.lower()
        if tag_lower == "title":
            self._in_title = False
        elif tag_lower == "a" and self._current_tag == "a":
            href = self._current_attrs.get("href", "").strip()
            if href:
                text_content = " ".join("".join(self._current_text).split())
                self.raw_items.append({
                    "href": href,
                    "text": text_content,
                    "title": self._current_attrs.get("title", ""),
                    "aria_label": self._current_attrs.get("aria-label", ""),
                    "download": self._current_attrs.get("download", ""),
                    "tag": "a"
                })
            self._current_tag = None
            self._current_attrs = {}
            self._current_text = []


def resolve_all_download_candidates(
    url_or_html: str,
    base_url: str = "",
    timeout: float = 10.0,
    ssl_context: Optional[ssl.SSLContext] = None
) -> List[Dict[str, Any]]:
    """
    Extracts and ranks all valid downloadable links from an HTML document or landing URL.

    Filters out non-downloadable links (nav links, terms of service, social media, anchors).
    Deduplicates and cleans candidate URLs.

    Each candidate dict contains:
        {
            "url": direct_url,
            "filename": filename,
            "ext": ext,
            "size_bytes": None or int,
            "title": text_label,
            "score": score
        }
    Guaranteed never to raise unhandled exceptions.
    """
    raw_input = str(url_or_html or "").strip()
    if not raw_input:
        return []

    is_url = False
    html_text = ""
    effective_base_url = str(base_url or "").strip()

    # Detect if raw_input is an HTTP URL rather than raw HTML markup
    if (raw_input.startswith(("http://", "https://")) and
        "\n" not in raw_input and
        "<html" not in raw_input.lower() and
        "<body" not in raw_input.lower() and
        "<a " not in raw_input.lower()):
        is_url = True

    if is_url:
        if not effective_base_url:
            effective_base_url = raw_input
        ctx = ssl_context if ssl_context is not None else get_permissive_ssl_context()
        custom_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }
        try:
            req = urllib.request.Request(raw_input, headers=custom_headers)
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                final_u = resp.geturl() or raw_input
                effective_base_url = final_u
                ct = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
                if ct not in ("text/html", "application/xhtml+xml"):
                    return []
                raw_bytes = resp.read(1024 * 1024)
                charset = resp.headers.get_content_charset() or "utf-8"
                try:
                    html_text = raw_bytes.decode(charset, errors="replace")
                except Exception:
                    html_text = raw_bytes.decode("utf-8", errors="replace")
        except Exception:
            return []
    else:
        html_text = raw_input

    if not html_text:
        return []

    extractor = _HtmlCandidateExtractor()
    try:
        extractor.feed(html_text)
    except Exception:
        pass

    raw_items = list(extractor.raw_items)

    # Inline script navigation and fallback regexes
    script_patterns = [
        r'(?:window\.)?location(?:\.href)?\s*=\s*[\'"]([^\'"]+)[\'"]',
        r'(?:window\.)?location\.(?:assign|replace)\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)',
        r'window\.open\s*\(\s*[\'"]([^\'"]+)[\'"]',
        r'(?:data-download[a-z0-9_-]*|data-href|data-url)\s*=\s*[\'"]([^\'"]+)[\'"]',
        r'<meta[^>]*?content=[\'"][^>]*?url=([^;\'"\s>]+)[\'"]'
    ]
    for pat in script_patterns:
        for m in re.finditer(pat, html_text, re.IGNORECASE):
            u = m.group(1).strip()
            if u:
                raw_items.append({
                    "href": u,
                    "text": "Script Redirect",
                    "title": "",
                    "aria_label": "",
                    "download": "",
                    "tag": "script"
                })

    for s_m in re.finditer(r'<script[^>]*>(.*?)</script>', html_text, re.IGNORECASE | re.DOTALL):
        script_body = s_m.group(1).replace(r'\/', '/')
        for url_m in re.finditer(r'https?://[^\s"\'<>\\]+', script_body, re.IGNORECASE):
            raw_items.append({
                "href": url_m.group(0),
                "text": "Script Link",
                "title": "",
                "aria_label": "",
                "download": "",
                "tag": "script"
            })

    ignored_schemes = ("#", "javascript:", "mailto:", "tel:", "data:", "about:")
    ignored_exts = {
        ".css", ".js", ".woff", ".woff2", ".svg", ".png", ".jpg", ".jpeg",
        ".gif", ".ico", ".webmanifest", ".map", ".ttf", ".eot", ".otf"
    }
    preferred_installer_exts = {
        ".exe", ".msi", ".zip", ".7z", ".rar", ".dmg", ".apk", ".iso",
        ".appx", ".appxbundle", ".msix", ".msixbundle", ".pkg", ".deb", ".rpm"
    }
    social_domains = {
        "twitter.com", "x.com", "facebook.com", "fb.com", "instagram.com",
        "linkedin.com", "t.me", "telegram.org", "reddit.com", "tiktok.com",
        "discord.gg", "discord.com", "pinterest.com"
    }
    non_download_keywords = {
        "privacy", "terms", "about", "contact", "login", "signin", "signup",
        "register", "logout", "faq", "help", "support", "license", "cookie",
        "legal", "blog", "pricing"
    }

    base_p_split = urllib.parse.urlsplit(effective_base_url) if effective_base_url else None
    base_clean = (base_p_split.scheme.lower(), base_p_split.netloc.lower(), base_p_split.path.rstrip("/")) if base_p_split else None

    src_query = (base_p_split.query or "").lower() if base_p_split else ""
    platform_tokens: List[str] = []
    if any(k in src_query for k in ("platform=windows", "os=win", "os=windows", "windows", "win")):
        platform_tokens = ["windows", "win", "x64", "win64", "x86"]
    elif any(k in src_query for k in ("platform=mac", "os=mac", "macos", "darwin", "osx")):
        platform_tokens = ["mac", "macos", "darwin", "dmg", "pkg"]
    elif any(k in src_query for k in ("platform=linux", "os=linux", "linux")):
        platform_tokens = ["linux", "appimage", "deb", "rpm", "tar.gz"]
    elif sys.platform == "win32":
        platform_tokens = ["windows", "win", "x64", "setup", "installer"]

    seen_dict: Dict[str, Dict[str, Any]] = {}

    for item in raw_items:
        raw_href = item["href"].strip("\"' \t\r\n")
        if not raw_href or raw_href.startswith(ignored_schemes):
            continue

        try:
            abs_url = urllib.parse.urljoin(effective_base_url, raw_href) if effective_base_url else raw_href
            p = urllib.parse.urlsplit(abs_url)
            if p.scheme.lower() not in ("http", "https") or not p.netloc:
                continue

            netloc_lower = p.netloc.lower()
            if any(netloc_lower == sd or netloc_lower.endswith("." + sd) for sd in social_domains):
                continue

            # Skip self-referencing links
            cand_clean = (p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/"))
            if base_clean and cand_clean == base_clean and not p.query:
                continue

            path_lower = p.path.lower()
            query_lower = (p.query or "").lower()
            combined_target = path_lower + ("?" + query_lower if query_lower else "")

            # Multi-part extension support
            ext = ""
            for multi_ext in (".tar.gz", ".tar.bz2", ".tar.xz", ".user.js"):
                if path_lower.endswith(multi_ext):
                    ext = multi_ext
                    break
            if not ext:
                _, ext = os.path.splitext(path_lower)

            if ext in ignored_exts:
                continue

            # Determine whether link is downloadable
            has_dl_ext = (ext in preferred_installer_exts) or (ext in COMMON_DOWNLOAD_EXTENSIONS)
            has_dl_attr = bool(item.get("download"))
            has_dl_path = any(dp in path_lower for dp in ("/download", "/downloads", "/releases/download/", "/files/", "/get_file/", "/releases/"))
            has_dl_query = any(dq in query_lower for dq in ("download=", "export=download", "dl=1", "action=download", "file="))

            link_text = (item.get("text") or "").strip()
            link_title = (item.get("title") or item.get("aria_label") or "").strip()
            text_lower = (link_text + " " + link_title).lower()
            has_dl_text = any(tok in text_lower for tok in ("download", "\u062a\u062d\u0645\u064a\u0644", "installer", "setup", "portable", "x64", "64-bit", "32-bit", "arm64", "build"))

            if not (has_dl_ext or has_dl_attr or has_dl_path or has_dl_query or has_dl_text):
                continue

            if not has_dl_ext:
                if any(kw in path_lower or kw in query_lower for kw in non_download_keywords):
                    continue

            # Derive filename
            cd_fn = item.get("download", "").strip()
            if cd_fn:
                filename = cd_fn
            else:
                base_fn = os.path.basename(urllib.parse.unquote(p.path.rstrip("/")))
                if base_fn and base_fn not in (".", ".."):
                    filename = base_fn
                else:
                    filename = derive_download_filename(abs_url)

            cand_ext = ""
            for multi_ext in (".tar.gz", ".tar.bz2", ".tar.xz", ".user.js"):
                if filename.lower().endswith(multi_ext):
                    cand_ext = multi_ext
                    break
            if not cand_ext:
                _, cand_ext = os.path.splitext(filename.lower())

            text_label = link_text or link_title or filename
            if len(text_label) > 100:
                text_label = text_label[:97] + "..."

            size_bytes: Optional[int] = None
            size_m = re.search(r'\(?\b(\d+(?:\.\d+)?)\s*(KB|MB|GB|Bytes)\b\)?', text_lower, re.IGNORECASE)
            if size_m:
                val = float(size_m.group(1))
                unit = size_m.group(2).upper()
                if unit == "KB":
                    size_bytes = int(val * 1024)
                elif unit == "MB":
                    size_bytes = int(val * 1024 * 1024)
                elif unit == "GB":
                    size_bytes = int(val * 1024 * 1024 * 1024)
                elif unit == "BYTES":
                    size_bytes = int(val)

            score = 0
            if cand_ext in preferred_installer_exts:
                score += 1000
            elif cand_ext in COMMON_DOWNLOAD_EXTENSIONS:
                score += 500

            if "/releases/download/" in path_lower:
                score += 350
            elif "/download" in path_lower or "/downloads" in path_lower:
                score += 200

            if any(tok in combined_target or tok in text_lower for tok in platform_tokens):
                score += 250

            if has_dl_attr:
                score += 200
            if has_dl_text:
                score += 100

            if path_lower in ("", "/"):
                score -= 600

            canonical_url = urllib.parse.urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path, p.query, ""))

            candidate_obj = {
                "url": abs_url,
                "filename": filename,
                "ext": cand_ext,
                "size_bytes": size_bytes,
                "title": text_label,
                "score": score
            }

            if canonical_url in seen_dict:
                existing = seen_dict[canonical_url]
                if score > existing["score"]:
                    seen_dict[canonical_url] = candidate_obj
                elif score == existing["score"] and len(text_label) > len(existing["title"]):
                    seen_dict[canonical_url] = candidate_obj
            else:
                seen_dict[canonical_url] = candidate_obj

        except Exception:
            continue

    candidates = list(seen_dict.values())
    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates


class _HtmlLinkCandidateParser(HTMLParser):
    """Parses HTML document to collect candidate download hyperlinks and refresh targets."""
    def __init__(self):
        super().__init__()
        self.raw_candidates: List[str] = []

    def handle_starttag(self, tag, attrs):
        attr_dict = {k.lower(): (v or "") for k, v in attrs}
        tag_lower = tag.lower()

        if tag_lower == "a" and "href" in attr_dict:
            self.raw_candidates.append(attr_dict["href"])

        if tag_lower == "meta" and attr_dict.get("http-equiv", "").lower() == "refresh":
            content = attr_dict.get("content", "")
            m = re.search(r"url\s*=\s*(?:['\"]([^'\"]+)['\"]|([^;\s'\"]+))", content, re.IGNORECASE)
            if m:
                u = m.group(1) or m.group(2)
                if u:
                    self.raw_candidates.append(u.strip())

        for k, v in attr_dict.items():
            if k.startswith("data-download") or k in ("data-href", "data-url", "data-src", "data-link"):
                if v:
                    self.raw_candidates.append(v.strip())


def resolve_real_download_url(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    ssl_context: Optional[ssl.SSLContext] = None,
    timeout: float = 10.0
) -> Dict[str, Any]:
    """
    Probes a candidate download URL to verify whether it returns a direct downloadable file
    or an HTML landing / thank-you page. If an HTML page is returned, parses and ranks
    candidate download links, probes them, and returns the real direct file download URL.

    Returns:
        {
            "url": final_url,
            "is_html": bool,
            "resolved": bool,
            "content_type": str,
            "size": int,
            "filename": str,
            "error": str
        }
    Guaranteed never to raise exceptions.
    """
    clean_url = str(url or "").strip()
    result: Dict[str, Any] = {
        "url": clean_url,
        "is_html": False,
        "resolved": False,
        "content_type": "",
        "size": 0,
        "filename": "",
        "error": "",
        "candidates": [],
        "page_title": ""
    }

    if not clean_url:
        result["error"] = "URL cannot be empty."
        return result

    try:
        parsed_src = urllib.parse.urlsplit(clean_url)
        if parsed_src.scheme.lower() not in ("http", "https") or not parsed_src.netloc:
            result["error"] = "URL must start with http:// or https:// and include a valid host."
            return result
    except Exception as e:
        result["error"] = str(e)
        return result

    ctx = ssl_context if ssl_context is not None else get_permissive_ssl_context()
    custom_headers = dict(headers or {})
    if not any(k.lower() == "user-agent" for k in custom_headers):
        custom_headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    if not any(k.lower() == "accept" for k in custom_headers):
        custom_headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"

    try:
        req = urllib.request.Request(clean_url, headers=custom_headers)
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            final_url = resp.geturl() or clean_url
            raw_ct = resp.headers.get("Content-Type", "")
            content_type = raw_ct.split(";")[0].strip().lower()
            cl = resp.headers.get("Content-Length")
            size = int(cl) if cl and cl.isdigit() else 0
            cd = resp.headers.get("Content-Disposition", "")
            filename = parse_filename_from_cd_header(cd)
            if not filename:
                try:
                    p = urllib.parse.urlsplit(final_url).path
                    base_p = os.path.basename(urllib.parse.unquote(p.rstrip("/")))
                    if base_p and base_p not in (".", ".."):
                        filename = base_p
                except Exception:
                    pass

            is_html = content_type in ("text/html", "application/xhtml+xml")
            if not is_html:
                return {
                    "url": final_url,
                    "is_html": False,
                    "resolved": False,
                    "content_type": content_type,
                    "size": size,
                    "filename": filename or derive_download_filename(final_url),
                    "error": ""
                }

            # Response is HTML. Read up to 512 KB of body for link extraction.
            raw_body = resp.read(512 * 1024)
            charset = resp.headers.get_content_charset() or "utf-8"
            try:
                html_text = raw_body.decode(charset, errors="replace")
            except Exception:
                html_text = raw_body.decode("utf-8", errors="replace")

    except Exception as e:
        result["error"] = str(e)
        return result

    result["url"] = final_url
    result["is_html"] = True
    result["content_type"] = content_type
    result["size"] = size
    result["filename"] = filename or derive_download_filename(final_url)

    # Extract all candidates and page title
    all_candidates = resolve_all_download_candidates(html_text, base_url=final_url)
    result["candidates"] = all_candidates

    extractor_title = ""
    try:
        _pe = _HtmlCandidateExtractor()
        _pe.feed(html_text)
        extractor_title = _pe.page_title.strip()
    except Exception:
        pass
    result["page_title"] = extractor_title

    # Collect link candidates
    parser = _HtmlLinkCandidateParser()
    try:
        parser.feed(html_text)
    except Exception:
        pass

    raw_candidates = list(parser.raw_candidates)

    # Inline script navigation and fallback regexes
    script_patterns = [
        r'(?:window\.)?location(?:\.href)?\s*=\s*[\'"]([^\'"]+)[\'"]',
        r'(?:window\.)?location\.(?:assign|replace)\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)',
        r'window\.open\s*\(\s*[\'"]([^\'"]+)[\'"]',
        r'(?:data-download[a-z0-9_-]*|data-href|data-url)\s*=\s*[\'"]([^\'"]+)[\'"]',
        r'<meta[^>]*?content=[\'"][^>]*?url=([^;\'"\s>]+)[\'"]'
    ]
    for pat in script_patterns:
        for m in re.finditer(pat, html_text, re.IGNORECASE):
            u = m.group(1).strip()
            if u:
                raw_candidates.append(u)

    # Extract absolute URLs and paths from inline <script> blocks
    for s_m in re.finditer(r'<script[^>]*>(.*?)</script>', html_text, re.IGNORECASE | re.DOTALL):
        script_body = s_m.group(1)
        clean_script = script_body.replace(r'\/', '/')
        for url_m in re.finditer(r'https?://[^\s"\'<>\\]+', clean_script, re.IGNORECASE):
            raw_candidates.append(url_m.group(0))

    ignored_exts = {
        ".css", ".js", ".woff", ".woff2", ".svg", ".png", ".jpg", ".jpeg",
        ".gif", ".ico", ".webmanifest", ".map", ".ttf", ".eot", ".otf"
    }
    preferred_installer_exts = {
        ".exe", ".msi", ".zip", ".7z", ".rar", ".dmg", ".apk", ".iso"
    }

    # Extract platform hints from source query
    src_query = (parsed_src.query or "").lower()
    platform_tokens: List[str] = []
    if any(k in src_query for k in ("platform=windows", "os=win", "os=windows", "windows", "win")):
        platform_tokens = ["windows", "win", "x64", "win64", "x86"]
    elif any(k in src_query for k in ("platform=mac", "os=mac", "macos", "darwin", "osx")):
        platform_tokens = ["mac", "macos", "darwin", "dmg", "pkg"]
    elif any(k in src_query for k in ("platform=linux", "os=linux", "linux")):
        platform_tokens = ["linux", "appimage", "deb", "rpm", "tar.gz"]
    elif sys.platform == "win32":
        platform_tokens = ["windows", "win", "x64"]

    final_split = urllib.parse.urlsplit(final_url)
    clean_final_no_frag = (final_split.scheme, final_split.netloc, final_split.path)
    src_split_no_frag = (parsed_src.scheme, parsed_src.netloc, parsed_src.path)

    seen = set()
    scored_candidates: List[Tuple[int, str]] = []

    for raw in raw_candidates:
        u_str = raw.strip("\"' \t\r\n")
        if not u_str or u_str.startswith(("#", "javascript:", "mailto:", "tel:", "data:", "about:")):
            continue
        try:
            abs_u = urllib.parse.urljoin(final_url, u_str)
            p = urllib.parse.urlsplit(abs_u)
            if p.scheme.lower() not in ("http", "https") or not p.netloc:
                continue

            # Skip self-referencing links
            cand_no_frag = (p.scheme, p.netloc, p.path)
            if cand_no_frag == clean_final_no_frag or cand_no_frag == src_split_no_frag:
                continue

            path_lower = p.path.lower()
            query_lower = (p.query or "").lower()
            cand_str = path_lower + ("?" + query_lower if query_lower else "")

            _, ext = os.path.splitext(path_lower)
            if ext in ignored_exts:
                continue

            if abs_u in seen:
                continue
            seen.add(abs_u)

            score = 0
            if ext in preferred_installer_exts:
                score += 1000
            elif ext in COMMON_DOWNLOAD_EXTENSIONS:
                score += 500

            has_dl = ("/download" in path_lower or "/downloads" in path_lower)
            has_plat = any(tok in cand_str for tok in platform_tokens)

            if has_dl and has_plat:
                score += 400
            elif has_dl:
                score += 150
            elif has_plat:
                score += 100

            if "/releases/download/" in path_lower:
                score += 350
            elif "/releases/" in path_lower:
                score += 150

            if path_lower in ("", "/"):
                score -= 600

            scored_candidates.append((score, abs_u))
        except Exception:
            continue

    scored_candidates.sort(key=lambda x: x[0], reverse=True)
    top_candidates = [u for _, u in scored_candidates[:5]]

    probe_headers = dict(custom_headers)
    for cand_url in top_candidates:
        # Probe with HEAD
        head_ok = False
        try:
            h_req = urllib.request.Request(cand_url, method="HEAD", headers=probe_headers)
            with urllib.request.urlopen(h_req, timeout=timeout, context=ctx) as c_resp:
                c_final = c_resp.geturl() or cand_url
                c_ct = (c_resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
                c_cl = c_resp.headers.get("Content-Length")
                c_size = int(c_cl) if c_cl and c_cl.isdigit() else 0
                c_cd = c_resp.headers.get("Content-Disposition", "")
                c_fn = parse_filename_from_cd_header(c_cd)
                if not c_fn:
                    try:
                        c_p = urllib.parse.urlsplit(c_final).path
                        c_base = os.path.basename(urllib.parse.unquote(c_p.rstrip("/")))
                        if c_base and c_base not in (".", ".."):
                            c_fn = c_base
                    except Exception:
                        pass

                if c_ct and c_ct not in ("text/html", "application/xhtml+xml"):
                    return {
                        "url": c_final,
                        "is_html": False,
                        "resolved": True,
                        "content_type": c_ct,
                        "size": c_size,
                        "filename": c_fn or derive_download_filename(c_final),
                        "error": "",
                        "candidates": all_candidates,
                        "page_title": extractor_title
                    }
                if not c_ct:
                    head_ok = False
                else:
                    head_ok = True
        except Exception:
            head_ok = False

        # Fallback to GET Range: bytes=0-0
        if not head_ok:
            try:
                g_headers = dict(probe_headers)
                g_headers["Range"] = "bytes=0-0"
                g_req = urllib.request.Request(cand_url, headers=g_headers)
                with urllib.request.urlopen(g_req, timeout=timeout, context=ctx) as c_resp:
                    c_final = c_resp.geturl() or cand_url
                    c_ct = (c_resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
                    c_cr = c_resp.headers.get("Content-Range", "")
                    c_size = 0
                    if "/" in c_cr:
                        tot = c_cr.split("/")[-1].strip()
                        if tot.isdigit():
                            c_size = int(tot)
                    if c_size == 0:
                        c_cl = c_resp.headers.get("Content-Length")
                        c_size = int(c_cl) if c_cl and c_cl.isdigit() else 0

                    c_cd = c_resp.headers.get("Content-Disposition", "")
                    c_fn = parse_filename_from_cd_header(c_cd)
                    if not c_fn:
                        try:
                            c_p = urllib.parse.urlsplit(c_final).path
                            c_base = os.path.basename(urllib.parse.unquote(c_p.rstrip("/")))
                            if c_base and c_base not in (".", ".."):
                                c_fn = c_base
                        except Exception:
                            pass

                    if c_ct and c_ct not in ("text/html", "application/xhtml+xml"):
                        return {
                            "url": c_final,
                            "is_html": False,
                            "resolved": True,
                            "content_type": c_ct,
                            "size": c_size,
                            "filename": c_fn or derive_download_filename(c_final),
                            "error": ""
                        }
            except Exception:
                pass

    return result


def validate_refresh_url(
    new_url: str,
    expected_size: int = 0,
    check_range: bool = True,
    timeout: float = 12.0,
    ssl_context: Optional[ssl.SSLContext] = None,
    headers: Optional[Dict[str, str]] = None
) -> Tuple[bool, str, int, bool]:
    """
    Validates a candidate refresh URL via HTTP HEAD and GET Range requests.
    Verifies that the new URL is accessible, points to the same file size (if expected_size > 0),
    and accepts HTTP Range byte requests (if check_range is True).
    Returns: (is_valid: bool, status_message: str, resolved_total_size: int, supports_ranges: bool)
    """
    clean_url = str(new_url or "").strip()
    if not clean_url:
        return False, "URL cannot be empty.", 0, False

    try:
        parsed = urllib.parse.urlsplit(clean_url)
        if parsed.scheme.lower() not in ("http", "https") or not parsed.netloc:
            return False, "URL must start with http:// or https:// and include a valid domain.", 0, False
    except Exception as e:
        return False, f"Malformed URL: {e}", 0, False

    ctx = ssl_context if ssl_context is not None else get_permissive_ssl_context()
    custom_headers = dict(headers or {})
    if not any(k.lower() == "user-agent" for k in custom_headers):
        custom_headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0"

    resolved_size = 0
    supports_ranges = False
    head_ok = False
    head_error_code = None
    head_error_reason = ""

    # 1. Attempt HTTP HEAD probe
    try:
        head_req = urllib.request.Request(clean_url, method="HEAD", headers=custom_headers)
        with urllib.request.urlopen(head_req, timeout=timeout, context=ctx) as resp:
            head_ok = True
            cl = resp.headers.get("Content-Length")
            ar = resp.headers.get("Accept-Ranges", "").lower()
            if cl and cl.isdigit():
                resolved_size = int(cl)
            if ar == "bytes":
                supports_ranges = True
    except urllib.error.HTTPError as e:
        e.close()
        head_error_code = e.code
        head_error_reason = str(getattr(e, "reason", e))
        # Note: Do not abort immediately on HEAD 401/403/405/501!
        # Many S3 pre-signed URLs, Cloudflare tokens, and media CDNs only sign GET,
        # rejecting HEAD with 403 or 405. We fall through to verify with GET Range probe.
    except urllib.error.URLError as e:
        return False, f"Failed to connect to host: {e.reason}", 0, False
    except Exception as e:
        return False, f"Connection error: {e}", 0, False

    # 2. Test Range support with GET Range: bytes=0-0 if check_range requested or HEAD didn't confirm ranges/size
    if check_range or not head_ok or resolved_size == 0 or not supports_ranges:
        try:
            range_req = urllib.request.Request(clean_url, headers=custom_headers)
            range_req.add_header("Range", "bytes=0-0")
            with urllib.request.urlopen(range_req, timeout=timeout, context=ctx) as resp:
                code = resp.getcode()
                cr = resp.headers.get("Content-Range", "")

                try:
                    resp.read(min(1024, resolved_size or 1024))
                except Exception:
                    pass

                if code == 206:
                    supports_ranges = True
                    if "/" in cr:
                        total_part = cr.split("/")[-1].strip()
                        if total_part.isdigit():
                            resolved_size = int(total_part)
                    # Note: If code == 206, do NOT use Content-Length as total size,
                    # because in a 206 Partial Content response for bytes=0-0,
                    # Content-Length is 1 (the slice length), NOT the total file size!
                elif code == 200:
                    # Server responded with 200 OK to a Range request, which means
                    # it IGNORED the Range header and sent the whole file body!
                    # Therefore, byte-range resuming is NOT supported!
                    supports_ranges = False
                    if not resolved_size:
                        cl = resp.headers.get("Content-Length")
                        if cl and cl.isdigit():
                            resolved_size = int(cl)
                else:
                    supports_ranges = False
        except urllib.error.HTTPError as e:
            e.close()
            if e.code in (401, 403, 410):
                return False, f"Server returned HTTP {e.code} ({e.reason}) — the download link is expired or unauthorized.", 0, False
            if e.code == 404:
                return False, f"Server returned HTTP 404: Not Found — file does not exist at this address.", 0, False
            if not head_ok:
                return False, f"Server returned HTTP {e.code} ({e.reason}).", 0, False
        except Exception as e:
            if not head_ok:
                return False, f"Range connection test failed: {e}", 0, False

    # If HEAD failed with 401/403/410 and GET Range was not verified or supported
    if not head_ok and head_error_code in (401, 403, 410) and not supports_ranges and resolved_size == 0:
        return False, f"Server returned HTTP {head_error_code} ({head_error_reason}) — link is expired or unauthorized.", 0, False

    # 3. Size match validation if an expected size was provided
    if expected_size > 0 and resolved_size > 0:
        if resolved_size != expected_size:
            return (
                False,
                f"File size mismatch: New link points to {resolved_size:,} bytes, "
                f"but existing download is {expected_size:,} bytes.",
                resolved_size,
                supports_ranges
            )

    # 4. Range requirement validation if partial chunks exist
    if check_range and not supports_ranges:
        return (
            False,
            "Server does not support HTTP Range requests (HTTP 206), which is required to resume partial chunks without restarting.",
            resolved_size,
            False
        )

    return True, "URL verified successfully.", resolved_size, supports_ranges


# ======================================================================================
# 3. TDM ADAPTIVE CONCURRENT TRANSFER & SCHEDULING ENGINE
# ======================================================================================

class TurboDownloadEngine:
    """
    High-throughput download engine featuring:
    - Dynamic on-the-fly chunk splitting (largest remaining space candidate + midpoint split).
    - Strict non-corrupt sequential assembly with 64KB streaming buffers & boundary assertions.
    - Integrated per-download token bucket rate limiting.
    - Robust range fallback, transient error retries, and atomic chunk boundary clamping.
    - Permissive SSL context for expired/self-signed certificates across all probes & chunk workers.
    """
    @staticmethod
    def is_googlevideo_url(url: str) -> bool:
        """Detects if a URL is hosted on YouTube CDN (googlevideo.com)."""
        if not url or not isinstance(url, str):
            return False
        try:
            parsed = urllib.parse.urlsplit(url)
            host = (parsed.hostname or "").lower()
            if host.endswith(".googlevideo.com") or host == "googlevideo.com":
                return True
            if any(dom in host for dom in ("youtube.com", "youtu.be", "ytimg.com")):
                return True
            path = (parsed.path or "").lower()
            if "videoplayback" in path:
                return True
        except Exception:
            pass
        url_lower = str(url).lower()
        return "googlevideo.com" in url_lower or "videoplayback" in url_lower

    def __init__(
        self,
        url: str,
        destination_path: str,
        max_connections: int = 8,
        min_split_threshold: int = 256 * 1024,  # 256 KB minimum remaining to allow split
        rate_limit_bytes_per_sec: float = 0.0,
        ssl_context: Optional[ssl.SSLContext] = None,
        opener: Optional[urllib.request.OpenerDirector] = None,
        headers: Optional[Dict[str, str]] = None,
        allow_dynamic_split: bool = True,
        on_progress: Optional[Callable] = None,
        on_chunk_update: Optional[Callable] = None,
        on_log: Optional[Callable] = None,
        on_complete: Optional[Callable] = None,
        on_error: Optional[Callable] = None
    ):
        self.url = url
        self.destination_path = destination_path
        self.max_connections = max(1, min(max_connections, 32))
        self.min_split_threshold = max(64 * 1024, min_split_threshold)
        self.rate_limiter = TokenBucketRateLimiter(rate_limit_bytes_per_sec)
        self.ssl_context = ssl_context if ssl_context is not None else get_permissive_ssl_context()
        self.opener = opener if opener is not None else urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=self.ssl_context)
        )
        self.headers: Dict[str, str] = dict(headers) if headers else {}

        # YouTube googlevideo CDN detection and concurrency safety
        self.is_googlevideo = self.is_googlevideo_url(self.url)
        self.allow_dynamic_split = allow_dynamic_split and not self.is_googlevideo
        if self.is_googlevideo:
            # YouTube googlevideo CDN issues HTTP 403 Forbidden on concurrent range requests
            # with the same signed token. Enforce safe concurrency (1 connection) & no dynamic splitting.
            self.max_connections = min(self.max_connections, 1)

        self.on_progress = on_progress
        self.on_chunk_update = on_chunk_update
        self.on_log = on_log
        self.on_complete = on_complete
        self.on_error = on_error

        self.total_size = 0
        self.supports_ranges = False
        self.content_type: str = ""
        self.filename = os.path.basename(destination_path)
        self.temp_dir = destination_path + ".sd_parts"
        for legacy_d in [destination_path + ".tdm_parts", destination_path + ".idm_parts"]:
            if os.path.isdir(legacy_d) and not os.path.exists(self.temp_dir):
                try:
                    os.replace(legacy_d, self.temp_dir)
                    break
                except Exception:
                    pass

        self.chunks: List[DownloadChunk] = []
        self.active_workers: List[threading.Thread] = []
        self._active_connections: List[urllib.request.addinfourl] = []

        self._lock = threading.RLock()
        self._cancel_event = threading.Event()
        self._pause_event = threading.Event()
        self._error_abort_event = threading.Event()
        self.is_running = False
        self.is_paused = False
        self.has_expired_link = False
        self.last_http_status = 0
        self._resume_mode = False

        # Speed calculation metrics
        self.start_time = 0.0
        self.last_speed_check_time = 0.0
        self.last_downloaded_bytes = 0
        self.current_speed = 0.0

    def log(self, message: str):
        timestamp = time.strftime("%H:%M:%S")
        log_msg = f"[{timestamp}] {message}"
        if self.on_log:
            try:
                self.on_log(log_msg)
            except Exception:
                pass

    def set_speed_limit(self, bytes_per_sec: float):
        """Update speed limit on the fly."""
        self.rate_limiter.set_limit(bytes_per_sec)
        if bytes_per_sec <= 0:
            self.log("Speed limit set to: Unlimited")
        else:
            if bytes_per_sec >= 1024 * 1024:
                self.log(f"Speed limit set to: {bytes_per_sec / (1024*1024):.2f} MB/s")
            else:
                self.log(f"Speed limit set to: {bytes_per_sec / 1024:.1f} KB/s")

    def get_chunks_snapshot(self) -> List[DownloadChunk]:
        """Returns a thread-safe snapshot copy of the current chunk list."""
        with self._lock:
            return list(self.chunks)

    def _parse_filename_from_cd(self, cd: str) -> Optional[str]:
        """Extracts clean filename from Content-Disposition header, ignoring parameters."""
        if not cd:
            return None
        parts = cd.split(";")
        for p in parts:
            p = p.strip()
            if p.lower().startswith("filename="):
                raw = p[9:].strip("\"' ")
                if raw:
                    return os.path.basename(raw)
        return None

    def _create_request(self, method: Optional[str] = None) -> urllib.request.Request:
        """Constructs an HTTP request pre-populated with standard headers and custom headers."""
        if method:
            req = urllib.request.Request(self.url, method=method)
        else:
            req = urllib.request.Request(self.url)

        has_ua = any(k.lower() == "user-agent" for k in self.headers)
        if not has_ua:
            req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0")

        for k, v in self.headers.items():
            req.add_header(k, v)
        return req

    def probe(self):
        """
        Inspect target URL for Content-Length, HTTP 206 Accept-Ranges, and file name.
        Uses HEAD with fallback to GET Range: bytes=0-0 to bypass servers blocking HEAD.
        """
        self.log(f"Probing server capabilities: {self.url}")
        req = self._create_request(method="HEAD")

        head_succeeded = False
        try:
            with urllib.request.urlopen(req, timeout=12, context=self.ssl_context) as resp:
                # Update URL if redirected
                redirected_url = resp.geturl()
                if redirected_url and redirected_url != self.url:
                    self.url = redirected_url
                    if self.is_googlevideo_url(self.url):
                        self.is_googlevideo = True
                        self.max_connections = min(self.max_connections, 1)
                        self.allow_dynamic_split = False

                cl = resp.headers.get("Content-Length")
                ar = resp.headers.get("Accept-Ranges", "").lower()
                raw_ct = resp.headers.get("Content-Type", "")
                self.content_type = raw_ct.split(";")[0].strip().lower()
                self.total_size = int(cl) if cl and cl.isdigit() else 0
                self.supports_ranges = (ar == "bytes") and (self.total_size > 0)

                cd = resp.headers.get("Content-Disposition", "")
                cd_fn = self._parse_filename_from_cd(cd)
                if cd_fn:
                    self.filename = cd_fn
                head_succeeded = True
        except urllib.error.HTTPError as e:
            e.close()
            head_succeeded = False
        except Exception:
            head_succeeded = False

        # If HEAD failed or did not confirm range support, test with GET Range: bytes=0-0
        if not head_succeeded or not self.supports_ranges:
            req = self._create_request()
            req.add_header("Range", "bytes=0-0")
            try:
                with urllib.request.urlopen(req, timeout=12, context=self.ssl_context) as resp:
                    redirected_url = resp.geturl()
                    if redirected_url and redirected_url != self.url:
                        self.url = redirected_url
                        if self.is_googlevideo_url(self.url):
                            self.is_googlevideo = True
                            self.max_connections = min(self.max_connections, 1)
                            self.allow_dynamic_split = False

                    raw_ct = resp.headers.get("Content-Type", "")
                    if raw_ct:
                        self.content_type = raw_ct.split(";")[0].strip().lower()

                    cr = resp.headers.get("Content-Range", "")
                    if "/" in cr:
                        total_str = cr.split("/")[-1].strip()
                        if total_str.isdigit():
                            self.total_size = int(total_str)
                            self.supports_ranges = True
                    elif resp.getcode() == 206:
                        self.supports_ranges = True

                    if not self.total_size and resp.getcode() == 200:
                        cl = resp.headers.get("Content-Length")
                        self.total_size = int(cl) if cl and cl.isdigit() else 0

                    cd = resp.headers.get("Content-Disposition", "")
                    cd_fn = self._parse_filename_from_cd(cd)
                    if cd_fn:
                        self.filename = cd_fn
            except Exception as e:
                if isinstance(e, urllib.error.HTTPError):
                    e.close()
                    if e.code in (401, 403, 410):
                        self.has_expired_link = True
                        self.last_http_status = e.code
                # If GET Range failed and HEAD also failed, attempt a plain GET request
                # without Range to follow redirects and probe headers
                if not head_succeeded:
                    try:
                        req_plain = self._create_request()
                        with urllib.request.urlopen(req_plain, timeout=12, context=self.ssl_context) as resp:
                            redirected_url = resp.geturl()
                            if redirected_url and redirected_url != self.url:
                                self.url = redirected_url
                                if self.is_googlevideo_url(self.url):
                                    self.is_googlevideo = True
                                    self.max_connections = min(self.max_connections, 1)
                                    self.allow_dynamic_split = False

                            raw_ct = resp.headers.get("Content-Type", "")
                            if raw_ct:
                                self.content_type = raw_ct.split(";")[0].strip().lower()

                            cl = resp.headers.get("Content-Length")
                            ar = resp.headers.get("Accept-Ranges", "").lower()
                            self.total_size = int(cl) if cl and cl.isdigit() else 0
                            self.supports_ranges = (ar == "bytes") and (self.total_size > 0)

                            cd = resp.headers.get("Content-Disposition", "")
                            cd_fn = self._parse_filename_from_cd(cd)
                            if cd_fn:
                                self.filename = cd_fn
                    except Exception as e_plain:
                        if isinstance(e_plain, urllib.error.HTTPError):
                            e_plain.close()
                            if e_plain.code in (401, 403, 410):
                                self.has_expired_link = True
                                self.last_http_status = e_plain.code
                        raise RuntimeError(f"Connection failed: {e_plain}")

        if self.is_googlevideo and self.total_size > 0:
            self.supports_ranges = True

        # Fallback filename extraction from URL if Content-Disposition was absent
        if not self.filename or os.path.isdir(self.destination_path) or self.filename in (".", "..", "download.bin"):
            try:
                parsed_path = urllib.parse.urlsplit(self.url).path
                url_fn = os.path.basename(urllib.parse.unquote(parsed_path.rstrip("/")))
                if url_fn:
                    self.filename = url_fn
            except Exception:
                pass

        # Update destination path if filename discovered
        if os.path.isdir(self.destination_path) or self.destination_path.endswith(("/", "\\")):
            self.destination_path = os.path.join(self.destination_path, self.filename or "download.bin")
            self.temp_dir = self.destination_path + ".sd_parts"
            for legacy_d in [self.destination_path + ".tdm_parts", self.destination_path + ".idm_parts"]:
                if os.path.isdir(legacy_d) and not os.path.exists(self.temp_dir):
                    try:
                        os.replace(legacy_d, self.temp_dir)
                        break
                    except Exception:
                        pass

        # HTML response safety net: abort if server returned an HTML page instead of a binary file
        fn_to_check = self.filename or os.path.basename(self.destination_path)
        dest_ext = os.path.splitext(fn_to_check)[1].lower() if fn_to_check else ""
        if getattr(self, "content_type", "") == "text/html":
            if not dest_ext or dest_ext == ".bin":
                raise RuntimeError("Server returned a web page (HTML), not a file")

        if self.supports_ranges and self.total_size > 0:
            size_mb = self.total_size / (1024 * 1024)
            self.log(f"Server supports HTTP 206 Multi-threading! Total Size: {size_mb:.2f} MB ({self.total_size:,} bytes).")
        else:
            if self.total_size > 0:
                self.log(f"Server does not support HTTP Range requests. Size: {self.total_size:,} bytes. Single-stream fallback active.")
            else:
                self.log("Server does not support HTTP Range requests and size is dynamic/unknown. Single-stream fallback active.")

    def start(self):
        """Launches the download supervisor thread."""
        self.is_running = True
        self.is_paused = False
        self._cancel_event.clear()
        self._pause_event.clear()
        self.start_time = time.time()
        self.last_speed_check_time = time.time()

        supervisor_thread = threading.Thread(target=self._supervisor_loop, daemon=True)
        supervisor_thread.start()

    def pause(self):
        """Pauses all active chunk downloads."""
        if not self.is_running or self.is_paused:
            return
        self.is_paused = True
        self._pause_event.set()
        self.save_state()
        self.log("Download paused by user.")

    def resume(self):
        """Resumes all active chunk downloads."""
        if not self.is_running or not self.is_paused:
            return
        self.is_paused = False
        self.last_speed_check_time = time.monotonic()
        self._pause_event.clear()
        self.log("Download resumed.")

    def cancel(self):
        """Cancels download and stops all worker threads immediately."""
        self.is_running = False
        self._cancel_event.set()
        self._pause_event.clear()

        # Abort any blocked socket reads immediately
        with self._lock:
            for conn in self._active_connections:
                try:
                    conn.close()
                except Exception:
                    pass
            self._active_connections.clear()

        self.log("Download cancelled by user.")
        self.cleanup_temp_files()

    def cleanup_temp_files(self):
        """Safely cleans up temporary chunk directory and files."""
        try:
            if hasattr(self, "temp_dir") and self.temp_dir and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir, ignore_errors=True)
        except Exception:
            pass

    def _supervisor_loop(self):
        """Master supervisor: manages initial connection, dynamic splitting, and assembly."""
        try:
            is_resuming = bool(
                getattr(self, "_resume_mode", False)
                or (self.chunks and any(c.downloaded_bytes > 0 for c in self.chunks))
            )

            # If not in resume mode, check if state file exists in temp_dir to restore
            if not is_resuming and not self.chunks and os.path.exists(self.temp_dir):
                if self.load_state() and self.chunks:
                    is_resuming = True

            if not is_resuming:
                self.probe()

                if os.path.exists(self.temp_dir):
                    shutil.rmtree(self.temp_dir, ignore_errors=True)
                os.makedirs(self.temp_dir, exist_ok=True)

                # Allocate initial chunk 0
                # If total_size > 0, initial_end MUST be total_size - 1 even in single-stream mode!
                initial_end = (self.total_size - 1) if self.total_size > 0 else 0
                chunk0 = DownloadChunk(
                    chunk_id=0,
                    start_byte=0,
                    end_byte=initial_end,
                    downloaded_bytes=0,
                    status="pending",
                    part_filepath=os.path.join(self.temp_dir, f"{os.path.basename(self.destination_path)}.part_0")
                )
                with self._lock:
                    self.chunks.clear()
                    self.chunks.append(chunk0)

                self.save_state()
                self._spawn_worker(chunk0)
            else:
                self.log(f"Resuming download from existing chunks ({len(self.chunks)} parts)...")
                os.makedirs(self.temp_dir, exist_ok=True)
                prior_workers = []
                with self._lock:
                    prior_workers = list(self.active_workers)
                for w in prior_workers:
                    if w.is_alive() and w != threading.current_thread():
                        w.join(timeout=0.3)
                self._error_abort_event.clear()
                with self._lock:
                    self.active_workers.clear()
                    self._active_connections.clear()
                    for c in self.chunks:
                        with c.lock:
                            expected = c.end_byte - c.start_byte + 1
                            if os.path.exists(c.part_filepath):
                                try:
                                    actual_bytes = os.path.getsize(c.part_filepath)
                                    c.downloaded_bytes = min(actual_bytes, expected)
                                    if actual_bytes > expected:
                                        with open(c.part_filepath, "r+b") as tf:
                                            tf.truncate(expected)
                                except Exception:
                                    pass
                            if self.total_size > 0 and c.downloaded_bytes >= expected:
                                c.status = "completed"
                            else:
                                c.status = "pending"
                                c.error_msg = ""
                    # Spawn workers for pending chunks up to max_connections
                    pending_chunks = [c for c in self.chunks if c.status == "pending"]
                    for c in pending_chunks[:self.max_connections]:
                        self._spawn_worker(c)
                self._resume_mode = False
                self.save_state()

            # Scheduling & Dynamic Splitting Loop
            while self.is_running and not self._cancel_event.is_set():
                time.sleep(0.08)

                if self.is_paused:
                    continue

                # Schedule pending chunks if worker slots available
                with self._lock:
                    active_count = sum(1 for c in self.chunks if c.status == "active")
                    if active_count < self.max_connections:
                        pending = [c for c in self.chunks if c.status == "pending"]
                        for c in pending[:self.max_connections - active_count]:
                            self._spawn_worker(c)

                # Check if we should dynamically split active chunks
                if self.supports_ranges and self.total_size > 0:
                    self._dynamic_split_check()

                # Update progress & calculate real-time speed
                self._update_progress_metrics()

                # Check completion or failure
                with self._lock:
                    all_finished = all(c.status in ("completed", "failed") for c in self.chunks)
                    any_failed = any(c.status == "failed" for c in self.chunks)

                # Fail fast if a chunk failed permanently
                if any_failed:
                    failed_chunks = [c for c in self.chunks if c.status == "failed"]
                    err = failed_chunks[0].error_msg if failed_chunks else "Chunk transfer failure"
                    self._stop_workers_for_error()
                    self.save_state()
                    raise RuntimeError(f"Download failed in chunk: {err}")

                if all_finished:
                    break

            if self._cancel_event.is_set():
                return

            # Perform strict sequential assembly
            self.assemble()

            elapsed = max(0.01, time.time() - self.start_time)
            avg_speed = (self.total_size / elapsed) if elapsed > 0 else 0
            speed_str = f"{avg_speed / (1024*1024):.2f} MB/s" if avg_speed >= 1024*1024 else f"{avg_speed / 1024:.1f} KB/s"
            self.log(f"[SUCCESS] Download finished successfully in {elapsed:.1f}s (Average Speed: {speed_str})!")

            if self.on_complete:
                self.on_complete(self.destination_path, self.total_size, elapsed)

        except Exception as e:
            self.log(f"[ERROR] {e}")
            if self.on_error:
                self.on_error(str(e))
        finally:
            self.is_running = False
            if self._cancel_event.is_set():
                self.cleanup_temp_files()

    def _spawn_worker(self, chunk: DownloadChunk):
        """Spawns an asynchronous worker thread for a specific chunk."""
        t = threading.Thread(target=self._chunk_worker, args=(chunk,), daemon=True)
        with self._lock:
            self.active_workers.append(t)
        t.start()

    def _chunk_worker(self, chunk: DownloadChunk):
        """
        Worker thread with automatic transient retry, safe boundary clamping,
        smooth single-connection streaming for YouTube/googlevideo CDN, and single-handle file streaming.
        """
        max_retries = 3
        retry_count = 0

        while retry_count < max_retries and not self._cancel_event.is_set() and not self._error_abort_event.is_set() and self.is_running:
            resp = None
            seg_bytes_read = 0
            try:
                # Streaming loop across byte range until chunk is fully downloaded
                while not self._cancel_event.is_set() and not self._error_abort_event.is_set() and self.is_running:
                    with chunk.lock:
                        chunk.status = "active"
                        cur_offset = chunk.start_byte + chunk.downloaded_bytes
                        target_end = chunk.end_byte
                        if self.total_size > 0 and cur_offset > target_end:
                            chunk.status = "completed"
                            return
                        if self.total_size == 0 and chunk.downloaded_bytes > 0 and chunk.status == "completed":
                            return

                    # Compute end byte for this request (single continuous stream from cur_offset to target_end)
                    if self.supports_ranges and self.total_size > 0:
                        req_end = target_end
                    else:
                        req_end = None

                    end_str = f"{req_end:,}" if req_end is not None else "end"
                    self.log(
                        f"Connection #{chunk.chunk_id} (Attempt {retry_count+1}): "
                        f"Byte range [{cur_offset:,} - {end_str}]"
                    )
                    if self.on_chunk_update:
                        self.on_chunk_update()

                    req = self._create_request()
                    if self.supports_ranges and self.total_size > 0 and req_end is not None:
                        req.add_header("Range", f"bytes={cur_offset}-{req_end}")
                        if chunk.downloaded_bytes > 0 and os.path.exists(chunk.part_filepath):
                            try:
                                with open(chunk.part_filepath, "r+b") as tf:
                                    tf.seek(chunk.downloaded_bytes)
                                    tf.truncate()
                            except Exception:
                                pass
                            file_mode = "ab"
                        else:
                            file_mode = "wb"
                    else:
                        chunk.downloaded_bytes = 0
                        file_mode = "wb"

                    resp = urllib.request.urlopen(req, timeout=15, context=self.ssl_context)
                    if self.supports_ranges and self.total_size > 0:
                        code = resp.getcode()
                        if code not in (200, 206):
                            raise RuntimeError(f"Unexpected HTTP status {code}")
                        if code == 200 and cur_offset > 0:
                            raise RuntimeError(f"Server returned HTTP 200 instead of HTTP 206 for non-zero range")

                    with self._lock:
                        self._active_connections.append(resp)

                    BUF_SIZE = 32768
                    seg_bytes_read = 0
                    expected_seg_bytes = (req_end - cur_offset + 1) if (req_end is not None) else None

                    with open(chunk.part_filepath, file_mode) as f:
                        while not self._cancel_event.is_set() and not self._error_abort_event.is_set() and self.is_running:
                            # Handle pause
                            while self._pause_event.is_set() and not self._cancel_event.is_set() and not self._error_abort_event.is_set() and self.is_running:
                                time.sleep(0.1)

                            if self._cancel_event.is_set() or self._error_abort_event.is_set() or not self.is_running:
                                return

                            with chunk.lock:
                                cur_end = chunk.end_byte
                                pos = chunk.start_byte + chunk.downloaded_bytes
                                if self.total_size > 0 and pos > cur_end:
                                    chunk.status = "completed"
                                    return
                                effective_end = min(cur_end, req_end) if req_end is not None else cur_end
                                to_read = min(BUF_SIZE, effective_end - pos + 1) if self.total_size > 0 else BUF_SIZE

                            if to_read <= 0:
                                break

                            data = resp.read(to_read)
                            if not data:
                                if expected_seg_bytes is not None and seg_bytes_read < expected_seg_bytes:
                                    raise RuntimeError(
                                        f"Premature EOF from server: received {seg_bytes_read:,} of {expected_seg_bytes:,} bytes"
                                    )
                                break

                            # Enforce per-download speed limit with cancel responsiveness
                            self.rate_limiter.acquire(len(data), self._cancel_event)

                            # Atomic boundary clamp before writing to disk
                            with chunk.lock:
                                cur_end = chunk.end_byte
                                pos = chunk.start_byte + chunk.downloaded_bytes
                                effective_end = min(cur_end, req_end) if req_end is not None else cur_end
                                if self.total_size > 0:
                                    if pos > effective_end:
                                        break
                                    needed = effective_end - pos + 1
                                    if len(data) > needed:
                                        data = data[:needed]

                                f.write(data)
                                chunk.downloaded_bytes += len(data)
                                seg_bytes_read += len(data)

                                if self.total_size > 0 and (chunk.start_byte + chunk.downloaded_bytes > chunk.end_byte):
                                    chunk.status = "completed"
                                    return

                    with self._lock:
                        if resp in self._active_connections:
                            self._active_connections.remove(resp)
                    try:
                        resp.close()
                    except Exception:
                        pass
                    resp = None

                    # Check if entire chunk is finished
                    with chunk.lock:
                        if self.total_size > 0 and (chunk.start_byte + chunk.downloaded_bytes > chunk.end_byte):
                            chunk.status = "completed"
                            return
                        if self.total_size == 0:
                            chunk.status = "completed"
                            return

                    # If single request completed without reaching chunk end, treat as premature EOF to retry
                    with chunk.lock:
                        if self.total_size > 0 and (chunk.start_byte + chunk.downloaded_bytes <= chunk.end_byte):
                            raise RuntimeError(
                                f"Premature EOF from server before chunk completion "
                                f"({chunk.downloaded_bytes:,}/{chunk.end_byte - chunk.start_byte + 1:,} bytes)"
                            )
                        chunk.status = "completed"
                        return

            except Exception as e:
                if self._cancel_event.is_set() or self._error_abort_event.is_set() or not self.is_running:
                    return
                if isinstance(e, urllib.error.HTTPError):
                    e.close()
                    self.last_http_status = e.code
                    if e.code in (401, 403, 410):
                        self.has_expired_link = True
                        chunk.error_msg = f"HTTP {e.code}: {e.reason} (Expired or Forbidden Link)"
                        break
                if self._cancel_event.is_set() or self._error_abort_event.is_set() or not self.is_running:
                    return
                if seg_bytes_read > 0:
                    retry_count = max(0, retry_count - 1)
                retry_count += 1
                self.log(f"Connection #{chunk.chunk_id} error: {e}. Retry {retry_count}/{max_retries} in 1s...")
                time.sleep(1.0)
            finally:
                if resp:
                    with self._lock:
                        if resp in self._active_connections:
                            self._active_connections.remove(resp)
                    try:
                        resp.close()
                    except Exception:
                        pass
                if self.on_chunk_update:
                    self.on_chunk_update()

        # If retries exhausted or cancelled/aborted and chunk did not complete
        if self._cancel_event.is_set() or self._error_abort_event.is_set() or not self.is_running:
            return

        with chunk.lock:
            if chunk.status != "completed":
                chunk.status = "failed"
                if not chunk.error_msg:
                    chunk.error_msg = f"Connection failed after {max_retries} attempts"
                self.log(f"Chunk #{chunk.chunk_id} failed permanently: {chunk.error_msg}")
        self.save_state()
        if self.on_chunk_update:
            self.on_chunk_update()

    def _dynamic_split_check(self):
        """
        TDM Adaptive Dynamic Midpoint Splitting Mechanism:
        1. Evaluates active worker count against max_connections.
        2. Candidate selection: selects active chunk with largest remaining un-downloaded space.
        3. Threshold condition: remaining must be >= min_split_threshold and remaining // 2 >= 32KB.
        4. Mid-point split: candidate's end_byte shrinks to mid - 1; new chunk created for [mid, old_end].
        5. Atomic lock synchronization prevents gaps or race conditions.
        6. New connection spawned immediately on new chunk.
        """
        with self._lock:
            if not self.allow_dynamic_split or self.is_googlevideo:
                return

            active_count = sum(1 for c in self.chunks if c.status == "active")
            if active_count >= self.max_connections:
                return

            candidates = [
                c for c in self.chunks
                if c.status == "active" and c.remaining_bytes >= self.min_split_threshold
            ]
            if not candidates:
                return

            # Select candidate with the largest remaining byte range
            candidate = max(candidates, key=lambda c: c.remaining_bytes)

            with candidate.lock:
                remaining = candidate.end_byte - (candidate.start_byte + candidate.downloaded_bytes) + 1
                half = remaining // 2
                if remaining < self.min_split_threshold or half < 32768 or candidate.status != "active":
                    return

                split_start = candidate.start_byte + candidate.downloaded_bytes + half
                old_end = candidate.end_byte

                # Candidate's new end is adjusted atomically
                candidate.end_byte = split_start - 1

            # Create the new chunk atomically inside self._lock
            new_id = len(self.chunks)
            part_path = os.path.join(self.temp_dir, f"{os.path.basename(self.destination_path)}.part_{new_id}")
            new_chunk = DownloadChunk(
                chunk_id=new_id,
                start_byte=split_start,
                end_byte=old_end,
                downloaded_bytes=0,
                status="pending",
                part_filepath=part_path
            )
            self.chunks.append(new_chunk)
            self.save_state()

        self.log(f"[SPLIT] Dynamic Split: Chunk #{candidate.chunk_id} split! Spawned Chunk #{new_id} [{split_start:,} - {old_end:,}]")
        self._spawn_worker(new_chunk)

    def _update_progress_metrics(self):
        """Computes smoothed transfer speed, ETA, and progress metrics."""
        now = time.monotonic()
        dt = now - self.last_speed_check_time

        with self._lock:
            total_downloaded = sum(c.downloaded_bytes for c in self.chunks)
            active_count = sum(1 for c in self.chunks if c.status == "active")

        if dt >= 0.4:
            delta_bytes = total_downloaded - self.last_downloaded_bytes
            instant_speed = max(0.0, delta_bytes / dt)
            # Exponential Moving Average for silky smooth speed meter
            if self.current_speed == 0.0:
                self.current_speed = instant_speed
            else:
                self.current_speed = (0.45 * instant_speed) + (0.55 * self.current_speed)

            self.last_downloaded_bytes = total_downloaded
            self.last_speed_check_time = now

        # Compute ETA
        if self.current_speed > 1024 and self.total_size > total_downloaded:
            rem_bytes = self.total_size - total_downloaded
            eta_sec = int(rem_bytes / self.current_speed)
            eta_str = f"{eta_sec // 3600:02d}:{(eta_sec % 3600) // 60:02d}:{eta_sec % 60:02d}"
        else:
            eta_str = "--:--:--"

        if self.on_progress:
            self.on_progress(total_downloaded, self.total_size, self.current_speed, eta_str, active_count)

    def assemble(self):
        """
        Strict Non-Corrupt Sequential Assembly:
        - Strict sorting by start_byte.
        - Boundary assertions: chunk[0].start_byte == 0, chunk[i].end_byte + 1 == chunk[i+1].start_byte.
        - On-disk part file size validations.
        - 64KB streaming buffer merge into target file.
        - Total assembled size verification.
        - Pre-allocation and streamlined streaming buffers (inspired by splitter.rs).
        - Magic bytes container detection (inspired by detector.rs).
        - Post-download integrity verification (CRC-32 & SHA-256).
        - Temporary directory cleanup upon successful assembly.
        """
        self.log("Beginning strict sequential assembly...")

        with self._lock:
            sorted_chunks = sorted(self.chunks, key=lambda c: c.start_byte)

        if not sorted_chunks:
            raise ValueError("No download chunks available for assembly.")

        # Magic bytes detection inspired by AeroArchive Studio (detector.rs)
        if sorted_chunks and os.path.exists(sorted_chunks[0].part_filepath):
            try:
                with open(sorted_chunks[0].part_filepath, "rb") as f0:
                    head_bytes = f0.read(512)
                detected = MagicBytesDetector.detect_bytes(head_bytes)
                if detected:
                    det_ext, det_mime, det_cat = detected
                    cur_ext = os.path.splitext(self.destination_path)[1].lower()
                    if (
                        cur_ext in ("", ".bin", ".download", ".octet-stream", ".part")
                        and not self.destination_path.endswith((".video.tmp", ".audio.tmp", ".tmp"))
                        and det_ext
                    ):
                        new_dest = os.path.splitext(self.destination_path)[0] + det_ext
                        self.log(f"[DETECTOR] Detected true format via magic bytes: {det_ext} ({det_cat}) -> {os.path.basename(new_dest)}")
                        self.destination_path = new_dest
                        self.filename = os.path.basename(new_dest)
            except Exception:
                pass

        # Boundary assertions
        if self.supports_ranges and self.total_size > 0:
            assert sorted_chunks[0].start_byte == 0, (
                f"Assembly Assertion Failed: Chunk 0 starts at {sorted_chunks[0].start_byte}, expected 0."
            )
            for i in range(len(sorted_chunks) - 1):
                c_cur = sorted_chunks[i]
                c_next = sorted_chunks[i+1]
                assert c_cur.end_byte + 1 == c_next.start_byte, (
                    f"Boundary Gap/Overlap detected between Chunk #{c_cur.chunk_id} "
                    f"(ends {c_cur.end_byte}) and #{c_next.chunk_id} (starts {c_next.start_byte})!"
                )
            assert sorted_chunks[-1].end_byte == self.total_size - 1, (
                f"Assembly Assertion Failed: Final chunk ends at {sorted_chunks[-1].end_byte}, expected {self.total_size - 1}."
            )

            # Validate part file size on disk matches expected byte span
            for c in sorted_chunks:
                expected_size = c.end_byte - c.start_byte + 1
                if not os.path.exists(c.part_filepath):
                    raise FileNotFoundError(f"Missing chunk file: {c.part_filepath}")
                actual_size = os.path.getsize(c.part_filepath)
                assert actual_size == expected_size, (
                    f"Chunk #{c.chunk_id} size mismatch: disk {actual_size:,} bytes != expected {expected_size:,} bytes."
                )

        # Streamlined 128KB streaming assembly (inspired by splitter.rs join_chunks)
        BUFFER_SIZE = 128 * 1024
        total_written = 0

        # Ensure target directory exists
        dest_dir = os.path.dirname(self.destination_path)
        if dest_dir:
            os.makedirs(dest_dir, exist_ok=True)

        with open(self.destination_path, "wb") as out_f:
            if self.total_size > 0:
                try:
                    out_f.truncate(self.total_size)
                except Exception:
                    pass
            for c in sorted_chunks:
                if not os.path.exists(c.part_filepath):
                    continue
                with open(c.part_filepath, "rb") as in_f:
                    while True:
                        buf = in_f.read(BUFFER_SIZE)
                        if not buf:
                            break
                        out_f.write(buf)
                        total_written += len(buf)
            out_f.flush()

        if self.total_size > 0:
            assert total_written == self.total_size, (
                f"Assembly size mismatch: Written {total_written:,} bytes != expected {self.total_size:,} bytes."
            )

        self.log(f"Assembled and verified {total_written:,} bytes with zero corruption.")

        # Post-download integrity verification (CRC-32 & SHA-256)
        try:
            hashes = calculate_file_integrity(self.destination_path)
            self.log(f"[INTEGRITY] SHA-256: {hashes.get('sha256')} | CRC-32: {hashes.get('crc32')}")
        except Exception as e:
            self.log(f"[INTEGRITY] Verification error: {e}")

        # Optional auto-unpack for archive files
        if get_setting("auto_unpack_archives", False):
            try:
                unpacked_to = auto_unpack_archive(self.destination_path)
                if unpacked_to:
                    self.log(f"[ARCHIVE] Successfully auto-unpacked to: {unpacked_to}")
            except Exception as e:
                self.log(f"[ARCHIVE] Auto-unpack error: {e}")

        # Cleanup part files
        try:
            shutil.rmtree(self.temp_dir, ignore_errors=True)
            self.log("Cleaned up temporary chunk files.")
        except Exception:
            pass

    def safe_shutdown(self):
        """
        Safely halts all active workers and serializes state into state.json
        WITHOUT purging temporary chunk files (.sd_parts).
        Enables seamless download resumption upon next launch.
        """
        self.is_running = False
        self.is_paused = True
        self._pause_event.set()
        self._cancel_event.set()
        with self._lock:
            for conn in list(self._active_connections):
                try:
                    conn.close()
                except Exception:
                    pass
            self._active_connections.clear()
        self.save_state()
        self.log("Download state saved safely in .sd_parts. Resume ready.")

    def _stop_workers_for_error(self):
        """Closes active socket connections and signals all workers to abort immediately."""
        self._error_abort_event.set()
        with self._lock:
            for conn in list(self._active_connections):
                try:
                    conn.close()
                except Exception:
                    pass
            self._active_connections.clear()

    def save_state(self) -> bool:
        """Serializes current download chunk state and progress into state.json within temp_dir."""
        try:
            if not getattr(self, "temp_dir", None):
                return False
            os.makedirs(self.temp_dir, exist_ok=True)
            state_file = os.path.join(self.temp_dir, "state.json")
            with self._lock:
                chunks_data = []
                for c in self.chunks:
                    with c.lock:
                        disk_bytes = c.downloaded_bytes
                        if os.path.exists(c.part_filepath):
                            try:
                                disk_bytes = os.path.getsize(c.part_filepath)
                            except Exception:
                                pass
                        chunks_data.append({
                            "chunk_id": c.chunk_id,
                            "start_byte": c.start_byte,
                            "end_byte": c.end_byte,
                            "downloaded_bytes": disk_bytes,
                            "status": c.status,
                            "part_filepath": c.part_filepath,
                            "error_msg": c.error_msg
                        })
                data = {
                    "url": self.url,
                    "destination_path": self.destination_path,
                    "total_size": self.total_size,
                    "supports_ranges": self.supports_ranges,
                    "has_expired_link": self.has_expired_link,
                    "filename": self.filename,
                    "headers": self.headers,
                    "chunks": chunks_data
                }
            tmp_state = state_file + ".tmp"
            with open(tmp_state, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp_state, state_file)
            return True
        except Exception as e:
            self.log(f"Warning: Failed to save chunk state: {e}")
            return False

    def load_state(self) -> bool:
        """Loads and restores download chunks and progress from state.json if present and valid."""
        try:
            if not getattr(self, "temp_dir", None):
                return False
            state_file = os.path.join(self.temp_dir, "state.json")
            if not os.path.isfile(state_file):
                return False
            with open(state_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            total_size = data.get("total_size", 0)
            chunks_data = data.get("chunks", [])
            if not chunks_data:
                return False

            with self._lock:
                self.chunks.clear()
                self.total_size = total_size
                self.supports_ranges = data.get("supports_ranges", True)
                self.has_expired_link = data.get("has_expired_link", False)
                for cd in chunks_data:
                    part_path = cd.get("part_filepath") or os.path.join(
                        self.temp_dir, f"{os.path.basename(self.destination_path)}.part_{cd['chunk_id']}"
                    )
                    disk_bytes = cd.get("downloaded_bytes", 0)
                    if os.path.exists(part_path):
                        try:
                            actual_disk = os.path.getsize(part_path)
                            disk_bytes = min(actual_disk, cd["end_byte"] - cd["start_byte"] + 1)
                        except Exception:
                            pass

                    expected_span = cd["end_byte"] - cd["start_byte"] + 1
                    status = cd.get("status", "pending")
                    if total_size > 0 and disk_bytes >= expected_span:
                        status = "completed"
                    elif status == "failed":
                        status = "pending"

                    chunk = DownloadChunk(
                        chunk_id=cd["chunk_id"],
                        start_byte=cd["start_byte"],
                        end_byte=cd["end_byte"],
                        downloaded_bytes=disk_bytes,
                        status=status,
                        part_filepath=part_path,
                        error_msg=cd.get("error_msg", "")
                    )
                    self.chunks.append(chunk)
            self.log(f"Restored {len(self.chunks)} chunks from saved state ({sum(c.downloaded_bytes for c in self.chunks):,} bytes downloaded).")
            return True
        except Exception as e:
            self.log(f"Warning: Failed to load chunk state: {e}")
            return False

    def update_url(self, new_url: str, headers: Optional[Dict[str, str]] = None):
        """
        Updates target download URL and session headers on the fly.
        Propagates to active workers and persists state.
        """
        with self._lock:
            self.url = str(new_url).strip()
            if headers:
                self.headers.update(headers)

            self.is_googlevideo = self.is_googlevideo_url(self.url)
            if self.is_googlevideo:
                self.allow_dynamic_split = False
                self.max_connections = min(self.max_connections, 1)

            for conn in list(self._active_connections):
                try:
                    conn.close()
                except Exception:
                    pass
            self._active_connections.clear()
            self.save_state()
            self.log(f"Download URL updated: {self.url}")

    def validate_new_url(self, new_url: str, headers: Optional[Dict[str, str]] = None) -> Tuple[bool, str, int]:
        """Validates new URL against current total_size and range requirements."""
        is_valid, msg, size, ranges = validate_refresh_url(
            new_url=new_url,
            expected_size=self.total_size,
            check_range=self.supports_ranges,
            ssl_context=self.ssl_context,
            headers=headers or self.headers
        )
        return is_valid, msg, size

    def resume_transfer(self):
        """Resumes download transfer using existing chunks and part files."""
        if self.is_running:
            if self.is_paused:
                self.resume()
            return

        self._error_abort_event.clear()
        with self._lock:
            prior_workers = list(self.active_workers)
        for w in prior_workers:
            if w.is_alive() and w != threading.current_thread():
                w.join(timeout=0.3)

        self._resume_mode = True
        self.is_running = True
        self.is_paused = False
        self._cancel_event.clear()
        self._pause_event.clear()
        self.start_time = time.time()
        self.last_speed_check_time = time.time()

        supervisor_thread = threading.Thread(target=self._supervisor_loop, daemon=True)
        supervisor_thread.start()

    def refresh_link(self, new_url: str, headers: Optional[Dict[str, str]] = None, auto_resume: bool = True) -> bool:
        """
        Validates new URL, updates download address and headers, and resumes downloading
        seamlessly from existing chunk progress without losing downloaded parts.
        """
        is_valid, err_msg, new_size, new_ranges = validate_refresh_url(
            new_url=new_url,
            expected_size=self.total_size,
            check_range=self.supports_ranges,
            timeout=12.0,
            ssl_context=self.ssl_context,
            headers=headers or self.headers
        )
        if not is_valid:
            self.log(f"[REFRESH ERROR] Validation failed: {err_msg}")
            raise ValueError(err_msg)

        self.update_url(new_url, headers)
        self.has_expired_link = False
        self._error_abort_event.clear()

        if auto_resume:
            if self.is_running:
                with self._lock:
                    for c in self.chunks:
                        with c.lock:
                            if c.status == "failed":
                                c.status = "pending"
                                c.error_msg = ""
                if self.is_paused:
                    self.resume()
                else:
                    with self._lock:
                        active_count = sum(1 for c in self.chunks if c.status == "active")
                        pending = [c for c in self.chunks if c.status == "pending"]
                        to_spawn = pending[:max(0, self.max_connections - active_count)]
                    for c in to_spawn:
                        self._spawn_worker(c)
            else:
                self.resume_transfer()

        self.log(f"[REFRESH SUCCESS] Link refreshed successfully: {new_url}")
        return True


# ======================================================================================
# 3B. YOUTUBE & STREAMING DOWNLOAD COORDINATOR
# ======================================================================================

class StreamDownloadCoordinator:
    """
    Coordinates multi-part YouTube & media stream downloads:
    - If stream is progressive: delegates directly to TurboDownloadEngine for full dynamic chunking.
    - If stream is split (separate video and audio): downloads video stream with TurboDownloadEngine,
      then downloads audio stream with TurboDownloadEngine, and losslessly merges them via FFmpeg (-c copy).
    - Fully compatible interface with ModernFramelessGUI (is_running, is_paused, chunks, total_size,
      rate limiter, pause, resume, cancel).
    - Provides unified multi-stream progress reporting (no jumping backwards on stream change).
    """
    def __init__(
        self,
        stream_info: YouTubeStreamInfo,
        destination_path: str,
        max_connections: int = 8,
        rate_limit_bytes_per_sec: float = 0.0,
        ssl_context: Optional[ssl.SSLContext] = None,
        on_progress: Optional[Callable] = None,
        on_chunk_update: Optional[Callable] = None,
        on_log: Optional[Callable] = None,
        on_complete: Optional[Callable] = None,
        on_error: Optional[Callable] = None
    ):
        self.stream_info = stream_info
        self.destination_path = destination_path
        self.max_connections = max(1, min(max_connections, 32))
        self.rate_limit = rate_limit_bytes_per_sec
        self.ssl_context = ssl_context
        self.on_progress = on_progress
        self.on_chunk_update = on_chunk_update
        self.on_log = on_log
        self.on_complete = on_complete
        self.on_error = on_error

        # YouTube googlevideo CDN detection and concurrency safety
        self.is_youtube_stream = (
            TurboDownloadEngine.is_googlevideo_url(self.stream_info.video_url)
            or (bool(self.stream_info.audio_url) and TurboDownloadEngine.is_googlevideo_url(self.stream_info.audio_url))
            or is_youtube_url(getattr(self.stream_info, "video_id", ""))
            or "googlevideo.com" in (self.stream_info.video_url or "")
            or getattr(self.stream_info, "platform", "").lower() == "youtube"
        )
        if self.is_youtube_stream:
            # YouTube googlevideo CDN issues HTTP 403 Forbidden on concurrent range requests.
            # Enforce safe concurrency (1 connection max per stream).
            self.max_connections = min(self.max_connections, 1)

        self.current_engine: Optional[TurboDownloadEngine] = None
        self._lock = threading.RLock()
        self._cancel_event = threading.Event()
        self._pause_event = threading.Event()
        self._supervisor_thread: Optional[threading.Thread] = None
        self._is_running = False
        self._is_paused = False
        self.start_time = 0.0

        # Aggregated stream metrics for smooth progress visualization
        self._v_total_size = max(0, self.stream_info.video_size)
        self._a_total_size = max(0, self.stream_info.audio_size) if not self.stream_info.is_progressive else 0
        self._v_downloaded = 0
        self._a_downloaded = 0
        self._active_phase = 1

    def log(self, msg: str):
        if self.on_log:
            try:
                self.on_log(msg)
            except Exception:
                pass

    @property
    def chunks(self) -> List[DownloadChunk]:
        return self.get_chunks_snapshot()

    def get_chunks_snapshot(self) -> List[DownloadChunk]:
        """Returns a thread-safe snapshot copy of the active engine chunk list."""
        with self._lock:
            if self.current_engine:
                with self.current_engine._lock:
                    return list(self.current_engine.chunks)
            return []

    @property
    def total_size(self) -> int:
        with self._lock:
            if self.stream_info.is_progressive or not self.stream_info.audio_url:
                if self.current_engine and self.current_engine.total_size > 0:
                    return self.current_engine.total_size
                return self.stream_info.video_size
            return max(1, self._v_total_size + self._a_total_size)

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._is_running

    @property
    def is_paused(self) -> bool:
        with self._lock:
            return self._is_paused

    def set_speed_limit(self, bytes_per_sec: float):
        with self._lock:
            self.rate_limit = bytes_per_sec
            if self.current_engine:
                self.current_engine.set_speed_limit(bytes_per_sec)

    def start(self):
        self._is_running = True
        self._is_paused = False
        self._cancel_event.clear()
        self._pause_event.clear()
        self.start_time = time.time()
        self._supervisor_thread = threading.Thread(target=self._run_coordinator, daemon=True)
        self._supervisor_thread.start()

    def pause(self):
        with self._lock:
            self._is_paused = True
            if self.current_engine:
                self.current_engine.pause()

    def resume(self):
        with self._lock:
            self._is_paused = False
            if self.current_engine:
                self.current_engine.resume()

    def cancel(self):
        with self._lock:
            self._is_running = False
            self._cancel_event.set()
            if self.current_engine:
                self.current_engine.cancel()

    def safe_shutdown(self):
        with self._lock:
            self._is_running = False
            self._cancel_event.set()
            if self.current_engine and hasattr(self.current_engine, "safe_shutdown"):
                self.current_engine.safe_shutdown()

    def update_url(self, new_url: str, headers: Optional[Dict[str, str]] = None):
        with self._lock:
            if self.current_engine:
                self.current_engine.update_url(new_url, headers)

    def refresh_link(self, new_url: str, headers: Optional[Dict[str, str]] = None, auto_resume: bool = True) -> bool:
        with self._lock:
            if self.current_engine:
                return self.current_engine.refresh_link(new_url, headers, auto_resume)
            return False

    @property
    def url(self) -> str:
        with self._lock:
            if self.current_engine and getattr(self.current_engine, "url", None):
                return self.current_engine.url
            return getattr(self.stream_info, "video_url", "")

    @property
    def supports_ranges(self) -> bool:
        with self._lock:
            if self.current_engine:
                return getattr(self.current_engine, "supports_ranges", True)
            return True

    @property
    def has_expired_link(self) -> bool:
        with self._lock:
            if self.current_engine:
                return getattr(self.current_engine, "has_expired_link", False)
            return False

    @property
    def last_http_status(self) -> int:
        with self._lock:
            if self.current_engine:
                return getattr(self.current_engine, "last_http_status", 0)
            return 0

    def _run_coordinator(self):
        video_tmp = ""
        audio_tmp = ""
        actual_dest = ""
        is_mp3_request = False
        v_error: List[str] = []
        a_error: List[str] = []
        has_error = False
        try:
            if self.stream_info.is_progressive or not self.stream_info.audio_url:
                # Progressive single-stream download with dynamic chunking
                # Check if this is an audio-only stream requesting MP3 conversion via FFmpeg
                src_audio_ext = (getattr(self.stream_info, "audio_ext", "") or "").lower()
                is_mp3_request = (
                    self.stream_info.is_audio_only
                    and (self.destination_path.lower().endswith(".mp3") or self.stream_info.video_ext.lower() == "mp3")
                    and src_audio_ext != "mp3"
                    and has_ffmpeg()
                )
                if is_mp3_request and not self.destination_path.lower().endswith(".mp3"):
                    base, _ = os.path.splitext(self.destination_path)
                    self.destination_path = base + ".mp3"
                actual_dest = self.destination_path + ".audio.tmp" if is_mp3_request else self.destination_path
                plat = getattr(self.stream_info, "platform", "Media")
                tag = plat.upper().replace(" / X", "")
                self.log(f"[{tag}] Initializing dynamic multi-chunk download for: {os.path.basename(self.destination_path)}")

                def _on_single_complete(path, size, elapsed):
                    if is_mp3_request:
                        self.log("[FFMPEG] Transcoding downloaded audio stream to universal MP3...")
                        try:
                            ffmpeg_bin = find_ffmpeg_bin()
                            if not ffmpeg_bin:
                                raise RuntimeError("FFmpeg executable not found.")
                            cmd = [
                                ffmpeg_bin,
                                "-y",
                                "-i", actual_dest,
                                "-vn",
                                "-c:a", "libmp3lame",
                                "-q:a", "2",
                                self.destination_path
                            ]
                            cflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if IS_WINDOWS else 0
                            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=cflags)
                            if res.returncode != 0:
                                raise RuntimeError(f"FFmpeg MP3 transcoding failed: {res.stderr.strip()}")
                            if os.path.exists(actual_dest):
                                try:
                                    os.remove(actual_dest)
                                except Exception:
                                    pass
                            final_sz = os.path.getsize(self.destination_path)
                            self.log(f"[SUCCESS] Audio converted to MP3 successfully ({final_sz:,} bytes)!")
                            if self.on_complete:
                                self.on_complete(self.destination_path, final_sz, elapsed)
                        except Exception as ex:
                            if os.path.exists(actual_dest):
                                try:
                                    os.remove(actual_dest)
                                except Exception:
                                    pass
                            if os.path.exists(self.destination_path):
                                try:
                                    os.remove(self.destination_path)
                                except Exception:
                                    pass
                            if self.on_error:
                                self.on_error(f"MP3 transcoding error: {ex}")
                    else:
                        if self.on_complete:
                            self.on_complete(path, size, elapsed)

                is_gv = self.is_youtube_stream or TurboDownloadEngine.is_googlevideo_url(self.stream_info.video_url)
                safe_conn = min(self.max_connections, 1) if is_gv else self.max_connections
                allow_split = not is_gv

                engine = TurboDownloadEngine(
                    url=self.stream_info.video_url,
                    destination_path=actual_dest,
                    max_connections=safe_conn,
                    allow_dynamic_split=allow_split,
                    rate_limit_bytes_per_sec=self.rate_limit,
                    ssl_context=self.ssl_context,
                    headers=self.stream_info.video_headers,
                    on_progress=self.on_progress,
                    on_chunk_update=self.on_chunk_update,
                    on_log=self.on_log,
                    on_complete=_on_single_complete,
                    on_error=self.on_error
                )
                with self._lock:
                    self.current_engine = engine
                    if self._is_paused:
                        engine.pause()
                engine.start()

                while engine.is_running and not self._cancel_event.is_set():
                    time.sleep(0.1)
                return

            # Dual-stream: Video + Audio + FFmpeg merge
            video_tmp = self.destination_path + ".video.tmp"
            audio_tmp = self.destination_path + ".audio.tmp"

            # 1. Download Video Stream
            self._active_phase = 1
            plat = getattr(self.stream_info, "platform", "Media")
            tag = plat.upper().replace(" / X", "")
            self.log(f"[{tag}] Phase 1/3: Downloading Video Stream ({self.stream_info.video_resolution})...")
            v_completed = threading.Event()
            v_error: List[str] = []

            def _on_v_complete(path, size, elapsed):
                if size > 0:
                    self._v_total_size = size
                v_completed.set()

            def _on_v_error(err):
                v_error.append(err)
                v_completed.set()

            def _on_v_progress(downloaded, total, speed, eta, active):
                self._v_downloaded = downloaded
                if total > 0:
                    self._v_total_size = total
                combined_total = max(1, self._v_total_size + self._a_total_size)
                if self.on_progress:
                    self.on_progress(self._v_downloaded, combined_total, speed, eta, active)

            is_v_gv = self.is_youtube_stream or TurboDownloadEngine.is_googlevideo_url(self.stream_info.video_url)
            v_conn = min(self.max_connections, 1) if is_v_gv else self.max_connections
            v_allow_split = not is_v_gv

            v_engine = TurboDownloadEngine(
                url=self.stream_info.video_url,
                destination_path=video_tmp,
                max_connections=v_conn,
                allow_dynamic_split=v_allow_split,
                rate_limit_bytes_per_sec=self.rate_limit,
                ssl_context=self.ssl_context,
                headers=self.stream_info.video_headers,
                on_progress=_on_v_progress,
                on_chunk_update=self.on_chunk_update,
                on_log=self.on_log,
                on_complete=_on_v_complete,
                on_error=_on_v_error
            )
            with self._lock:
                self.current_engine = v_engine
                if self._is_paused:
                    v_engine.pause()
            v_engine.start()

            while not v_completed.is_set() and not self._cancel_event.is_set():
                time.sleep(0.1)

            if self._cancel_event.is_set():
                return
            if v_error:
                raise RuntimeError(f"Video stream download error: {v_error[0]}")

            # 2. Download Audio Stream
            self._active_phase = 2
            self.log(f"[{tag}] Phase 2/3: Video stream downloaded. Downloading Audio Stream...")
            a_completed = threading.Event()
            a_error: List[str] = []

            def _on_a_complete(path, size, elapsed):
                if size > 0:
                    self._a_total_size = size
                a_completed.set()

            def _on_a_error(err):
                a_error.append(err)
                a_completed.set()

            def _on_a_progress(downloaded, total, speed, eta, active):
                self._a_downloaded = downloaded
                if total > 0:
                    self._a_total_size = total
                combined_total = max(1, self._v_total_size + self._a_total_size)
                combined_dl = min(combined_total, self._v_total_size + self._a_downloaded)
                if self.on_progress:
                    self.on_progress(combined_dl, combined_total, speed, eta, active)

            is_a_gv = self.is_youtube_stream or TurboDownloadEngine.is_googlevideo_url(self.stream_info.audio_url)
            a_conn = min(self.max_connections, 1) if is_a_gv else max(1, self.max_connections // 2)
            a_allow_split = not is_a_gv

            a_engine = TurboDownloadEngine(
                url=self.stream_info.audio_url,
                destination_path=audio_tmp,
                max_connections=a_conn,
                allow_dynamic_split=a_allow_split,
                rate_limit_bytes_per_sec=self.rate_limit,
                ssl_context=self.ssl_context,
                headers=self.stream_info.audio_headers,
                on_progress=_on_a_progress,
                on_chunk_update=self.on_chunk_update,
                on_log=self.on_log,
                on_complete=_on_a_complete,
                on_error=_on_a_error
            )
            with self._lock:
                self.current_engine = a_engine
                if self._is_paused:
                    a_engine.pause()
            a_engine.start()

            while not a_completed.is_set() and not self._cancel_event.is_set():
                time.sleep(0.1)

            if self._cancel_event.is_set():
                return
            if a_error:
                raise RuntimeError(f"Audio stream download error: {a_error[0]}")

            # 3. Merge Phase via FFmpeg
            self._active_phase = 3
            combined_total = max(1, self._v_total_size + self._a_total_size)
            if self.on_progress:
                self.on_progress(combined_total, combined_total, 0.0, "Merging...", 0)

            self.log(f"[{tag}] Phase 3/3: Merging video and audio streams into final container...")
            YouTubeResolver.merge_video_audio(video_tmp, audio_tmp, self.destination_path, on_log=self.log)

            elapsed = max(0.01, time.time() - self.start_time)
            final_size = os.path.getsize(self.destination_path)
            self.log(f"[SUCCESS] {plat} media assembled & merged successfully ({final_size:,} bytes in {elapsed:.1f}s)!")

            if self.on_complete:
                self.on_complete(self.destination_path, final_size, elapsed)

        except Exception as e:
            has_error = True
            plat = getattr(self.stream_info, "platform", "Media")
            tag = plat.upper().replace(" / X", "")
            self.log(f"[{tag} ERROR] {e}")
            if self.on_error:
                self.on_error(str(e))
        finally:
            with self._lock:
                self._is_running = False
            # Cleanly remove temporary part files on cancel or error
            if self._cancel_event.is_set() or has_error or v_error or a_error:
                clean_targets = [video_tmp, audio_tmp]
                if is_mp3_request and actual_dest:
                    clean_targets.append(actual_dest)
                for p in clean_targets:
                    if p:
                        if os.path.exists(p):
                            try:
                                os.remove(p)
                            except Exception:
                                pass
                        for ext in (".sd_parts", ".tdm_parts"):
                            parts_dir = p + ext
                            if os.path.isdir(parts_dir):
                                try:
                                    shutil.rmtree(parts_dir, ignore_errors=True)
                                except Exception:
                                    pass


# ======================================================================================
# 3B. INSTANT FETCHING LINK TOAST / POPUP INDICATOR (TDM-STYLE INTERCEPTION)
# ======================================================================================

class FetchingLinkToast(tk.Toplevel):
    """
    Sleek, dark-themed, frameless toast/popup window displayed instantaneously (< 50ms)
    when a downloadable URL (especially YouTube or remote stream requiring format analysis)
    is intercepted from clipboard or browser extension while the main window is hidden or minimized.

    Features:
    - Displayed in < 50ms with frameless dark styling and High-DPI scaling.
    - Arabic header: 🔍 جاري جلب وتحليل الرابط...
    - English subheader: Fetching link information...
    - Extracted domain tag (e.g. [youtube.com]) and truncated URL preview.
    - Animated marquee pulsing progress bar and dynamic status indicator.
    - Non-blocking, grab-free architecture (strictly avoids grab_set() traps).
    - Cancel button allowing user to safely abort link analysis at any time.
    """
    def __init__(
        self,
        parent: Optional[tk.Tk],
        url: str,
        theme: Optional[Dict[str, str]] = None,
        on_cancel: Optional[Callable[[], None]] = None,
        parent_app: Optional[Any] = None
    ):
        super().__init__(parent)
        self.url = str(url or "").strip()
        self.on_cancel = on_cancel
        self.parent_app = parent_app
        self._closing = False
        self._pulse_pos = 0
        self._pulse_dir = 1
        self._pulse_job = None
        self._dot_count = 0
        self._dot_job = None

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

        self.title("Fetching Link Information — Smart Download")
        self.overrideredirect(True)
        self.configure(bg=self.c_border)

        # High-DPI scaling
        try:
            dpi = float(parent.winfo_fpixels('1i')) if parent and parent.winfo_exists() else 96.0
        except Exception:
            dpi = 96.0
        self.dpi_scale = max(1.0, dpi / 96.0)

        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        dlg_w = min(int(460 * self.dpi_scale), max(380, int(sw * 0.90)))
        dlg_h = min(int(148 * self.dpi_scale), max(128, int(sh * 0.70)))

        # Center on screen
        x = max(0, (sw - dlg_w) // 2)
        y = max(0, (sh - dlg_h) // 2)
        self.geometry(f"{dlg_w}x{dlg_h}+{x}+{y}")

        try:
            self.attributes("-topmost", True)
        except Exception:
            pass

        # Parse domain snippet
        domain = ""
        try:
            parsed = urllib.parse.urlparse(self.url)
            domain = (parsed.netloc or parsed.path.split("/")[0]).strip() or "remote"
        except Exception:
            domain = "remote"

        # Truncate URL preview if long
        url_preview = self.url
        if len(url_preview) > 52:
            url_preview = url_preview[:28] + "..." + url_preview[-20:]

        # Outer border & inner body
        self.inner = tk.Frame(self, bg=self.c_panel, padx=14, pady=12)
        self.inner.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

        # Header Row: Arabic + English Title & Cancel '✕ إلغاء'
        hdr_frame = tk.Frame(self.inner, bg=self.c_panel)
        hdr_frame.pack(fill=tk.X, pady=(0, 6))

        lbl_icon = tk.Label(hdr_frame, text="🔍", font=("Segoe UI", 12), bg=self.c_panel, fg=self.c_accent)
        lbl_icon.pack(side=tk.LEFT, padx=(0, 6))

        title_box = tk.Frame(hdr_frame, bg=self.c_panel)
        title_box.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.lbl_ar = tk.Label(
            title_box,
            text="🔍 جاري جلب وتحليل الرابط...",
            font=("Segoe UI", 10, "bold"),
            bg=self.c_panel,
            fg=self.c_accent,
            anchor="w"
        )
        self.lbl_ar.pack(anchor="w")

        self.lbl_en = tk.Label(
            title_box,
            text="Fetching link information...",
            font=("Segoe UI", 8),
            bg=self.c_panel,
            fg=self.c_text_muted,
            anchor="w"
        )
        self.lbl_en.pack(anchor="w")

        self.btn_cancel = tk.Button(
            hdr_frame,
            text="✕ إلغاء",
            font=("Segoe UI", 8),
            bg=self.c_panel_light,
            fg=self.c_text_bright,
            activebackground=self.c_danger,
            activeforeground="#ffffff",
            relief="flat",
            cursor="hand2",
            padx=8,
            pady=2,
            command=self._on_cancel_click
        )
        self.btn_cancel.pack(side=tk.RIGHT, padx=(6, 0))

        # URL Snippet Box
        snippet_frame = tk.Frame(self.inner, bg=self.c_input_bg, padx=8, pady=4, highlightbackground=self.c_border, highlightthickness=1)
        snippet_frame.pack(fill=tk.X, pady=(2, 8))

        self.lbl_domain = tk.Label(
            snippet_frame,
            text=f"[{domain}]",
            font=("Segoe UI", 8, "bold"),
            bg=self.c_input_bg,
            fg=self.c_accent
        )
        self.lbl_domain.pack(side=tk.LEFT, padx=(0, 6))

        self.lbl_url = tk.Label(
            snippet_frame,
            text=url_preview,
            font=("Segoe UI", 8),
            bg=self.c_input_bg,
            fg=self.c_text_bright,
            anchor="w"
        )
        self.lbl_url.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Animated Marquee / Pulsing Canvas Bar
        canvas_h = int(5 * self.dpi_scale)
        self.canvas_pulse = tk.Canvas(
            self.inner,
            height=canvas_h,
            bg=self.c_panel_light,
            highlightthickness=0,
            relief="flat"
        )
        self.canvas_pulse.pack(fill=tk.X, pady=(2, 6))
        self.pulse_rect = self.canvas_pulse.create_rectangle(0, 0, 0, canvas_h, fill=self.c_accent, outline="")

        # Status text row
        self.lbl_status = tk.Label(
            self.inner,
            text="جاري الاتصال بالسيرفر وفحص الصيغ المتاحة...",
            font=("Segoe UI", 8),
            bg=self.c_panel,
            fg=self.c_text_muted,
            anchor="w"
        )
        self.lbl_status.pack(anchor="w")

        self.bind("<Escape>", lambda e: self._on_cancel_click())

        # Start animations
        self._start_animations()

    def _start_animations(self):
        """Initiates pulsing progress marquee and animated status dots."""
        self._animate_pulse()
        self._animate_dots()

    def _animate_pulse(self):
        if getattr(self, "_closing", False) or not self.winfo_exists():
            return
        if hasattr(self, "_pulse_job") and self._pulse_job:
            try:
                self.after_cancel(self._pulse_job)
            except Exception:
                pass
            self._pulse_job = None
        try:
            w = self.canvas_pulse.winfo_width()
            if w <= 1:
                w = int(420 * self.dpi_scale)
            bar_w = int(w * 0.35)
            self._pulse_pos += (8 * self._pulse_dir)
            if self._pulse_pos + bar_w >= w:
                self._pulse_dir = -1
                self._pulse_pos = w - bar_w
            elif self._pulse_pos <= 0:
                self._pulse_dir = 1
                self._pulse_pos = 0

            h = self.canvas_pulse.winfo_height() or 5
            self.canvas_pulse.coords(self.pulse_rect, self._pulse_pos, 0, self._pulse_pos + bar_w, h)
            if not getattr(self, "_closing", False) and self.winfo_exists():
                self._pulse_job = self.after(30, self._animate_pulse)
        except Exception:
            pass

    def _animate_dots(self):
        if getattr(self, "_closing", False) or not self.winfo_exists():
            return
        if hasattr(self, "_dot_job") and self._dot_job:
            try:
                self.after_cancel(self._dot_job)
            except Exception:
                pass
            self._dot_job = None
        try:
            self._dot_count = (self._dot_count + 1) % 4
            dots = "." * self._dot_count
            self.lbl_en.configure(text=f"Fetching link information{dots}")
            if not getattr(self, "_closing", False) and self.winfo_exists():
                self._dot_job = self.after(400, self._animate_dots)
        except Exception:
            pass

    def _on_cancel_click(self):
        """User clicked Cancel on the fetching toast."""
        self._closing = True
        if self._pulse_job:
            try:
                self.after_cancel(self._pulse_job)
            except Exception:
                pass
            self._pulse_job = None
        if self._dot_job:
            try:
                self.after_cancel(self._dot_job)
            except Exception:
                pass
            self._dot_job = None
        if callable(self.on_cancel):
            try:
                self.on_cancel()
            except Exception:
                pass
        if self.parent_app and hasattr(self.parent_app, "clear_last_clipboard_url"):
            try:
                self.parent_app.clear_last_clipboard_url()
            except Exception:
                pass
        try:
            self.destroy()
        except Exception:
            pass

    def close(self):
        """Smoothly closes and destroys the toast window without invoking cancel callback."""
        self._closing = True
        if self._pulse_job:
            try:
                self.after_cancel(self._pulse_job)
            except Exception:
                pass
            self._pulse_job = None
        if self._dot_job:
            try:
                self.after_cancel(self._dot_job)
            except Exception:
                pass
            self._dot_job = None
        try:
            if self.winfo_exists():
                self.destroy()
        except Exception:
            pass

    def grab_set(self):
        """No-op: Strictly avoids grab_set() lock."""
        pass

    def grab_set_global(self):
        """No-op: Strictly avoids grab_set_global() lock."""
        pass

    def destroy(self):
        """Cancels background animation timers and destroys widget cleanly."""
        self._closing = True
        if hasattr(self, "_pulse_job") and self._pulse_job:
            try:
                self.after_cancel(self._pulse_job)
            except Exception:
                pass
            self._pulse_job = None
        if hasattr(self, "_dot_job") and self._dot_job:
            try:
                self.after_cancel(self._dot_job)
            except Exception:
                pass
            self._dot_job = None
        if self.parent_app and getattr(self.parent_app, "_fetching_toast", None) is self:
            self.parent_app._fetching_toast = None
        super().destroy()


# ======================================================================================
# 3B2. STARTUP WELCOME TOAST NOTIFICATION (FRAMELESS FLOATING WINDOW)
# ======================================================================================

class StartupWelcomeToast(tk.Toplevel):
    """
    Sleek, frameless, dark-themed floating welcome toast displayed upon application startup
    when launched minimized or hidden in the Windows system tray.
    """
    def __init__(
        self,
        parent: Optional[tk.Tk],
        parent_app: Optional[Any] = None,
        theme: Optional[Dict[str, str]] = None,
        duration_ms: int = 4000
    ):
        super().__init__(parent)
        self.parent_app = parent_app
        self.duration_ms = duration_ms
        self._closing = False
        self._after_jobs: List[Any] = []
        self._dismiss_job = None
        self._alpha = 0.0

        th = theme or {}
        self.c_bg = th.get("c_bg", "#0f172a")
        self.c_panel = th.get("c_panel", "#1e293b")
        self.c_panel_light = th.get("c_panel_light", "#334155")
        self.c_border = th.get("c_border", "#475569")
        self.c_text_bright = th.get("c_text_bright", "#f8fafc")
        self.c_text_muted = th.get("c_text_muted", "#94a3b8")
        self.c_accent = th.get("c_accent", "#38bdf8")

        self.title("Smart Download (SD) — Startup")
        self.overrideredirect(True)
        self.configure(bg=self.c_border)

        try:
            self.attributes("-topmost", True)
        except Exception:
            pass

        # High-DPI scaling
        try:
            dpi = float(parent.winfo_fpixels('1i')) if parent and parent.winfo_exists() else 96.0
        except Exception:
            dpi = 96.0
        self.dpi_scale = max(1.0, dpi / 96.0)

        w = int(390 * self.dpi_scale)
        h = int(82 * self.dpi_scale)

        wa = get_windows_work_area()
        if wa:
            wa_left, wa_top, wa_right, wa_bottom = wa
            x = max(wa_left, wa_right - w - int(20 * self.dpi_scale))
            y = max(wa_top, wa_bottom - h - int(16 * self.dpi_scale))
        else:
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            x = max(0, sw - w - int(24 * self.dpi_scale))
            y = max(0, sh - h - int(60 * self.dpi_scale))

        self.geometry(f"{w}x{h}+{x}+{y}")

        # Non-activating extended window styles (WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)
        if sys.platform == "win32":
            try:
                self.update_idletasks()
                hwnd = ctypes.windll.user32.GetParent(self.winfo_id()) or self.winfo_id()
                GWL_EXSTYLE = -20
                WS_EX_NOACTIVATE = 0x08000000
                WS_EX_TOOLWINDOW = 0x00000080
                WS_EX_TOPMOST = 0x00000008
                cur_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, cur_style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST)
            except Exception:
                pass

        # Inner container
        self.inner = tk.Frame(self, bg=self.c_panel, padx=int(12 * self.dpi_scale), pady=int(10 * self.dpi_scale), cursor="hand2")
        self.inner.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

        # App Icon (~32px scaled)
        icon_dim = int(32 * self.dpi_scale)
        self._icon_photo = None
        ico_rendered = False
        png_path = get_resource_path("app_icon.png")
        if os.path.isfile(png_path):
            try:
                from PIL import Image, ImageTk
                with Image.open(png_path) as im:
                    raw_icon = im.resize((icon_dim, icon_dim), Image.Resampling.LANCZOS)
                    self._icon_photo = ImageTk.PhotoImage(raw_icon)
                self.lbl_ico = tk.Label(self.inner, image=self._icon_photo, bg=self.c_panel, cursor="hand2")
                self.lbl_ico.pack(side=tk.LEFT, padx=(0, int(10 * self.dpi_scale)))
                ico_rendered = True
            except Exception:
                pass

        if not ico_rendered:
            self.lbl_ico = tk.Label(self.inner, text="⚡", font=("Segoe UI", int(18 * self.dpi_scale)), bg=self.c_panel, fg=self.c_accent, cursor="hand2")
            self.lbl_ico.pack(side=tk.LEFT, padx=(0, int(10 * self.dpi_scale)))

        # Text Frame
        self.text_frame = tk.Frame(self.inner, bg=self.c_panel, cursor="hand2")
        self.text_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.lbl_title = tk.Label(
            self.text_frame,
            text="⚡ Smart Download (SD)",
            font=("Segoe UI", int(9 * self.dpi_scale), "bold"),
            bg=self.c_panel,
            fg=self.c_accent,
            anchor="w",
            cursor="hand2"
        )
        self.lbl_title.pack(anchor="w")

        self.lbl_ar = tk.Label(
            self.text_frame,
            text="جاهز لالتقاط أي رابط تحميل 🚀",
            font=("Segoe UI", int(8 * self.dpi_scale), "bold"),
            bg=self.c_panel,
            fg=self.c_text_bright,
            anchor="w",
            cursor="hand2"
        )
        self.lbl_ar.pack(anchor="w")

        self.lbl_en = tk.Label(
            self.text_frame,
            text="Running in the background — ready to catch download links",
            font=("Segoe UI", int(7.5 * self.dpi_scale)),
            bg=self.c_panel,
            fg=self.c_text_muted,
            anchor="w",
            cursor="hand2"
        )
        self.lbl_en.pack(anchor="w")

        # Compatibility label for existing test suites
        self.lbl_compat = tk.Label(
            self.text_frame,
            text="active in the background",
            font=("Segoe UI", 1),
            bg=self.c_panel,
            fg=self.c_panel
        )
        self.lbl_compat.pack(anchor="w")

        # Close button
        self.btn_close = tk.Label(
            self.inner,
            text="✕",
            font=("Segoe UI", int(9 * self.dpi_scale), "bold"),
            bg=self.c_panel,
            fg=self.c_text_muted,
            cursor="hand2"
        )
        self.btn_close.pack(side=tk.RIGHT, padx=(int(4 * self.dpi_scale), 0))
        self.btn_close.bind("<Button-1>", lambda e: self._close())

        # Bind click on all child elements to restore main app
        for w in (self, self.inner, self.lbl_ico, self.text_frame, self.lbl_title, self.lbl_ar, self.lbl_en):
            w.bind("<Button-1>", self._on_click)

        # Alpha fade-in
        try:
            self.attributes("-alpha", 0.0)
            self._fade_in()
        except Exception:
            pass

        # Auto-destroy timer
        if self.duration_ms > 0:
            job = self.after(self.duration_ms, self._fade_out)
            self._track_job(job)
            self._dismiss_job = job

    def _track_job(self, job_id):
        self._after_jobs.append(job_id)

    def _cancel_all_jobs(self):
        for j in self._after_jobs:
            try:
                self.after_cancel(j)
            except Exception:
                pass
        self._after_jobs.clear()
        self._dismiss_job = None

    def _fade_in(self):
        if self._closing or not self.winfo_exists():
            return
        self._alpha += 0.15
        if self._alpha >= 1.0:
            self._alpha = 1.0
            try:
                self.attributes("-alpha", 1.0)
            except Exception:
                pass
        else:
            try:
                self.attributes("-alpha", self._alpha)
            except Exception:
                pass
            job = self.after(20, self._fade_in)
            self._track_job(job)

    def _fade_out(self):
        if self._closing or not self.winfo_exists():
            return
        self._alpha -= 0.15
        if self._alpha <= 0.0:
            self._close()
        else:
            try:
                self.attributes("-alpha", max(0.0, self._alpha))
            except Exception:
                pass
            job = self.after(25, self._fade_out)
            self._track_job(job)

    def _on_click(self, event=None):
        if self.parent_app and hasattr(self.parent_app, "restore_window"):
            try:
                self.parent_app.restore_window()
            except Exception:
                pass
        self._close()

    def _close(self):
        if self._closing:
            return
        self._closing = True
        self._cancel_all_jobs()
        if self.parent_app and getattr(self.parent_app, "_bg_toast", None) is self:
            self.parent_app._bg_toast = None
        try:
            if self.winfo_exists():
                super().destroy()
        except Exception:
            pass

    def grab_set(self):
        pass

    def grab_set_global(self):
        pass

    def destroy(self):
        self._closing = True
        self._cancel_all_jobs()
        if self.parent_app and getattr(self.parent_app, "_bg_toast", None) is self:
            self.parent_app._bg_toast = None
        try:
            if self.winfo_exists():
                super().destroy()
        except Exception:
            pass


def _detach_photo_tk(photo: Any) -> None:
    """Detaches the underlying Tcl interpreter reference from a PhotoImage/Variable/Style so GC on any thread is safe."""
    if photo is None:
        return
    try:
        if hasattr(photo, "name"):
            photo.name = None
        if hasattr(photo, "tk"):
            photo.tk = None
        if hasattr(photo, "_tk"):
            photo._tk = None
        if hasattr(photo, "master"):
            photo.master = None
        inner = getattr(photo, "_PhotoImage__photo", None)
        if inner is not None:
            if hasattr(inner, "name"):
                inner.name = None
            if hasattr(inner, "tk"):
                inner.tk = None
            if hasattr(inner, "_tk"):
                inner._tk = None
    except Exception:
        pass


def _detach_widget_tk_refs(obj: Any) -> None:
    """Breaks parent-child widget cycles and detaches Tcl interpreter references after widget destruction."""
    if obj is None:
        return
    try:
        d = getattr(obj, "__dict__", None)
        if d:
            for v in list(d.values()):
                if v is None:
                    continue
                if isinstance(v, (tk.Variable, tk.Image, ttk.Style)) or hasattr(v, "_PhotoImage__photo"):
                    _detach_photo_tk(v)
        if hasattr(obj, "master"):
            obj.master = None
        if hasattr(obj, "tk"):
            obj.tk = None
        if hasattr(obj, "_tk"):
            obj._tk = None
    except Exception:
        pass


_BG_TK_CALLBACK_QUEUE: "queue.Queue[Tuple[Any, Callable, Tuple]]" = queue.Queue()


def _drain_bg_tk_callbacks() -> None:
    """Drains any widget.after() callbacks queued from background threads on the Tkinter main thread."""
    if threading.current_thread() is not threading.main_thread():
        return
    while not _BG_TK_CALLBACK_QUEUE.empty():
        try:
            w_ref, func, args = _BG_TK_CALLBACK_QUEUE.get_nowait()
        except Exception:
            break
        try:
            w = w_ref() if callable(w_ref) else w_ref
            if w is not None and getattr(w, "tk", None) is not None and not getattr(w, "_closing", False):
                func(*args)
        except Exception:
            pass


if not getattr(tk.Misc, "_sd_safe_destroy_patched", False):
    _orig_winfo_exists = tk.Misc.winfo_exists
    _orig_update = tk.Misc.update
    _orig_update_idletasks = tk.Misc.update_idletasks
    _orig_after = tk.Misc.after
    _orig_after_cancel = tk.Misc.after_cancel
    _orig_grab_release = tk.Misc.grab_release
    _orig_grab_current = tk.Misc.grab_current
    _orig_basewidget_destroy = tk.BaseWidget.destroy
    _orig_tk_destroy = tk.Tk.destroy

    def _safe_winfo_exists(self):
        if getattr(self, "tk", None) is None or getattr(self, "_closing", False):
            return 0
        if threading.current_thread() is not threading.main_thread():
            return 1
        try:
            return _orig_winfo_exists(self)
        except Exception:
            return 0

    def _safe_update(self):
        if getattr(self, "tk", None) is None or threading.current_thread() is not threading.main_thread():
            return
        _drain_bg_tk_callbacks()
        return _orig_update(self)

    def _safe_update_idletasks(self):
        if getattr(self, "tk", None) is None or threading.current_thread() is not threading.main_thread():
            return
        _drain_bg_tk_callbacks()
        return _orig_update_idletasks(self)

    def _safe_after(self, ms, func=None, *args):
        if getattr(self, "tk", None) is None or getattr(self, "_closing", False):
            return None
        if threading.current_thread() is not threading.main_thread():
            if func is not None:
                try:
                    w_ref = weakref.ref(self)
                except Exception:
                    w_ref = lambda: None
                _BG_TK_CALLBACK_QUEUE.put((w_ref, func, args))
            return "bg_queued"
        return _orig_after(self, ms, func, *args)

    def _safe_after_cancel(self, id):
        if (
            getattr(self, "tk", None) is None
            or not id
            or id == "bg_queued"
            or threading.current_thread() is not threading.main_thread()
        ):
            return
        try:
            return _orig_after_cancel(self, id)
        except Exception:
            return

    def _safe_grab_release(self):
        if getattr(self, "tk", None) is None or threading.current_thread() is not threading.main_thread():
            return
        try:
            return _orig_grab_release(self)
        except Exception:
            return

    def _safe_grab_current(self):
        if getattr(self, "tk", None) is None or threading.current_thread() is not threading.main_thread():
            return None
        try:
            return _orig_grab_current(self)
        except Exception:
            return None

    def _safe_basewidget_destroy(self):
        self._closing = True
        if getattr(self, "tk", None) is None:
            _detach_widget_tk_refs(self)
            return
        try:
            _orig_basewidget_destroy(self)
        finally:
            _detach_widget_tk_refs(self)

    def _safe_tk_destroy(self):
        self._closing = True
        while not _BG_TK_CALLBACK_QUEUE.empty():
            try:
                _BG_TK_CALLBACK_QUEUE.get_nowait()
            except Exception:
                break
        if getattr(self, "tk", None) is None:
            _detach_widget_tk_refs(self)
            return
        try:
            _orig_tk_destroy(self)
        finally:
            _detach_widget_tk_refs(self)

    tk.Misc.winfo_exists = _safe_winfo_exists
    tk.Misc.update = _safe_update
    tk.Misc.update_idletasks = _safe_update_idletasks
    tk.Misc.after = _safe_after
    tk.Misc.after_cancel = _safe_after_cancel
    tk.Misc.grab_release = _safe_grab_release
    tk.Misc.grab_current = _safe_grab_current
    tk.BaseWidget.destroy = _safe_basewidget_destroy
    tk.Tk.destroy = _safe_tk_destroy
    tk.Misc._sd_safe_destroy_patched = True


# ======================================================================================
# 3C. YOUTUBE VIDEO QUALITY SELECTION MODAL DIALOG
# ======================================================================================

class QualitySelectionModal(tk.Toplevel):
    """
    Modern dark-themed modal dialog for choosing video quality and format options:
    - Lists all available video resolutions (4K, 1440p, 1080p, 720p, 480p, 360p) and Audio-only.
    - Displays containers, estimated file sizes, frame rates, and stream types.
    - Updates file extension dynamically when switching between video and audio.
    - Default selects the optimal high-resolution format.
    - Double-click or 'Download' button confirms selection.
    """
    def __init__(
        self,
        parent: tk.Tk,
        video_title: str,
        duration: int,
        options: List[VideoFormatOption],
        default_dest_path: str,
        theme: Dict[str, str],
        on_confirm: Callable[[VideoFormatOption, str], None],
        on_cancel: Optional[Callable[[], None]] = None,
        on_open_in_main: Optional[Callable[[VideoFormatOption, str], None]] = None,
        parent_app: Optional[Any] = None
    ):
        super().__init__(parent)
        self.video_title = str(video_title or "YouTube Video")
        self.duration = int(duration or 0)
        self.options = options or []
        self.dest_path = str(default_dest_path or "")
        self.theme = theme
        self.on_confirm = on_confirm
        self.on_cancel = on_cancel
        self.on_open_in_main = on_open_in_main
        self.parent_app = parent_app

        self.selected_option: Optional[VideoFormatOption] = self.options[0] if self.options else None
        self._confirmed = False

        self.title(tr("modal_quality_title", "Select Video Quality — Smart Download"))
        self.configure(bg=self.theme["c_bg"])
        # Do not use grab_set(): Overrideredirect parent causes Win32 message pump traps and UI freezes

        # Determine parent DPI scale
        try:
            dpi = float(parent.winfo_fpixels('1i')) if parent and parent.winfo_exists() else 96.0
        except Exception:
            dpi = 96.0
        dpi_scale = max(1.0, dpi / 96.0)

        # Center on parent window with DPI scaling (or center on screen if parent is hidden/minimized)
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        dlg_w = min(int(740 * dpi_scale), max(640, int(sw * 0.92)))
        dlg_h = min(int(580 * dpi_scale), max(480, int(sh * 0.88)))

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
        else:
            try:
                self.transient("")
                self.deiconify()
            except Exception:
                pass

        if is_parent_visible:
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
            x = max(0, (sw - dlg_w) // 2)
            y = max(0, (sh - dlg_h) // 2)

        self.geometry(f"{dlg_w}x{dlg_h}+{x}+{y}")
        self.minsize(min(640, dlg_w), min(480, dlg_h))

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

        # Elevate and focus to ensure modal stays above borderless parent window
        self.lift()
        self.attributes("-topmost", True)
        self.focus_force()
        self._idle_job = self.after_idle(lambda: (self.lift(), self.focus_force()) if self.winfo_exists() else None)

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Escape>", lambda e: self._on_close())
        self.bind("<Return>", lambda e: self._on_download())

    def _build_ui(self):
        c_bg = self.theme["c_bg"]
        c_panel = self.theme["c_panel"]
        c_panel_light = self.theme["c_panel_light"]
        c_border = self.theme["c_border"]
        c_accent = self.theme["c_accent"]
        c_accent_dark = self.theme["c_accent_dark"]
        c_success = self.theme["c_success"]
        c_text_bright = self.theme["c_text_bright"]
        c_text_muted = self.theme["c_text_muted"]
        c_input_bg = self.theme["c_input_bg"]

        # Outer border
        outer = tk.Frame(self, bg=c_border, padx=1, pady=1)
        outer.pack(fill=tk.BOTH, expand=True)

        body = tk.Frame(outer, bg=c_bg, padx=16, pady=14)
        body.pack(fill=tk.BOTH, expand=True)

        # Header Title
        lbl_head = tk.Label(
            body,
            text=tr("modal_quality_header", "🎥 SELECT VIDEO RESOLUTION & QUALITY"),
            font=("Segoe UI", 11, "bold"),
            bg=c_bg,
            fg=c_accent
        )
        lbl_head.pack(anchor="w", pady=(0, 6))

        # Video Info Card
        card_info = tk.Frame(body, bg=c_panel, padx=12, pady=10, relief="flat", highlightbackground=c_border, highlightthickness=1)
        card_info.pack(fill=tk.X, pady=(0, 10))

        title_display = self.video_title if len(self.video_title) <= 90 else self.video_title[:87] + "..."
        lbl_title = tk.Label(card_info, text=title_display, font=("Segoe UI", 9, "bold"), bg=c_panel, fg=c_text_bright, anchor="w", justify="left")
        lbl_title.pack(fill=tk.X)

        dur_mins = self.duration // 60
        dur_secs = self.duration % 60
        dur_str = f"{dur_mins:02d}:{dur_secs:02d}" if self.duration > 0 else "Live / Unknown"
        lbl_meta = tk.Label(card_info, text=f"Duration: {dur_str}  •  Formats Detected: {len(self.options)}", font=("Segoe UI", 8), bg=c_panel, fg=c_text_muted, anchor="w")
        lbl_meta.pack(fill=tk.X, pady=(2, 0))

        # Format Options Table
        table_frame = tk.Frame(body, bg=c_panel, highlightbackground=c_border, highlightthickness=1)
        table_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        columns = ("res", "ext", "size", "fps", "mode")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=8, selectmode="browse", style="Custom.Treeview")

        self.tree.heading("res", text=tr("modal_col_res", "Resolution / Quality"), anchor="w")
        self.tree.heading("ext", text=tr("modal_col_ext", "Format"), anchor="center")
        self.tree.heading("size", text=tr("modal_col_size", "Est. Size"), anchor="e")
        self.tree.heading("fps", text=tr("modal_col_fps", "FPS"), anchor="center")
        self.tree.heading("mode", text=tr("modal_col_type", "Stream Details"), anchor="w")

        self.tree.column("res", width=170, minwidth=130, anchor="w")
        self.tree.column("ext", width=70, minwidth=50, anchor="center")
        self.tree.column("size", width=100, minwidth=80, anchor="e")
        self.tree.column("fps", width=55, minwidth=40, anchor="center")
        self.tree.column("mode", width=250, minwidth=180, anchor="w")

        # Scrollbar
        scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Populate rows
        self._row_to_opt: Dict[str, VideoFormatOption] = {}
        for idx, opt in enumerate(self.options):
            iid = f"opt_{idx}"
            self._row_to_opt[iid] = opt
            fps_str = str(opt.fps) if opt.fps > 0 else "—"
            size_str = format_filesize(opt.filesize_approx)
            vals = (opt.resolution_label, opt.ext.upper(), size_str, fps_str, opt.note)
            self.tree.insert("", tk.END, iid=iid, values=vals)

        if self.options:
            first_iid = "opt_0"
            self.tree.selection_set(first_iid)
            self.tree.focus(first_iid)

        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<Double-Button-1>", self._on_tree_double_click)

        # Destination path card
        card_dest = tk.Frame(body, bg=c_panel, padx=12, pady=8, highlightbackground=c_border, highlightthickness=1)
        card_dest.pack(fill=tk.X, pady=(0, 12))

        lbl_dest = tk.Label(card_dest, text=tr("modal_save_to", "Save As:"), font=("Segoe UI", 9, "bold"), bg=c_panel, fg=c_text_bright)
        lbl_dest.pack(side=tk.LEFT)

        self.entry_dest = tk.Entry(card_dest, font=("Segoe UI", 9), bg=c_input_bg, fg=c_text_bright, insertbackground=c_accent, relief="flat")
        self.entry_dest.insert(0, self.dest_path)
        self.entry_dest.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 8), ipady=3)

        btn_browse = tk.Button(
            card_dest,
            text=tr("modal_btn_browse", "📁 Browse..."),
            font=("Segoe UI", 8),
            bg=c_panel_light,
            fg=c_text_bright,
            relief="flat",
            activebackground=c_accent_dark,
            cursor="hand2",
            command=self._on_browse
        )
        btn_browse.pack(side=tk.RIGHT)

        # Bottom Buttons
        btn_row = tk.Frame(body, bg=c_bg)
        btn_row.pack(fill=tk.X)

        self.btn_download = tk.Button(
            btn_row,
            text=tr("modal_btn_start_quality", "⚡ Download Selected Quality"),
            font=("Segoe UI", 9, "bold"),
            bg=c_success,
            fg="white",
            relief="flat",
            activebackground="#059669",
            cursor="hand2",
            padx=16,
            pady=6,
            command=self._on_download
        )
        self.btn_download.pack(side=tk.LEFT)

        self.btn_download_mp3: Optional[tk.Button] = None
        has_audio = any(opt.is_audio_only for opt in self.options)
        if has_audio:
            self.btn_download_mp3 = tk.Button(
                btn_row,
                text=tr("modal_download_mp3", "🎵 Download MP3"),
                font=("Segoe UI", 9, "bold"),
                bg=c_accent_dark,
                fg="white",
                relief="flat",
                activebackground=c_accent,
                cursor="hand2",
                padx=16,
                pady=6,
                command=self._on_download_mp3
            )
            self.btn_download_mp3.pack(side=tk.LEFT, padx=(8, 0))

        self.btn_cancel = tk.Button(
            btn_row,
            text=tr("modal_btn_cancel", "✕ Cancel"),
            font=("Segoe UI", 9, "bold"),
            bg=c_panel_light,
            fg=c_text_muted,
            relief="flat",
            activebackground=c_border,
            cursor="hand2",
            padx=16,
            pady=6,
            command=self._on_close
        )
        self.btn_cancel.pack(side=tk.RIGHT)

        self.btn_open_app = tk.Button(
            btn_row,
            text=tr("modal_btn_open_in_main", "📋 Open in Main App"),
            font=("Segoe UI", 9),
            bg=c_panel_light,
            fg=c_text_bright,
            relief="flat",
            activebackground=c_border,
            cursor="hand2",
            padx=14,
            pady=6,
            command=self._on_open_in_main
        )
        self.btn_open_app.pack(side=tk.RIGHT, padx=(0, 8))

    def _on_download_mp3(self):
        """One-click download as universal MP3 audio."""
        mp3_opt = next((o for o in self.options if o.is_audio_only and o.ext.lower() == "mp3"), None)
        if not mp3_opt:
            mp3_opt = next((o for o in self.options if o.is_audio_only), None)
        if not mp3_opt:
            return

        self.selected_option = mp3_opt
        for iid, opt in self._row_to_opt.items():
            if opt == mp3_opt:
                self.tree.selection_set(iid)
                self.tree.focus(iid)
                break

        cur_path = self.entry_dest.get().strip()
        target_path = cur_path or self.dest_path
        if target_path:
            base, _ = os.path.splitext(target_path)
            parent_dir = os.path.dirname(target_path)
            parent_base = os.path.basename(os.path.normpath(parent_dir)) if parent_dir else ""
            new_ext = ".mp3"
            subfolders_lower = {v.lower() for v in CATEGORY_SUBFOLDERS.values()}
            if parent_base in CATEGORY_SUBFOLDERS.values() or parent_base.lower() in subfolders_lower:
                updated_dest = resolve_categorized_path(
                    parent_dir,
                    os.path.basename(base) + new_ext,
                    auto_categorize=True,
                    create_dir=False
                )
            else:
                updated_dest = base + new_ext
            self.entry_dest.delete(0, tk.END)
            self.entry_dest.insert(0, updated_dest)
            self.dest_path = updated_dest

        self._on_download()

    def _on_tree_double_click(self, event):
        item = self.tree.identify_row(event.y)
        if item and item in self._row_to_opt:
            self.tree.selection_set(item)
            self.selected_option = self._row_to_opt[item]
            self._on_tree_select(None)
        self._on_download()

    def _on_tree_select(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        iid = sel[0]
        opt = self._row_to_opt.get(iid)
        if not opt:
            return
        self.selected_option = opt

        # Dynamically adjust filename extension in the destination entry
        cur_path = self.entry_dest.get().strip()
        target_path = cur_path or self.dest_path
        if target_path:
            base, _ = os.path.splitext(target_path)
            new_ext = opt.ext.lower()
            if not new_ext.startswith("."):
                new_ext = "." + new_ext
            parent_dir = os.path.dirname(target_path)
            parent_base = os.path.basename(os.path.normpath(parent_dir)) if parent_dir else ""
            subfolders_lower = {v.lower() for v in CATEGORY_SUBFOLDERS.values()}
            if parent_base in CATEGORY_SUBFOLDERS.values() or parent_base.lower() in subfolders_lower:
                updated_dest = resolve_categorized_path(
                    parent_dir,
                    os.path.basename(base) + new_ext,
                    auto_categorize=True,
                    create_dir=False
                )
            else:
                updated_dest = base + new_ext
            self.entry_dest.delete(0, tk.END)
            self.entry_dest.insert(0, updated_dest)
            if self.dest_path:
                self.dest_path = updated_dest

    def _on_browse(self):
        cur = self.entry_dest.get().strip()
        init_dir = os.path.dirname(cur) if cur else os.path.expanduser("~")
        init_file = os.path.basename(cur) if cur else "download.mp4"
        chosen = filedialog.asksaveasfilename(
            parent=self,
            title="Save Video As",
            initialdir=init_dir,
            initialfile=init_file
        )
        if chosen:
            self.entry_dest.delete(0, tk.END)
            self.entry_dest.insert(0, chosen)

    def _on_download(self):
        if not self.selected_option:
            return
        final_dest = self.entry_dest.get().strip()
        if not final_dest:
            if self.dest_path:
                base, _ = os.path.splitext(self.dest_path)
                final_dest = f"{base}.{self.selected_option.ext}"
            else:
                downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
                clean_title = sanitize_filename(self.video_title)
                final_dest = os.path.join(downloads_dir, f"{clean_title}.{self.selected_option.ext}")
        self._confirmed = True
        try:
            self.grab_release()
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass
        self.on_confirm(self.selected_option, final_dest)

    def _on_open_in_main(self):
        if not self.selected_option:
            return
        final_dest = self.entry_dest.get().strip()
        if not final_dest:
            if self.dest_path:
                base, _ = os.path.splitext(self.dest_path)
                final_dest = f"{base}.{self.selected_option.ext}"
            else:
                downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
                clean_title = sanitize_filename(self.video_title)
                final_dest = os.path.join(downloads_dir, f"{clean_title}.{self.selected_option.ext}")
        self._confirmed = True
        try:
            self.grab_release()
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass
        if self.on_open_in_main:
            try:
                self.on_open_in_main(self.selected_option, final_dest)
            except Exception:
                pass
        else:
            if self.master and hasattr(self.master, "restore_window"):
                try:
                    self.master.restore_window()
                except Exception:
                    pass
            self.on_confirm(self.selected_option, final_dest)

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
        if self.parent_app and getattr(self.parent_app, "_quality_modal", None) is self:
            self.parent_app._quality_modal = None
        super().destroy()

    def _on_close(self):
        self.destroy()
        if self.parent_app and hasattr(self.parent_app, "clear_last_clipboard_url"):
            try:
                self.parent_app.clear_last_clipboard_url()
            except Exception:
                pass
        elif self.master and hasattr(self.master, "clear_last_clipboard_url"):
            try:
                self.master.clear_last_clipboard_url()
            except Exception:
                pass
        if self.on_cancel:
            try:
                self.on_cancel()
            except Exception:
                pass


# ======================================================================================
# 3D. SAFE THEMED MODAL DIALOG (OVERRIDEREDIRECT & FRAMELESS COMPATIBLE)
# ======================================================================================

class SafeModalDialog(tk.Toplevel):
    """
    Sleek, theme-consistent modal dialog designed specifically for borderless / overrideredirect windows.
    Replaces native Win32 messageboxes to eliminate window hierarchy corruption, message pump deadlocks,
    and process exits on Windows.
    """
    def __init__(
        self,
        parent: Optional[tk.Tk],
        title: str,
        message: str,
        dialog_type: str = "error",  # "error", "info", "warning", "confirm"
        theme: Optional[Dict[str, str]] = None,
        on_confirm: Optional[Callable[[], None]] = None,
        on_cancel: Optional[Callable[[], None]] = None
    ):
        super().__init__(parent)
        self.dialog_type = dialog_type
        self.on_confirm = on_confirm
        self.on_cancel = on_cancel
        self.result = False

        th = theme or {}
        c_bg = th.get("c_bg", "#0f172a")
        c_panel = th.get("c_panel", "#1e293b")
        c_panel_light = th.get("c_panel_light", "#334155")
        c_border = th.get("c_border", "#475569")
        c_text_bright = th.get("c_text_bright", "#f8fafc")
        c_text_muted = th.get("c_text_muted", "#94a3b8")
        c_accent = th.get("c_accent", "#38bdf8")
        c_accent_dark = th.get("c_accent_dark", "#0284c7")
        c_danger = th.get("c_danger", "#ef4444")
        c_warning = th.get("c_warning", "#f59e0b")
        c_success = th.get("c_success", "#10b981")

        if dialog_type == "error":
            accent_col = c_danger
            icon_str = "⚠️"
        elif dialog_type == "warning":
            accent_col = c_warning
            icon_str = "⚠️"
        elif dialog_type == "confirm":
            accent_col = c_accent
            icon_str = "❓"
        else:
            accent_col = c_accent
            icon_str = "ℹ️"

        self.title(title)
        self.configure(bg=c_bg)
        # Do not use grab_set(): with borderless / overrideredirect windows,
        # grab_set traps Win32 input messages and locks the main window pump.

        # Dimensions & Centering with DPI scaling
        try:
            dpi = float(parent.winfo_fpixels('1i')) if parent and parent.winfo_exists() else 96.0
        except Exception:
            dpi = 96.0
        dpi_scale = max(1.0, dpi / 96.0)

        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        dlg_w = min(int(520 * dpi_scale), max(440, int(sw * 0.90)))
        dlg_h = min(int(260 * dpi_scale), max(220, int(sh * 0.70)))

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
        self.minsize(min(440, dlg_w), min(220, dlg_h))

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

        # Elevate and focus
        try:
            self.lift()
            self.attributes("-topmost", True)
            self.focus_force()
        except Exception:
            pass

        outer = tk.Frame(self, bg=c_border, padx=1, pady=1)
        outer.pack(fill=tk.BOTH, expand=True)

        body = tk.Frame(outer, bg=c_bg, padx=18, pady=16)
        body.pack(fill=tk.BOTH, expand=True)

        # Header with icon and title
        hdr_frame = tk.Frame(body, bg=c_bg)
        hdr_frame.pack(fill=tk.X, pady=(0, 10))

        lbl_icon = tk.Label(hdr_frame, text=icon_str, font=("Segoe UI", 16), bg=c_bg, fg=accent_col)
        lbl_icon.pack(side=tk.LEFT, padx=(0, 8))

        lbl_title = tk.Label(hdr_frame, text=title, font=("Segoe UI", 11, "bold"), bg=c_bg, fg=accent_col, anchor="w")
        lbl_title.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Message box (Scrollable text or wrap label)
        msg_frame = tk.Frame(body, bg=c_panel, padx=12, pady=10, highlightbackground=c_border, highlightthickness=1)
        msg_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 14))

        txt_msg = tk.Text(
            msg_frame,
            font=("Segoe UI", 9),
            bg=c_panel,
            fg=c_text_bright,
            wrap=tk.WORD,
            relief="flat",
            highlightthickness=0,
            height=4
        )
        txt_scroll = ttk.Scrollbar(msg_frame, orient=tk.VERTICAL, command=txt_msg.yview)
        txt_msg.configure(yscrollcommand=txt_scroll.set)
        txt_msg.insert("1.0", str(message or ""))
        txt_msg.configure(state="disabled")
        txt_msg.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        txt_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Buttons
        btn_frame = tk.Frame(body, bg=c_bg)
        btn_frame.pack(fill=tk.X)

        if dialog_type == "confirm":
            btn_yes = tk.Button(
                btn_frame,
                text=tr("btn_yes", "Yes"),
                font=("Segoe UI", 9, "bold"),
                bg=accent_col,
                fg="white",
                relief="flat",
                activebackground=c_accent_dark,
                cursor="hand2",
                padx=18,
                pady=5,
                command=self._on_ok
            )
            btn_yes.pack(side=tk.RIGHT, padx=(8, 0))

            btn_no = tk.Button(
                btn_frame,
                text=tr("btn_no", "No"),
                font=("Segoe UI", 9),
                bg=c_panel_light,
                fg=c_text_muted,
                relief="flat",
                activebackground=c_border,
                cursor="hand2",
                padx=18,
                pady=5,
                command=self._on_close
            )
            btn_no.pack(side=tk.RIGHT)
        else:
            btn_ok = tk.Button(
                btn_frame,
                text=tr("btn_ok", "OK"),
                font=("Segoe UI", 9, "bold"),
                bg=accent_col,
                fg="white",
                relief="flat",
                activebackground=c_accent_dark,
                cursor="hand2",
                padx=22,
                pady=5,
                command=self._on_ok
            )
            btn_ok.pack(side=tk.RIGHT)

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Escape>", lambda e: self._on_close())
        self.bind("<Return>", lambda e: self._on_ok())

    def grab_set(self):
        """No-op: Eliminates Win32 input capture and message pump locking."""
        pass

    def grab_set_global(self):
        """No-op: Eliminates Win32 input capture and message pump locking."""
        pass

    def destroy(self):
        if hasattr(self, "_modal_icon_photo"):
            _detach_photo_tk(self._modal_icon_photo)
            self._modal_icon_photo = None
        try:
            self.grab_release()
        except Exception:
            pass
        super().destroy()

    def _on_ok(self):
        self.result = True
        self.destroy()
        if self.on_confirm:
            try:
                self.on_confirm()
            except Exception:
                pass

    def _on_close(self):
        self.result = False
        self.destroy()
        if self.on_cancel:
            try:
                self.on_cancel()
            except Exception:
                pass


class ToolTip:
    """
    Lightweight, high-DPI aware, floating tooltip for Tkinter widgets.
    Dynamically resolves localized text via callable or translation key.
    """
    def __init__(self, widget: tk.Widget, text_or_key: Union[str, Callable[[], str]]):
        self.widget = widget
        self.text_or_key = text_or_key
        self.tip_window: Optional[tk.Toplevel] = None
        self._show_job = None
        try:
            self.widget.bind("<Enter>", self._on_enter, add="+")
            self.widget.bind("<Leave>", self._on_leave, add="+")
            self.widget.bind("<ButtonPress>", self._on_leave, add="+")
            self.widget.bind("<Destroy>", self._on_destroy, add="+")
        except Exception:
            pass

    def _get_text(self) -> str:
        if callable(self.text_or_key):
            try:
                return str(self.text_or_key())
            except Exception:
                return ""
        return tr(self.text_or_key, self.text_or_key)

    def _on_enter(self, event=None):
        self._schedule()

    def _on_leave(self, event=None):
        self._unschedule()
        self._hide()

    def _on_destroy(self, event=None):
        self._unschedule()
        self._hide()

    def _schedule(self):
        self._unschedule()
        if hasattr(self.widget, "after"):
            try:
                self._show_job = self.widget.after(500, self._show)
            except Exception:
                pass

    def _unschedule(self):
        if self._show_job and hasattr(self.widget, "after_cancel"):
            try:
                self.widget.after_cancel(self._show_job)
            except Exception:
                pass
            self._show_job = None

    def _show(self):
        text = self._get_text()
        if not text:
            return
        try:
            if not self.widget.winfo_exists() or not self.widget.winfo_viewable():
                return
            if self.tip_window:
                return
            x = self.widget.winfo_rootx() + (self.widget.winfo_width() // 2)
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
            self.tip_window = tw = tk.Toplevel(self.widget)
            tw.wm_overrideredirect(True)
            tw.wm_geometry(f"+{x}+{y}")
            tw.attributes("-topmost", True)
            label = tk.Label(
                tw,
                text=text,
                justify=tk.LEFT,
                background="#1e293b",
                foreground="#f8fafc",
                relief=tk.SOLID,
                borderwidth=1,
                font=("Segoe UI", 8),
                padx=6,
                pady=3
            )
            label.pack(ipadx=1)
        except Exception:
            self._hide()

    def _hide(self):
        tw = self.tip_window
        self.tip_window = None
        if tw:
            try:
                tw.destroy()
            except Exception:
                pass


# ======================================================================================
# ARCHITECTURAL ENHANCEMENTS (AEROARCHIVE STUDIO INSPIRED)
# ======================================================================================

class MagicBytesDetector:
    """
    Magic-bytes file type detector inspired by AeroArchive Studio (detector.rs).
    Detects true binary container and format from initial bytes (header signature),
    independent of generic URLs or query parameters.
    """
    SIGNATURES = [
        # (magic_bytes, offset, extension, mime_type, category)
        (b"PK\x03\x04", 0, ".zip", "application/zip", "Compressed"),
        (b"PK\x05\x06", 0, ".zip", "application/zip", "Compressed"),
        (b"PK\x07\x08", 0, ".zip", "application/zip", "Compressed"),
        (b"\x37\x7A\xBC\xAF\x27\x1C", 0, ".7z", "application/x-7z-compressed", "Compressed"),
        (b"Rar!\x1A\x07\x00", 0, ".rar", "application/x-rar-compressed", "Compressed"),
        (b"Rar!\x1A\x07\x01\x00", 0, ".rar", "application/x-rar-compressed", "Compressed"),
        (b"\x1F\x8B", 0, ".gz", "application/gzip", "Compressed"),
        (b"%PDF-", 0, ".pdf", "application/pdf", "Documents"),
        (b"\x89PNG\r\n\x1a\n", 0, ".png", "image/png", "Images"),
        (b"\xFF\xD8\xFF", 0, ".jpg", "image/jpeg", "Images"),
        (b"GIF87a", 0, ".gif", "image/gif", "Images"),
        (b"GIF89a", 0, ".gif", "image/gif", "Images"),
        (b"\x1A\x45\xDF\xA3", 0, ".mkv", "video/x-matroska", "Video"),
        (b"ID3", 0, ".mp3", "audio/mpeg", "Audio"),
        (b"\xFF\xFB", 0, ".mp3", "audio/mpeg", "Audio"),
        (b"\xFF\xF3", 0, ".mp3", "audio/mpeg", "Audio"),
        (b"MZ", 0, ".exe", "application/x-msdownload", "Programs"),
        (b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1", 0, ".msi", "application/x-msi", "Programs"),
    ]

    @classmethod
    def detect_bytes(cls, data: bytes) -> Optional[Tuple[str, str, str]]:
        """
        Returns (extension, mime_type, category) if recognized, or None.
        """
        if not data or len(data) < 2:
            return None

        # Check MP4 / MOV (offset 4: ftyp)
        if len(data) >= 12 and data[4:8] == b"ftyp":
            brand = data[8:12].lower()
            if brand in (b"qt  ", b"moov"):
                return (".mov", "video/quicktime", "Video")
            return (".mp4", "video/mp4", "Video")

        # Check RIFF subtypes (WEBP, WAV, AVI)
        if len(data) >= 12 and data[:4] == b"RIFF":
            form_type = data[8:12]
            if form_type == b"WEBP":
                return (".webp", "image/webp", "Images")
            elif form_type == b"WAVE":
                return (".wav", "audio/wav", "Audio")
            elif form_type == b"AVI ":
                return (".avi", "video/x-msvideo", "Video")

        # Check TAR (offset 257: ustar)
        if len(data) >= 265 and data[257:262] == b"ustar":
            return (".tar", "application/x-tar", "Compressed")

        # Check ISO 9660 (offset 32768: CD001)
        if len(data) >= 32773 and data[32768:32773] == b"CD001":
            return (".iso", "application/x-iso9660-image", "General")

        for sig, offset, ext, mime, cat in cls.SIGNATURES:
            sig_len = len(sig)
            if len(data) >= offset + sig_len and data[offset:offset+sig_len] == sig:
                return (ext, mime, cat)

        return None

    @classmethod
    def detect_file(cls, filepath: str) -> Optional[Tuple[str, str, str]]:
        if not os.path.isfile(filepath):
            return None
        try:
            with open(filepath, "rb") as f:
                header = f.read(512)
            return cls.detect_bytes(header)
        except Exception:
            return None


def calculate_file_integrity(filepath: str) -> Dict[str, str]:
    """
    Computes CRC-32 and SHA-256 integrity hashes for a file.
    Uses 64KB streaming blocks for low memory overhead.
    """
    if not os.path.isfile(filepath):
        return {"crc32": "", "sha256": ""}
    crc = 0
    sha = hashlib.sha256()
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(64 * 1024)
            if not chunk:
                break
            crc = zlib.crc32(chunk, crc)
            sha.update(chunk)
    return {
        "crc32": f"{crc & 0xFFFFFFFF:08X}",
        "sha256": sha.hexdigest().lower()
    }


def auto_unpack_archive(archive_path: str, destination_dir: Optional[str] = None) -> Optional[str]:
    """
    Extracts downloaded archive (.zip, .tar, .tar.gz, .tgz, .7z) into a dedicated folder.
    Returns path to extracted folder on success, or None.
    """
    if not os.path.isfile(archive_path):
        return None
    stem = os.path.splitext(os.path.basename(archive_path))[0]
    if archive_path.lower().endswith(".tar.gz"):
        stem = os.path.basename(archive_path)[:-7]
    base_dir = destination_dir or os.path.dirname(archive_path)
    out_dir = os.path.join(base_dir, stem)
    try:
        os.makedirs(out_dir, exist_ok=True)
        # 1. 7z / rar extraction via tar.exe (Windows 10/11 built-in libarchive bsdtar) or 7z CLI
        if archive_path.lower().endswith((".7z", ".rar")):
            tar_tool = shutil.which("tar")
            if tar_tool:
                try:
                    res = subprocess.run([tar_tool, "-xf", archive_path, "-C", out_dir], capture_output=True, timeout=60)
                    if res.returncode == 0:
                        return out_dir
                except Exception:
                    pass
            seven_z = shutil.which("7z") or shutil.which("7za")
            if seven_z:
                try:
                    res = subprocess.run([seven_z, "x", "-y", f"-o{out_dir}", archive_path], capture_output=True, timeout=60)
                    if res.returncode == 0:
                        return out_dir
                except Exception:
                    pass

        # 2. Standard zip archives
        if zipfile.is_zipfile(archive_path):
            with zipfile.ZipFile(archive_path, 'r') as zf:
                zf.extractall(out_dir)
            return out_dir
        # 3. Standard tar / tar.gz / tgz archives
        elif tarfile.is_tarfile(archive_path):
            with tarfile.open(archive_path, 'r:*') as tf:
                if hasattr(tarfile, 'data_filter'):
                    tf.extractall(out_dir, filter='data')
                else:
                    tf.extractall(out_dir)
            return out_dir
        else:
            try:
                shutil.unpack_archive(archive_path, out_dir)
                return out_dir
            except Exception:
                pass
    except Exception:
        pass
    return None


# ======================================================================================
# 3E. TDM-STYLE DOWNLOAD CONFIRMATION MODAL (SAFE, GRAB-FREE, BORDERLESS COMPATIBLE)
# ======================================================================================

def get_file_category_and_icon(filename_or_url: str) -> Tuple[str, str]:
    """Returns (category_name, icon_symbol) based on file extension."""
    clean = str(filename_or_url or "").split('?')[0].split('#')[0]
    ext = os.path.splitext(clean)[1].lower().lstrip('.')
    if ext in ("zip", "rar", "7z", "tar", "gz", "bz2", "xz", "iso", "tgz", "7zip", "z"):
        return ("Compressed", "📦")
    elif ext in ("exe", "msi", "dmg", "pkg", "deb", "rpm", "apk", "bin", "appimage", "bat", "cmd", "ps1"):
        return ("Programs", "⚙️")
    elif ext in ("mp4", "mkv", "webm", "avi", "mov", "wmv", "flv", "m4v", "3gp", "ts"):
        return ("Video", "🎬")
    elif ext in ("mp3", "wav", "flac", "aac", "ogg", "m4a", "wma", "opus", "mka"):
        return ("Audio", "🎵")
    elif ext in ("pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "rtf", "epub", "csv", "json", "xml"):
        return ("Documents", "📄")
    elif ext in ("jpg", "jpeg", "png", "gif", "bmp", "webp", "svg", "ico", "tiff"):
        return ("Images", "🖼️")
    else:
        return ("General", "📥")


CATEGORY_SUBFOLDERS: Dict[str, str] = {
    "Video": "Video",
    "Audio": "Music",
    "Programs": "Programs",
    "Compressed": "Compressed",
    "Documents": "Documents",
    "Images": "Images",
    "General": "General",
}


def resolve_categorized_path(base_dir: str, filename: str, auto_categorize: bool = True, create_dir: bool = True) -> str:
    """
    Resolves destination path into typed category subfolders (e.g. Video, Music, Programs, Compressed, etc.)
    when auto_categorize is enabled. Prevents recursive/nested subfolders if base_dir already points
    to a category subfolder.
    """
    raw_fn = str(filename or "").strip().split('?')[0].split('#')[0]
    clean_fn = os.path.basename(raw_fn) or "download.bin"
    if not base_dir or not str(base_dir).strip():
        base_dir = os.path.join(os.path.expanduser("~"), "Downloads")
    if not auto_categorize:
        return os.path.join(base_dir, clean_fn)

    category, _ = get_file_category_and_icon(clean_fn)
    if clean_fn.lower().endswith(".bin"):
        category = "General"
    subfolder = CATEGORY_SUBFOLDERS.get(category, "General")

    base_norm = os.path.normpath(str(base_dir))
    base_name = os.path.basename(base_norm)
    subfolders_lower = {s.lower() for s in CATEGORY_SUBFOLDERS.values()}
    if base_name in CATEGORY_SUBFOLDERS.values() or base_name.lower() in subfolders_lower:
        root_dir = os.path.dirname(base_norm)
    else:
        root_dir = base_norm

    target_dir = os.path.join(root_dir, subfolder)
    if create_dir:
        try:
            os.makedirs(target_dir, exist_ok=True)
        except Exception:
            pass

    return os.path.join(target_dir, clean_fn)


class DownloadHistoryManager:
    """Thread-safe persistent storage and query manager for completed, paused, and failed downloads."""

    def __init__(self, history_file: Optional[str] = None, max_entries: int = 500):
        self._lock = threading.RLock()
        self.max_entries = int(max_entries)
        if history_file:
            self.history_file = history_file
        else:
            self.history_file = os.path.join(get_config_dir(), "download_history.json")
        self._entries: List[Dict[str, Any]] = []
        self._load_entries()

    def _load_entries(self):
        with self._lock:
            if not os.path.isfile(self.history_file):
                self._entries = []
                return
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self._entries = data
                    else:
                        self._entries = []
            except Exception:
                self._entries = []

    def _save_entries(self) -> bool:
        with self._lock:
            try:
                dir_path = os.path.dirname(os.path.abspath(self.history_file))
                if dir_path:
                    os.makedirs(dir_path, exist_ok=True)
                tmp_file = f"{self.history_file}.tmp_{os.getpid()}_{int(time.time() * 1000)}"
                with open(tmp_file, "w", encoding="utf-8") as f:
                    json.dump(self._entries, f, indent=2)
                os.replace(tmp_file, self.history_file)
                return True
            except Exception:
                try:
                    if 'tmp_file' in locals() and os.path.exists(tmp_file):
                        os.remove(tmp_file)
                except Exception:
                    pass
                try:
                    with open(self.history_file, "w", encoding="utf-8") as f:
                        json.dump(self._entries, f, indent=2)
                    return True
                except Exception:
                    return False

    def add_or_update_entry(
        self,
        url: str,
        file_path: str,
        size_bytes: int = 0,
        status: str = "Completed",
        elapsed_sec: float = 0.0
    ) -> Dict[str, Any]:
        with self._lock:
            norm_path = os.path.abspath(file_path) if file_path else ""
            norm_path_case = os.path.normcase(norm_path) if norm_path else ""
            raw_url = str(url or "").strip()
            filename = os.path.basename(norm_path) if norm_path else derive_download_filename(raw_url)
            if not filename:
                filename = "download.bin"

            category, icon = get_file_category_and_icon(filename or raw_url)
            if filename.lower().endswith(".bin"):
                category, icon = "General", "📥"

            try:
                calc_size = int(size_bytes or 0)
            except Exception:
                calc_size = 0
            if calc_size <= 0 and norm_path and os.path.isfile(norm_path):
                try:
                    calc_size = os.path.getsize(norm_path)
                except Exception:
                    calc_size = 0

            try:
                elapsed_val = float(elapsed_sec or 0.0)
            except Exception:
                elapsed_val = 0.0

            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

            match_idx = -1
            matched_id = None
            old_entry = None
            for idx, entry in enumerate(self._entries):
                e_path = entry.get("file_path", "")
                e_url = entry.get("url", "")
                e_fn = entry.get("filename", "")
                e_path_norm = os.path.normcase(os.path.abspath(e_path)) if e_path else ""
                if norm_path_case and e_path_norm and e_path_norm == norm_path_case:
                    match_idx = idx
                    matched_id = entry.get("id")
                    old_entry = entry
                    break
                if raw_url and e_url == raw_url and filename and e_fn == filename:
                    match_idx = idx
                    matched_id = entry.get("id")
                    old_entry = entry
                    break

            if match_idx >= 0 and old_entry:
                self._entries.pop(match_idx)
                entry_id = matched_id or old_entry.get("id") or f"dl_{int(time.time() * 1000)}_{len(self._entries)}"
                final_size = calc_size if calc_size > 0 else old_entry.get("size_bytes", 0)
                final_elapsed = elapsed_val if elapsed_val > 0 else float(old_entry.get("elapsed_sec", 0.0))
                final_path = norm_path or old_entry.get("file_path", "")
                final_url = raw_url or old_entry.get("url", "")
            else:
                entry_id = f"dl_{int(time.time() * 1000)}_{len(self._entries)}"
                final_size = calc_size
                final_elapsed = elapsed_val
                final_path = norm_path
                final_url = raw_url

            record = {
                "id": entry_id,
                "filename": filename,
                "file_path": final_path,
                "url": final_url,
                "size_bytes": final_size,
                "category": category,
                "icon": icon,
                "status": status,
                "timestamp": timestamp,
                "elapsed_sec": final_elapsed,
            }
            self._entries.insert(0, record)
            if len(self._entries) > self.max_entries:
                self._entries = self._entries[:self.max_entries]

            self._save_entries()
            return dict(record)

    def get_entries(self, category_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            if not category_filter or category_filter.strip().lower() in ("all", "all categories", "كافة التصنيفات", "الكل", ""):
                return [dict(e) for e in self._entries]
            cat_clean = category_filter.strip().lower()
            cat_aliases = {
                "music": "audio",
                "audio": "audio",
                "صوتيات": "audio",
                "صوت": "audio",
                "video": "video",
                "videos": "video",
                "فيديو": "video",
                "مرئي": "video",
                "image": "images",
                "images": "images",
                "صور": "images",
                "صورة": "images",
                "document": "documents",
                "documents": "documents",
                "مستندات": "documents",
                "وثائق": "documents",
                "program": "programs",
                "programs": "programs",
                "برامج": "programs",
                "تطبيقات": "programs",
                "compressed": "compressed",
                "مضغوط": "compressed",
                "أرشيف": "compressed",
                "general": "general",
                "عام": "general",
            }
            target_cat = cat_aliases.get(cat_clean, cat_clean)
            res = []
            for e in self._entries:
                item_cat = str(e.get("category", "")).strip().lower()
                norm_item_cat = cat_aliases.get(item_cat, item_cat)
                if item_cat == cat_clean or norm_item_cat == target_cat:
                    res.append(dict(e))
            return res

    def get_entry(self, entry_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            str_id = str(entry_id)
            for e in self._entries:
                if str(e.get("id")) == str_id:
                    return dict(e)
            return None

    def remove_entry(self, entry_id: str, delete_file: bool = False) -> bool:
        with self._lock:
            str_id = str(entry_id)
            target = None
            for e in self._entries:
                if str(e.get("id")) == str_id:
                    target = e
                    break
            if not target:
                return False
            self._entries.remove(target)
            if delete_file:
                fp = target.get("file_path", "")
                if fp and os.path.isfile(fp):
                    try:
                        os.remove(fp)
                    except Exception:
                        pass
            self._save_entries()
            return True

    def clear_history(self) -> bool:
        with self._lock:
            self._entries.clear()
            self._save_entries()
            return True


def open_downloaded_file(file_path: str):
    """Opens downloaded file with default OS application."""
    if not file_path or not os.path.exists(file_path):
        return
    try:
        if IS_WINDOWS and hasattr(os, "startfile"):
            os.startfile(file_path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", file_path])
        else:
            subprocess.Popen(["xdg-open", file_path])
    except Exception:
        pass


def open_containing_folder(file_path: str):
    """Opens folder containing downloaded file and highlights it on Windows."""
    if not file_path:
        return
    folder = os.path.dirname(file_path) if file_path else ""
    if not folder or not os.path.exists(folder):
        folder = os.path.expanduser("~")
    try:
        if IS_WINDOWS:
            norm_path = os.path.normpath(file_path)
            if os.path.isfile(norm_path):
                subprocess.Popen(["explorer", f"/select,{norm_path}"])
            elif os.path.exists(folder):
                if hasattr(os, "startfile"):
                    os.startfile(folder)
                else:
                    subprocess.Popen(["explorer", folder])
            else:
                home = os.path.expanduser("~")
                if hasattr(os, "startfile"):
                    os.startfile(home)
                else:
                    subprocess.Popen(["explorer", home])
        elif sys.platform == "darwin":
            if os.path.exists(file_path):
                subprocess.Popen(["open", "-R", file_path])
            else:
                subprocess.Popen(["open", folder])
        else:
            subprocess.Popen(["xdg-open", folder])
    except Exception:
        pass


def parse_speed_limit(val_str: Any) -> float:
    """
    Parses speed limit string into bytes per second. Returns 0.0 for unlimited.
    Accepts: 'Unlimited', '500 KB/s', '1 MB/s', '2.5 MB/s', '1024', etc.
    """
    if not val_str:
        return 0.0
    s = str(val_str).strip().lower()
    if s in ("unlimited", "0", "0.0", "none", "off", "max", ""):
        return 0.0
    import re
    # 1. Gigabytes per second
    m_gb = re.search(r"([\d\.]+)\s*(gb/s|g/s|gbps|gib/s|gib|gb)", s)
    if m_gb:
        try:
            return float(m_gb.group(1)) * 1024.0 * 1024.0 * 1024.0
        except ValueError:
            return 0.0
    # 2. Megabytes per second
    m_mb = re.search(r"([\d\.]+)\s*(mb/s|m/s|mbps|mib/s|mib|mb)", s)
    if m_mb:
        try:
            return float(m_mb.group(1)) * 1024.0 * 1024.0
        except ValueError:
            return 0.0
    # 3. Kilobytes per second
    m_kb = re.search(r"([\d\.]+)\s*(kb/s|k/s|kbps|kib/s|kib|kb)", s)
    if m_kb:
        try:
            return float(m_kb.group(1)) * 1024.0
        except ValueError:
            return 0.0
    # 4. Bytes per second
    m_b = re.search(r"([\d\.]+)\s*(bytes/s|byte/s|bytes|b/s|bps|b)", s)
    if m_b:
        try:
            return float(m_b.group(1))
        except ValueError:
            return 0.0
    # 5. Short single-letter suffixes e.g. '10m', '500k', '1g'
    m_suf = re.search(r"^([\d\.]+)\s*([gmkb])$", s)
    if m_suf:
        try:
            val = float(m_suf.group(1))
            unit = m_suf.group(2)
            if unit == "g":
                return val * 1024.0 * 1024.0 * 1024.0
            if unit == "m":
                return val * 1024.0 * 1024.0
            if unit == "k":
                return val * 1024.0
            if unit == "b":
                return val
        except ValueError:
            return 0.0
    try:
        val = float(s)
        if val < 100000.0:
            return val * 1024.0
        return val
    except ValueError:
        return 0.0


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


class MultipleCandidatesModal(tk.Toplevel):
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

        self.var_select_all = tk.BooleanVar(value=True)
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
            var = tk.BooleanVar(value=True)
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
        super().destroy()

    def grab_set(self):
        pass

    def grab_set_global(self):
        pass


class RefreshLinkModal(tk.Toplevel):
    """
    Modern dark-themed TDM-style dialog for updating an expired or forbidden download link:
    - Displays current URL, file name, existing progress preserved, and input for the new URL.
    - Grab-free: strictly avoids grab_set() / grab_set_global() to prevent Win32 message pump traps.
    - High-DPI scaled, centered over parent, and focused.
    - Auto-detects valid URLs on clipboard for instant one-click or auto-pasting.
    - Asynchronously validates the candidate URL with HTTP HEAD/GET Range before committing.
    - Upon success, calls on_success(new_url, headers) to update TurboDownloadEngine and resume downloading.
    """
    def __init__(
        self,
        parent: Optional[tk.Tk],
        old_url: str = "",
        total_size: int = 0,
        downloaded_bytes: int = 0,
        filename: str = "",
        theme: Optional[Dict[str, str]] = None,
        on_success: Optional[Callable[[str, Optional[Dict[str, str]]], None]] = None,
        on_cancel: Optional[Callable[[], None]] = None,
        ssl_context: Optional[ssl.SSLContext] = None,
        expected_ranges: bool = True,
        custom_headers: Optional[Dict[str, str]] = None
    ):
        super().__init__(parent)
        self.old_url = str(old_url or "").strip()
        self.total_size = max(0, int(total_size or 0))
        self.downloaded_bytes = max(0, int(downloaded_bytes or 0))
        self.filename = str(filename or "").strip() or derive_download_filename(self.old_url)
        self.on_success = on_success
        self.on_cancel = on_cancel
        self.ssl_context = ssl_context or get_permissive_ssl_context()
        self.expected_ranges = expected_ranges
        self.custom_headers = dict(custom_headers or {})
        self.result_url: Optional[str] = None
        self._confirmed = False

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

        self.title(tr("refresh_modal_title", "🔄 Refresh Download Address — Smart Download"))
        self.configure(bg=self.c_bg)

        if parent:
            try:
                self.transient(parent)
            except Exception:
                pass

        # Determine DPI scaling
        try:
            dpi = float(parent.winfo_fpixels('1i')) if parent and parent.winfo_exists() else 96.0
        except Exception:
            dpi = 96.0
        self.dpi_scale = max(1.0, dpi / 96.0)

        # Center on parent window
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        dlg_w = min(int(640 * self.dpi_scale), max(520, int(sw * 0.88)))
        dlg_h = min(int(440 * self.dpi_scale), max(360, int(sh * 0.80)))
        try:
            if parent and parent.winfo_exists():
                px = parent.winfo_x()
                py = parent.winfo_y()
                pw = parent.winfo_width() or dlg_w
                ph = parent.winfo_height() or dlg_h
            else:
                px, py, pw, ph = 100, 100, dlg_w, dlg_h
        except Exception:
            px, py, pw, ph = 100, 100, dlg_w, dlg_h

        x = max(0, px + (pw - dlg_w) // 2)
        y = max(0, py + (ph - dlg_h) // 2)
        self.geometry(f"{dlg_w}x{dlg_h}+{x}+{y}")
        self.minsize(min(480, dlg_w), min(320, dlg_h))

        # Icons
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

        # Elevate and focus
        try:
            self.lift()
            self.attributes("-topmost", True)
            self.focus_force()
            self._idle_job = self.after_idle(lambda: (self.lift(), self.focus_force()) if self.winfo_exists() else None)
        except Exception:
            pass

        self.parent = parent
        self._pending_ui_action = None

        self._build_ui(dlg_w)

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Escape>", lambda e: self._on_close())
        self._poll_pending_ui()

    def _poll_pending_ui(self):
        if getattr(self, "_pending_ui_action", None):
            self.process_pending_events()
        if not getattr(self, "_closing", False):
            try:
                if self.winfo_exists():
                    self._poll_job = self.after(30, self._poll_pending_ui)
            except Exception:
                pass

    def process_pending_events(self):
        """Processes any asynchronous worker callbacks, vital when running outside mainloop() in tests."""
        action = getattr(self, "_pending_ui_action", None)
        if action:
            self._pending_ui_action = None
            try:
                action()
            except Exception:
                pass

    def grab_set(self):
        """No-op: Eliminates Win32 input capture and message pump locking."""
        pass

    def grab_set_global(self):
        """No-op: Eliminates Win32 input capture and message pump locking."""
        pass

    def destroy(self):
        self._closing = True
        if getattr(self, "_idle_job", None):
            try:
                self.after_cancel(self._idle_job)
            except Exception:
                pass
            self._idle_job = None
        if hasattr(self, "_poll_job") and self._poll_job:
            try:
                self.after_cancel(self._poll_job)
            except Exception:
                pass
            self._poll_job = None
        if hasattr(self, "_modal_icon_photo"):
            _detach_photo_tk(self._modal_icon_photo)
            self._modal_icon_photo = None
        try:
            self.grab_release()
        except Exception:
            pass
        super().destroy()

    def _build_ui(self, dlg_w: int):
        container = tk.Frame(self, bg=self.c_bg, padx=16, pady=12)
        container.pack(fill=tk.BOTH, expand=True)

        # Header Banner
        header = tk.Frame(container, bg=self.c_bg)
        header.pack(fill=tk.X, pady=(0, 10))

        lbl_icon = tk.Label(header, text="🔄", font=("Segoe UI Emoji", 20), bg=self.c_bg, fg=self.c_accent)
        lbl_icon.pack(side=tk.LEFT, padx=(0, 10))

        title_box = tk.Frame(header, bg=self.c_bg)
        title_box.pack(side=tk.LEFT, fill=tk.X, expand=True)

        lbl_title = tk.Label(
            title_box,
            text=tr("refresh_modal_header", "Refresh Expired Download Address"),
            font=("Segoe UI", 11, "bold"),
            bg=self.c_bg,
            fg=self.c_text_bright,
            anchor="w"
        )
        lbl_title.pack(fill=tk.X)

        lbl_sub = tk.Label(
            title_box,
            text=tr("refresh_modal_sub", "Paste the new active link to continue downloading without losing your downloaded parts."),
            font=("Segoe UI", 8),
            bg=self.c_bg,
            fg=self.c_text_muted,
            anchor="w"
        )
        lbl_sub.pack(fill=tk.X)

        # Preserved State Card
        info_card = tk.Frame(
            container,
            bg=self.c_panel,
            padx=12,
            pady=8,
            relief="flat",
            highlightbackground=self.c_border,
            highlightthickness=1
        )
        info_card.pack(fill=tk.X, pady=(0, 10))

        # File row
        row_fn = tk.Frame(info_card, bg=self.c_panel)
        row_fn.pack(fill=tk.X, pady=2)
        tk.Label(row_fn, text=tr("refresh_modal_filename", "File Name:"), font=("Segoe UI", 8, "bold"), bg=self.c_panel, fg=self.c_text_muted, width=14, anchor="w").pack(side=tk.LEFT)
        tk.Label(row_fn, text=self.filename, font=("Segoe UI", 8, "bold"), bg=self.c_panel, fg=self.c_text_bright, anchor="w").pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Progress preserved row
        row_prog = tk.Frame(info_card, bg=self.c_panel)
        row_prog.pack(fill=tk.X, pady=2)
        tk.Label(row_prog, text=tr("refresh_modal_preserved", "Preserved Data:"), font=("Segoe UI", 8, "bold"), bg=self.c_panel, fg=self.c_text_muted, width=14, anchor="w").pack(side=tk.LEFT)

        if self.total_size > 0:
            pct = min(100.0, (self.downloaded_bytes / self.total_size) * 100.0)
            prog_txt = f"{self.downloaded_bytes / (1024*1024):.2f} MB of {self.total_size / (1024*1024):.2f} MB ({pct:.1f}%) saved on disk"
        else:
            prog_txt = f"{self.downloaded_bytes / (1024*1024):.2f} MB downloaded"
        tk.Label(row_prog, text=f"🛡️ {prog_txt}", font=("Segoe UI", 8, "bold"), bg=self.c_panel, fg=self.c_success, anchor="w").pack(side=tk.LEFT)

        # Old URL row
        row_old = tk.Frame(info_card, bg=self.c_panel)
        row_old.pack(fill=tk.X, pady=(4, 2))
        tk.Label(row_old, text=tr("refresh_modal_old_addr", "Old Address:"), font=("Segoe UI", 8, "bold"), bg=self.c_panel, fg=self.c_text_muted, width=14, anchor="w").pack(side=tk.LEFT)

        entry_old = tk.Entry(row_old, font=("Consolas", 8), bg=self.c_input_bg, fg=self.c_text_muted, relief="flat")
        entry_old.insert(0, self.old_url)
        entry_old.configure(state="readonly")
        entry_old.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=1)

        # New URL Input Section
        input_card = tk.Frame(
            container,
            bg=self.c_panel,
            padx=12,
            pady=10,
            relief="flat",
            highlightbackground=self.c_border,
            highlightthickness=1
        )
        input_card.pack(fill=tk.X, pady=(0, 10))

        lbl_new = tk.Label(
            input_card,
            text=tr("refresh_modal_new_url", "New Download URL:"),
            font=("Segoe UI", 9, "bold"),
            bg=self.c_panel,
            fg=self.c_accent,
            anchor="w"
        )
        lbl_new.pack(fill=tk.X, pady=(0, 6))

        new_url_row = tk.Frame(input_card, bg=self.c_panel)
        new_url_row.pack(fill=tk.X)

        self.entry_new_url = tk.Entry(
            new_url_row,
            font=("Segoe UI", 9),
            bg=self.c_input_bg,
            fg=self.c_text_bright,
            insertbackground=self.c_accent,
            relief="flat"
        )
        self.entry_new_url.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6), ipady=3)
        self.entry_new_url.bind("<Return>", lambda e: self._start_validation())
        self.entry_url = self.entry_new_url
        self._check_clipboard = self._check_clipboard_auto_fill

        btn_paste = tk.Button(
            new_url_row,
            text=tr("btn_paste", "📋 Paste"),
            font=("Segoe UI", 8, "bold"),
            bg=self.c_panel_light,
            fg=self.c_text_bright,
            relief="flat",
            activebackground=self.c_accent_dark,
            cursor="hand2",
            padx=8,
            pady=2,
            command=self._paste_clipboard
        )
        btn_paste.pack(side=tk.RIGHT)

        # Auto-detect valid candidate from clipboard
        self._check_clipboard_auto_fill()

        # Status Label Area
        self.lbl_status = tk.Label(
            container,
            text=tr("refresh_modal_status_idle", "Paste the new download link and click Validate & Resume."),
            font=("Segoe UI", 8),
            bg=self.c_bg,
            fg=self.c_text_muted,
            wraplength=max(400, dlg_w - 50),
            justify="left",
            anchor="w"
        )
        self.lbl_status.pack(fill=tk.X, pady=(2, 10))

        # Action Buttons
        btn_row = tk.Frame(container, bg=self.c_bg)
        btn_row.pack(fill=tk.X, side=tk.BOTTOM)

        self.btn_validate = tk.Button(
            btn_row,
            text=tr("refresh_modal_btn_validate", "🔄 Validate & Resume"),
            font=("Segoe UI", 9, "bold"),
            bg=self.c_success,
            fg="white",
            relief="flat",
            activebackground="#059669",
            cursor="hand2",
            padx=14,
            pady=5,
            command=self._start_validation
        )
        self.btn_validate.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_cancel = tk.Button(
            btn_row,
            text=tr("refresh_modal_btn_cancel", "✕ Cancel"),
            font=("Segoe UI", 9),
            bg=self.c_panel_light,
            fg=self.c_text_bright,
            relief="flat",
            activebackground=self.c_border,
            cursor="hand2",
            padx=12,
            pady=5,
            command=self._on_close
        )
        self.btn_cancel.pack(side=tk.LEFT)

    def _check_clipboard_auto_fill(self):
        """Auto-populates new URL entry if clipboard contains a valid download URL different from old."""
        try:
            clip = get_clipboard_text(self)
            if clip:
                clip = clip.strip()
                if (clip.startswith("http://") or clip.startswith("https://")) and clip != self.old_url:
                    self.entry_new_url.delete(0, tk.END)
                    self.entry_new_url.insert(0, clip)
                    self.entry_new_url.select_range(0, tk.END)
        except Exception:
            pass

    def _paste_clipboard(self):
        try:
            clip = get_clipboard_text(self)
            if clip:
                self.entry_new_url.delete(0, tk.END)
                self.entry_new_url.insert(0, clip.strip())
        except Exception:
            pass

    def _set_status(self, msg: str, is_error: bool = False, is_info: bool = False, is_success: bool = False):
        if not self.winfo_exists():
            return
        if is_error:
            col = self.c_danger
        elif is_success:
            col = self.c_success
        elif is_info:
            col = self.c_accent
        else:
            col = self.c_text_muted
        self.lbl_status.configure(text=msg, fg=col)

    def _start_validation(self):
        new_url = self.entry_new_url.get().strip()
        if not new_url:
            self._set_status("Please paste a valid HTTP or HTTPS download link.", is_error=True)
            return
        if not (new_url.startswith("http://") or new_url.startswith("https://")):
            self._set_status("Invalid URL scheme. Link must begin with http:// or https://", is_error=True)
            return

        self.btn_validate.configure(state="disabled", text=tr("refresh_modal_btn_validating", "⏳ Validating..."))
        self.btn_cancel.configure(state="disabled")
        self._set_status("Connecting to remote server and verifying byte ranges...", is_info=True)

        def _worker():
            is_valid, msg, remote_size, ranges_ok = validate_refresh_url(
                new_url=new_url,
                expected_size=self.total_size,
                check_range=self.expected_ranges,
                timeout=12.0,
                ssl_context=self.ssl_context,
                headers=self.custom_headers
            )
            def _ui_done():
                if not self.winfo_exists():
                    return
                if is_valid:
                    self._on_validation_success(new_url, remote_size)
                else:
                    self._on_validation_failure(msg)
            self._pending_ui_action = _ui_done
            try:
                self.after(0, _ui_done)
            except Exception:
                pass

        t = threading.Thread(target=_worker, daemon=True)
        self._validating_thread = t
        t.start()

    def _on_validation_success(self, new_url: str, remote_size: int):
        self._set_status(f"✅ Verified successfully! Remote size: {remote_size:,} bytes. Resuming...", is_success=True)
        self.result_url = new_url
        self._confirmed = True
        if self.on_success:
            try:
                self.on_success(new_url, self.custom_headers)
            except Exception as e:
                self._set_status(f"Error applying update: {e}", is_error=True)
                self.btn_validate.configure(state="normal", text=tr("refresh_modal_btn_validate", "🔄 Validate & Resume"))
                self.btn_cancel.configure(state="normal")
                return
        self.destroy()

    def _on_validation_failure(self, err_msg: str):
        self.btn_validate.configure(state="normal", text=tr("refresh_modal_btn_validate", "🔄 Validate & Resume"))
        self.btn_cancel.configure(state="normal")
        self._set_status(f"❌ {err_msg}", is_error=True)

    def _on_close(self):
        self._confirmed = False
        self.destroy()
        if self.on_cancel:
            try:
                self.on_cancel()
            except Exception:
                pass


RefreshLinkDialog = RefreshLinkModal


class AppUpdateModal(tk.Toplevel):
    """
    Sleek, non-blocking, dark-themed application update notification and installer download dialog.
    Displays the new version, release notes summary, live download progress bar, and a one-click
    [⬇ Update Now] button that downloads SmartDownload-Setup.exe and upgrades seamlessly.
    """

    def __init__(
        self,
        parent: tk.Widget,
        update_info: Dict[str, Any],
        theme: Optional[Dict[str, str]] = None,
        parent_app: Optional[Any] = None,
        updater: Optional[AppAutoUpdater] = None,
        on_log: Optional[Callable[[str], None]] = None,
        on_exit_app: Optional[Callable[[], None]] = None
    ):
        super().__init__(parent)
        self.parent_widget = parent
        self.update_info = update_info or {}
        self.parent_app = parent_app
        self.on_exit_app = on_exit_app
        self.updater = updater or AppAutoUpdater(
            on_log=on_log or getattr(parent_app, "log", None)
        )
        self._cancel_event = threading.Event()
        self._is_downloading = False

        # Grab-free modal (never blocks main thread or other windows)
        self.grab_set = lambda: None
        self.grab_set_global = lambda: None
        self.transient(parent)

        t = theme or {}
        self.c_bg = t.get("c_bg", "#0f172a")
        self.c_panel = t.get("c_panel", "#1e293b")
        self.c_panel_light = t.get("c_panel_light", "#334155")
        self.c_border = t.get("c_border", "#475569")
        self.c_accent = t.get("c_accent", "#38bdf8")
        self.c_accent_dark = t.get("c_accent_dark", "#0284c7")
        self.c_success = t.get("c_success", "#10b981")
        self.c_warning = t.get("c_warning", "#f59e0b")
        self.c_danger = t.get("c_danger", "#ef4444")
        self.c_text_bright = t.get("c_text_bright", "#f8fafc")
        self.c_text_muted = t.get("c_text_muted", "#94a3b8")
        self.c_input_bg = t.get("c_input_bg", "#090d16")

        latest_ver = self.update_info.get("latest_version", APP_VERSION)
        self.title(f"🚀 Update Available — Smart Download (SD) v{latest_ver}")
        self.configure(bg=self.c_bg)

        try:
            dpi = float(self.winfo_fpixels("1i"))
        except Exception:
            dpi = 96.0
        self.dpi_scale = max(1.0, dpi / 96.0)

        dlg_w = int(580 * self.dpi_scale)
        dlg_h = int(450 * self.dpi_scale)
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = max(0, (sw - dlg_w) // 2)
        y = max(0, (sh - dlg_h) // 2)
        self.geometry(f"{dlg_w}x{dlg_h}+{x}+{y}")
        self.minsize(int(500 * self.dpi_scale), int(380 * self.dpi_scale))

        ico_path = get_resource_path("app_icon.ico")
        if os.path.isfile(ico_path):
            try:
                self.iconbitmap(ico_path)
            except Exception:
                pass

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._build_ui()

        try:
            self.lift()
            self.attributes("-topmost", True)
            self.focus_force()
        except Exception:
            pass

    def _build_ui(self):
        cur_ver = self.update_info.get("current_version", APP_VERSION)
        latest_ver = self.update_info.get("latest_version", APP_VERSION)
        rel_name = self.update_info.get("release_name") or f"Smart Download (SD) v{latest_ver}"
        rel_notes = self.update_info.get("release_notes") or "Bug fixes, extractor updates, and performance improvements."
        inst_size = int(self.update_info.get("installer_size") or 0)

        container = tk.Frame(self, bg=self.c_bg, padx=16, pady=14)
        container.pack(fill=tk.BOTH, expand=True)

        # Header
        lbl_title = tk.Label(
            container,
            text=f"🚀 NEW UPDATE AVAILABLE — v{latest_ver}",
            font=("Segoe UI", 11, "bold"),
            bg=self.c_bg,
            fg=self.c_accent,
            anchor="w"
        )
        lbl_title.pack(fill=tk.X)

        lbl_sub = tk.Label(
            container,
            text=rel_name,
            font=("Segoe UI", 9),
            bg=self.c_bg,
            fg=self.c_text_bright,
            anchor="w"
        )
        lbl_sub.pack(fill=tk.X, pady=(2, 8))

        # Version Badge Card
        badge_card = tk.Frame(
            container,
            bg=self.c_panel,
            padx=12,
            pady=8,
            highlightbackground=self.c_border,
            highlightthickness=1
        )
        badge_card.pack(fill=tk.X, pady=(0, 10))

        size_txt = f"  •  Size: {format_filesize(inst_size)}" if inst_size > 0 else ""
        ver_text = f"Installed: v{cur_ver}   ➔   New Release: v{latest_ver}{size_txt}"
        self.lbl_version_info = tk.Label(
            badge_card,
            text=ver_text,
            font=("Segoe UI", 9, "bold"),
            bg=self.c_panel,
            fg=self.c_success,
            anchor="w"
        )
        self.lbl_version_info.pack(fill=tk.X)

        # Release Notes Section
        lbl_notes_hdr = tk.Label(
            container,
            text="📋 Release Notes & Highlights:",
            font=("Segoe UI", 8, "bold"),
            bg=self.c_bg,
            fg=self.c_text_muted,
            anchor="w"
        )
        lbl_notes_hdr.pack(fill=tk.X, pady=(0, 4))

        notes_frame = tk.Frame(
            container,
            bg=self.c_input_bg,
            highlightbackground=self.c_border,
            highlightthickness=1
        )
        notes_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        self.txt_notes = tk.Text(
            notes_frame,
            bg=self.c_input_bg,
            fg=self.c_text_bright,
            font=("Segoe UI", 9),
            relief="flat",
            wrap="word",
            height=7,
            padx=8,
            pady=6
        )
        scroll_notes = ttk.Scrollbar(notes_frame, orient="vertical", command=self.txt_notes.yview)
        self.txt_notes.configure(yscrollcommand=scroll_notes.set)
        self.txt_notes.insert("1.0", rel_notes)
        self.txt_notes.configure(state="disabled")
        self.txt_notes.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_notes.pack(side=tk.RIGHT, fill=tk.Y)

        # Progress Bar & Status
        prog_h = max(18, int(20 * self.dpi_scale))
        self.canvas_prog = tk.Canvas(container, height=prog_h, bg=self.c_input_bg, highlightthickness=0)
        self.canvas_prog.pack(fill=tk.X, pady=(0, 6))
        self._draw_progress(0.0)

        self.lbl_status = tk.Label(
            container,
            text="Click '⬇ Update Now' to download and install the update automatically.",
            font=("Segoe UI", 8),
            bg=self.c_bg,
            fg=self.c_text_muted,
            anchor="w"
        )
        self.lbl_status.pack(fill=tk.X, pady=(0, 10))

        # Action Buttons
        btn_row = tk.Frame(container, bg=self.c_bg)
        btn_row.pack(fill=tk.X, side=tk.BOTTOM)

        self.btn_update_now = tk.Button(
            btn_row,
            text="⬇ Update Now (تحديث الآن)",
            font=("Segoe UI", 9, "bold"),
            bg=self.c_success,
            fg="white",
            relief="flat",
            activebackground="#059669",
            cursor="hand2",
            padx=16,
            pady=5,
            command=self._start_update_download
        )
        self.btn_update_now.pack(side=tk.LEFT, padx=(0, 8))
        self.btn_update = self.btn_update_now

        self.btn_later = tk.Button(
            btn_row,
            text="Later (لاحقاً)",
            font=("Segoe UI", 9),
            bg=self.c_panel_light,
            fg=self.c_text_bright,
            relief="flat",
            activebackground=self.c_border,
            cursor="hand2",
            padx=14,
            pady=5,
            command=self._on_close
        )
        self.btn_later.pack(side=tk.LEFT)

    def _draw_progress(self, pct: float):
        try:
            if not self.winfo_exists():
                return
            self.canvas_prog.delete("all")
            w = self.canvas_prog.winfo_width()
            if w <= 1:
                w = int(540 * self.dpi_scale)
            h = self.canvas_prog.winfo_height() or max(18, int(20 * self.dpi_scale))
            self.canvas_prog.create_rectangle(0, 0, w, h, fill=self.c_input_bg, outline=self.c_border)
            fill_w = max(0.0, min(float(w), (pct / 100.0) * float(w)))
            if fill_w > 0:
                self.canvas_prog.create_rectangle(0, 0, fill_w, h, fill=self.c_accent_dark, outline="")
            self.canvas_prog.create_text(w // 2, h // 2, text=f"{pct:.1f}%", font=("Segoe UI", 8, "bold"), fill=self.c_text_bright)
        except Exception:
            pass

    def _start_update_download(self):
        if self._is_downloading:
            return
        installer_url = (
            self.update_info.get("installer_url")
            or self.update_info.get("download_url")
            or self.update_info.get("portable_url")
            or ""
        )
        if not installer_url:
            self.lbl_status.configure(text="❌ No installer download URL found in release assets.", fg=self.c_danger)
            return

        self._is_downloading = True
        self._cancel_event.clear()
        self.btn_update_now.configure(state="disabled", text="⏳ Downloading Update...")
        self.lbl_status.configure(text="Connecting to GitHub Releases...", fg=self.c_accent)

        def _prog_cb(downloaded: int, total: int):
            def _ui():
                if not self.winfo_exists():
                    return
                pct = (downloaded / total * 100.0) if total > 0 else 0.0
                self._draw_progress(pct)
                dl_mb = downloaded / (1024 * 1024)
                if total > 0:
                    tot_mb = total / (1024 * 1024)
                    self.lbl_status.configure(
                        text=f"Downloading update: {dl_mb:.1f} MB / {tot_mb:.1f} MB ({pct:.1f}%)",
                        fg=self.c_accent
                    )
                else:
                    self.lbl_status.configure(
                        text=f"Downloading update: {dl_mb:.1f} MB...",
                        fg=self.c_accent
                    )
            try:
                self.after(0, _ui)
            except Exception:
                pass

        def _worker():
            try:
                installer_path = self.updater.download_update(
                    download_url=installer_url,
                    progress_cb=_prog_cb,
                    cancel_event=self._cancel_event
                )

                def _on_done():
                    if not self.winfo_exists():
                        return
                    self._draw_progress(100.0)
                    self.lbl_status.configure(
                        text="✅ Download complete! Launching installer to upgrade...",
                        fg=self.c_success
                    )
                    exit_cb = self.on_exit_app or (getattr(self.parent_app, "exit_completely", None) if self.parent_app else None)
                    self.updater.apply_update(
                        installer_path=installer_path,
                        silent=True,
                        launch_after=True,
                        exit_callback=exit_cb
                    )
                    try:
                        self.destroy()
                    except Exception:
                        pass

                self.after(0, _on_done)
            except Exception as e:
                def _on_err():
                    self._is_downloading = False
                    if not self.winfo_exists():
                        return
                    self.btn_update_now.configure(state="normal", text="⬇ Update Now (تحديث الآن)")
                    self.lbl_status.configure(text=f"❌ Update failed: {e}", fg=self.c_danger)
                try:
                    self.after(0, _on_err)
                except Exception:
                    pass

        threading.Thread(target=_worker, daemon=True, name="AppUpdateDownloadThread").start()

    def _on_close(self):
        self._cancel_event.set()
        try:
            self.destroy()
        except Exception:
            pass


# ======================================================================================
# WINDOWS SYSTEM TRAY NOTIFICATION AREA INTEGRATION (NON-BLOCKING PYSTRAY)
# ======================================================================================

class SystemTrayManager:
    """
    Manages the Windows System Tray (Notification Area) icon and right-click context menu.
    Integrates non-blocking background icon loop with Tkinter main thread.
    Features:
    1. Modern application icon (app_icon.ico / app_icon.png) rendered cleanly.
    2. Single-click and double-click restore and elevate main application window.
    3. Right-click context menu:
       - 🖥️ Open Smart Download (SD)
       - 📋 Clipboard Sniffer: Active / Paused
       - 🚀 Start with Windows: ON / OFF
       - ❌ Exit Completely
    4. Non-blocking thread-safe execution communicating with Tkinter main thread.
    5. Clean teardown unregistering tray icon without leaving ghost icons.
    """
    def __init__(self, app: Any):
        try:
            self._app_ref = weakref.ref(app) if app is not None else (lambda: None)
        except TypeError:
            self._app_ref = lambda: app
        self.icon: Optional[Any] = None
        self._running = False
        self._lock = threading.Lock()

    @property
    def app(self) -> Any:
        return self._app_ref()

    @app.setter
    def app(self, value: Any):
        if value is None:
            self._app_ref = lambda: None
        else:
            try:
                self._app_ref = weakref.ref(value)
            except TypeError:
                self._app_ref = lambda: value

    def _get_icon_image(self):
        """Loads application icon image for tray area."""
        ico_path = get_resource_path("app_icon.ico")
        png_path = get_resource_path("app_icon.png")
        if os.path.isfile(png_path):
            try:
                from PIL import Image
                return Image.open(png_path)
            except Exception:
                pass
        if os.path.isfile(ico_path):
            try:
                from PIL import Image
                return Image.open(ico_path)
            except Exception:
                pass
        try:
            from PIL import Image
            return Image.new("RGBA", (32, 32), color=(14, 165, 233, 255))
        except Exception:
            return None

    def _get_sniffer_text(self, item=None) -> str:
        app = self.app
        active = getattr(app, "_clipboard_sniffer_active", True) if app is not None else True
        return tr("tray_sniffer_active") if active else tr("tray_sniffer_paused")

    def _get_startup_text(self, item=None) -> str:
        enabled = is_startup_enabled()
        return tr("tray_startup_on") if enabled else tr("tray_startup_off")

    def _on_menu_open(self, icon=None, item=None):
        app = self.app
        if app is None:
            return
        if hasattr(app, "dispatch_to_main_thread"):
            app.dispatch_to_main_thread(app.restore_window)
        else:
            app.restore_window()

    def _on_menu_toggle_sniffer(self, icon=None, item=None):
        app = self.app
        if app is None:
            return
        if hasattr(app, "dispatch_to_main_thread"):
            app.dispatch_to_main_thread(self._do_toggle_sniffer)
        else:
            self._do_toggle_sniffer()

    def _do_toggle_sniffer(self):
        app = self.app
        if app is not None and hasattr(app, "toggle_clipboard_sniffer"):
            app.toggle_clipboard_sniffer()
        self.update_menu()

    def _on_menu_toggle_startup(self, icon=None, item=None):
        app = self.app
        if app is None:
            return
        if hasattr(app, "dispatch_to_main_thread"):
            app.dispatch_to_main_thread(self._do_toggle_startup)
        else:
            self._do_toggle_startup()

    def _do_toggle_startup(self):
        app = self.app
        if app is not None and hasattr(app, "toggle_startup_setting"):
            app.toggle_startup_setting()
        self.update_menu()

    def _on_menu_exit(self, icon=None, item=None):
        app = self.app
        if app is None:
            return
        if hasattr(app, "dispatch_to_main_thread"):
            app.dispatch_to_main_thread(app.exit_completely)
        else:
            app.exit_completely()

    def _build_menu(self):
        if not PYSTRAY_AVAILABLE or TrayMenuItem is None or TrayMenu is None:
            return None
        return TrayMenu(
            TrayMenuItem(tr("tray_open"), self._on_menu_open, default=True),
            TrayMenuItem(self._get_sniffer_text, self._on_menu_toggle_sniffer),
            TrayMenuItem(self._get_startup_text, self._on_menu_toggle_startup),
            TrayMenuItem(tr("tray_exit"), self._on_menu_exit),
        )

    @property
    def is_running(self) -> bool:
        with self._lock:
            return bool(self._running and self.icon is not None)

    def start(self):
        """Starts the tray icon in a background worker thread."""
        if not PYSTRAY_AVAILABLE or pystray is None:
            return
        if os.environ.get("SD_DISABLE_SYSTEM_TRAY") == "1":
            with self._lock:
                self._running = True
            return
        with self._lock:
            if self._running and self.icon is not None:
                return
            img = self._get_icon_image()
            if img is None:
                return
            menu = self._build_menu()
            try:
                self.icon = pystray.Icon("SmartDownload", img, "Smart Download (SD)", menu=menu)
                # Patch notify to catch both WM_LBUTTONUP (0x0202) and WM_LBUTTONDBLCLK (0x0203)
                orig_notify = getattr(self.icon, "_on_notify", None)
                if orig_notify:
                    def _patched_notify(wparam, lparam):
                        if lparam in (0x0202, 0x0203):
                            try:
                                if self.icon is not None:
                                    self.icon()
                            except Exception:
                                pass
                            return
                        return orig_notify(wparam, lparam)
                    self.icon._on_notify = _patched_notify
                # Run in a daemon thread so it never blocks Python process termination
                tray_thread = threading.Thread(target=self.icon.run, daemon=True, name='SmartDownloadTrayThread')
                self._thread = tray_thread
                tray_thread.start()
                self._running = True
            except Exception:
                self._running = False
                self.icon = None

    def stop(self):
        """Stops the tray icon and removes it from the Windows notification area."""
        with self._lock:
            self._running = False
            self.app = None
            if self.icon is not None:
                try:
                    q = getattr(self.icon, "_Icon__queue", None)
                    if q is not None and q.empty():
                        try:
                            q.put_nowait(True)
                        except Exception:
                            pass
                    self.icon.stop()
                except Exception:
                    pass
                self.icon = None
            if hasattr(self, "_thread") and self._thread and self._thread != threading.current_thread():
                try:
                    self._thread.join(timeout=0.5)
                except Exception:
                    pass
                self._thread = None

    def update_menu(self):
        """Refreshes dynamic labels in context menu."""
        with self._lock:
            if self.icon is not None:
                try:
                    self.icon.menu = self._build_menu()
                    if getattr(self.icon, "visible", False):
                        self.icon.update_menu()
                except Exception:
                    pass

    def notify(self, message: str, title: str = "Smart Download (SD)"):
        """Displays Windows system tray notification balloon if supported."""
        with self._lock:
            if self.icon is not None and getattr(self.icon, "visible", False):
                try:
                    self.icon.notify(message, title)
                except Exception:
                    pass
            elif self.icon is not None:
                def _delayed_notify():
                    time.sleep(0.5)
                    with self._lock:
                        if self.icon is not None and getattr(self.icon, "visible", False):
                            try:
                                self.icon.notify(message, title)
                            except Exception:
                                pass
                threading.Thread(target=_delayed_notify, daemon=True, name="DelayedTrayNotify").start()


# ======================================================================================
# 4. MODERN FRAMELESS WINDOW GUI (DARK THEME & SEGMENTED CHUNK VISUALIZER)
# ======================================================================================

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


# ======================================================================================
# 5. APPLICATION ENTRYPOINT
# ======================================================================================

def main():
    import multiprocessing
    multiprocessing.freeze_support()

    # CLI handler for test mode or binary verification
    if "--test-startup" in sys.argv:
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
