import os
import sys
import subprocess
import ast
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
SRC_DIR = os.path.join(BASE_DIR, "src", "smart_download")

res = subprocess.run(["git", "show", "HEAD:turbo_downloader.py"], capture_output=True, text=True, encoding="utf-8")
if res.returncode != 0:
    raise RuntimeError(f"git show failed: {res.stderr}")
source_lines = res.stdout.splitlines(True)

def get_slice(start_1indexed, end_1indexed):
    return "".join(source_lines[start_1indexed - 1 : end_1indexed])

def write_module(relative_path, content):
    full_path = os.path.join(SRC_DIR, relative_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)
    try:
        ast.parse(content, filename=relative_path)
        print(f"[OK] Wrote & validated syntax: {relative_path}")
    except SyntaxError as e:
        print(f"[ERROR] Syntax error in {relative_path}: {e}")
        raise

print("[*] Beginning lossless modular extraction from HEAD:turbo_downloader.py...")

# 1. src/smart_download/config.py
get_resource_path_code = '''def get_resource_path(relative_path: str) -> str:
    """Resolve absolute path for bundled assets in development or PyInstaller frozen bundle."""
    if hasattr(sys, "_MEIPASS"):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    direct = os.path.join(base_path, relative_path)
    if os.path.exists(direct):
        return direct
    in_assets = os.path.join(base_path, "assets", relative_path)
    if os.path.exists(in_assets):
        return in_assets
    curr = base_path
    for _ in range(3):
        cand = os.path.join(curr, "assets", relative_path)
        if os.path.exists(cand):
            return cand
        cand_direct = os.path.join(curr, relative_path)
        if os.path.exists(cand_direct):
            return cand_direct
        parent = os.path.dirname(curr)
        if parent == curr:
            break
        curr = parent
    return in_assets if os.path.exists(in_assets) else direct
'''

config_code = '''"""
Application configuration, paths, constants, and settings management for Smart Download.
"""
import os
import sys
import json
import shutil
import tempfile
from typing import Dict, Any, Optional

APP_NAME = "Smart Download"
APP_TITLE = "Smart Download (SD)"
APP_ID = "SmartDownload"
APP_VERSION = "2.0.0"
APP_AUTHOR = "Smart Download Team"
GITHUB_REPO_OWNER = "hozifa460"
GITHUB_REPO_NAME = "smart-download-sd"
DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

IS_WINDOWS = sys.platform.startswith("win")

# Dynamic chunking engine defaults
CHUNK_SIZE_KB = 1024
MAX_CONCURRENT_CHUNKS = 32
DEFAULT_CHUNKS = 8
MIN_CHUNK_BYTES = 512 * 1024
BUFFER_SIZE = 64 * 1024

''' + get_resource_path_code + "\n\n" + get_slice(176, 255) + "\n"

write_module("config.py", config_code)

# 2. Extract Locales: ar.json, en.json, locales/i18n.py
translations_code = get_slice(260, 895)
trans_scope = {}
exec(compile(translations_code, "<translations>", "exec"), trans_scope)
trans = trans_scope["TRANSLATIONS"]

locales_dir = os.path.join(SRC_DIR, "locales")
os.makedirs(locales_dir, exist_ok=True)

with open(os.path.join(locales_dir, "en.json"), "w", encoding="utf-8") as f:
    json.dump(trans.get("en", {}), f, ensure_ascii=False, indent=2)
print("[OK] Wrote locales/en.json")

with open(os.path.join(locales_dir, "ar.json"), "w", encoding="utf-8") as f:
    json.dump(trans.get("ar", {}), f, ensure_ascii=False, indent=2)
print("[OK] Wrote locales/ar.json")

i18n_code = '''"""
Internationalization and localization manager for Smart Download.
"""
import os
import sys
import json
from typing import Dict, List, Optional, Callable, Any

from ..config import get_setting, set_setting

_LOCALES_DIR = os.path.dirname(os.path.abspath(__file__))

def _load_locale(lang: str) -> Dict[str, str]:
    path = os.path.join(_LOCALES_DIR, f"{lang}.json")
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "en": _load_locale("en"),
    "ar": _load_locale("ar"),
}

''' + get_slice(898, 991) + "\n\n" + get_slice(994, 1004) + "\n"

write_module("locales/i18n.py", i18n_code)

locales_init = '''from .i18n import (
    LocalizationManager,
    tr,
    get_current_language,
    set_current_language,
    TRANSLATIONS,
)

__all__ = [
    "LocalizationManager",
    "tr",
    "get_current_language",
    "set_current_language",
    "TRANSLATIONS",
]
'''
write_module("locales/__init__.py", locales_init)

# 3. utils/
# 3.1 dpi.py
dpi_code = '''"""
Windows High-DPI awareness and work area metrics utilities.
"""
import sys
import ctypes
from typing import Tuple, Optional

from ..config import IS_WINDOWS

''' + get_slice(75, 110) + "\n\n" + get_slice(1997, 2015) + "\n"
write_module("utils/dpi.py", dpi_code)

# 3.2 clipboard.py
clip_code = '''"""
Cross-platform and Windows-optimized clipboard utilities.
"""
import sys
import subprocess
import ctypes
import time
from typing import Optional, Any

from ..config import IS_WINDOWS

''' + get_slice(1754, 1811) + "\n"
clip_fix_target = """        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32"""
clip_fix_replacement = """        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        user32.GetClipboardData.restype = wintypes.HANDLE
        user32.GetClipboardData.argtypes = [wintypes.UINT]
        kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalLock.restype = wintypes.LPVOID
        kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]"""
clip_code = clip_code.replace(clip_fix_target, clip_fix_replacement)
write_module("utils/clipboard.py", clip_code)

# 3.3 url_utils.py
url_code = '''"""
URL parsing, content-disposition extraction, downloadable validation, and filename helpers.
"""
import os
import re
import urllib.parse
import urllib.request
from typing import Optional, Dict, Tuple, List, Any

def _lazy_is_youtube_url(url: str) -> bool:
    try:
        from ..services.youtube_service import is_youtube_url
        return is_youtube_url(url)
    except Exception:
        return False

def _lazy_is_social_media_url(url: str) -> bool:
    try:
        from ..services.youtube_service import is_social_media_url
        return is_social_media_url(url)
    except Exception:
        return False

def _lazy_is_media_url(url: str) -> bool:
    try:
        from ..services.youtube_service import is_media_url
        return is_media_url(url)
    except Exception:
        return False

def _lazy_extract_media_platform(url: str) -> Optional[str]:
    try:
        from ..services.youtube_service import extract_media_platform
        return extract_media_platform(url)
    except Exception:
        return None

is_youtube_url = _lazy_is_youtube_url
is_social_media_url = _lazy_is_social_media_url
is_media_url = _lazy_is_media_url
extract_media_platform = _lazy_extract_media_platform

''' + get_slice(1473, 1751) + "\n\n" + get_slice(2018, 2041) + "\n\n" + get_slice(6606, 6667) + "\n"
write_module("utils/url_utils.py", url_code)

# 3.4 file_ops.py
file_ops_code = '''"""
File operations, magic bytes detection, integrity hashing, category determination, and archive unpacking.
"""
import os
import sys
import hashlib
import subprocess
import zipfile
import tarfile
import zlib
import shutil
from typing import Optional, Tuple, Dict, Any

from ..config import IS_WINDOWS

''' + get_slice(6109, 6336) + "\n\n" + get_slice(6557, 6603) + "\n"
write_module("utils/file_ops.py", file_ops_code)

# 3.5 tk_helpers.py
tk_helpers_code = '''"""
Tkinter widget and image reference decoupling and event queue drainage helpers.
"""
import sys
import gc
import weakref
import threading
import queue
import tkinter as tk
from tkinter import ttk
from typing import Any, Tuple, Callable

''' + get_slice(5082, 5260) + "\n"
write_module("utils/tk_helpers.py", tk_helpers_code)

# 3.6 utils/__init__.py
utils_init = '''from .dpi import enable_high_dpi_awareness, get_windows_work_area
from .clipboard import _win32_clipboard_get, get_clipboard_text
from .url_utils import (
    COMMON_DOWNLOAD_EXTENSIONS,
    WEB_SCRIPT_EXTENSIONS,
    is_downloadable_url,
    clean_download_filename,
    derive_download_filename,
    is_potential_html_url,
    parse_filename_from_cd_header,
    parse_speed_limit,
)
from .file_ops import (
    MagicBytesDetector,
    calculate_file_integrity,
    auto_unpack_archive,
    get_file_category_and_icon,
    CATEGORY_SUBFOLDERS,
    resolve_categorized_path,
    open_downloaded_file,
    open_containing_folder,
)
from .tk_helpers import _detach_photo_tk, _detach_widget_tk_refs, _drain_bg_tk_callbacks

__all__ = [
    "enable_high_dpi_awareness",
    "get_windows_work_area",
    "_win32_clipboard_get",
    "get_clipboard_text",
    "COMMON_DOWNLOAD_EXTENSIONS",
    "WEB_SCRIPT_EXTENSIONS",
    "is_downloadable_url",
    "clean_download_filename",
    "derive_download_filename",
    "is_potential_html_url",
    "parse_filename_from_cd_header",
    "parse_speed_limit",
    "MagicBytesDetector",
    "calculate_file_integrity",
    "auto_unpack_archive",
    "get_file_category_and_icon",
    "CATEGORY_SUBFOLDERS",
    "resolve_categorized_path",
    "open_downloaded_file",
    "open_containing_folder",
    "_detach_photo_tk",
    "_detach_widget_tk_refs",
    "_drain_bg_tk_callbacks",
]
'''
write_module("utils/__init__.py", utils_init)

# 4. core/
# 4.1 rate_limiter.py
rate_limiter_code = '''"""
Token bucket rate limiter for dynamic live download speed regulation.
"""
import time
import threading
from typing import Optional

''' + get_slice(1859, 1928) + "\n"
write_module("core/rate_limiter.py", rate_limiter_code)

# 4.2 chunk.py
chunk_code = '''"""
Download chunk state data class and permissive SSL context provider.
"""
import ssl
import threading
from dataclasses import dataclass, field
from typing import Optional

''' + get_slice(1935, 1994) + "\n"
write_module("core/chunk.py", chunk_code)

# 4.3 html_resolver.py
html_resolver_code = '''"""
HTML candidate discovery, web scraping parser, and redirect resolution.
"""
import os
import sys
import re
import ssl
import urllib.request
import urllib.parse
import urllib.error
from html.parser import HTMLParser
from typing import List, Dict, Optional, Tuple, Any

from .chunk import get_permissive_ssl_context
from ..utils.url_utils import (
    is_downloadable_url,
    derive_download_filename,
    is_potential_html_url,
    parse_filename_from_cd_header,
    COMMON_DOWNLOAD_EXTENSIONS,
)

''' + get_slice(2045, 2886) + "\n"
write_module("core/html_resolver.py", html_resolver_code)

# 4.4 engine.py
engine_code = '''"""
TurboDownloadEngine: Multi-threaded dynamic chunking, resume, assembly, and throttling download engine.
"""
import os
import sys
import time
import math
import urllib.request
import urllib.error
import urllib.parse
import threading
import ssl
import shutil
import tempfile
import json
from typing import List, Optional, Callable, Dict, Any, Union, Tuple

from ..config import (
    get_resource_path,
    get_setting,
    CHUNK_SIZE_KB,
    MAX_CONCURRENT_CHUNKS,
    DEFAULT_CHUNKS,
    MIN_CHUNK_BYTES,
    BUFFER_SIZE,
)
from .rate_limiter import TokenBucketRateLimiter
from .chunk import DownloadChunk, get_permissive_ssl_context
from .html_resolver import validate_refresh_url
from ..utils.url_utils import (
    is_downloadable_url,
    derive_download_filename,
    is_potential_html_url,
    parse_filename_from_cd_header,
)
from ..utils.file_ops import (
    calculate_file_integrity,
    auto_unpack_archive,
    MagicBytesDetector,
)

''' + get_slice(2893, 4044) + "\n"
write_module("core/engine.py", engine_code)

# 4.5 stream_coordinator.py
stream_coordinator_code = '''"""
StreamDownloadCoordinator: Orchestrates separate video/audio stream downloads and container multiplexing.
"""
import os
import sys
import time
import threading
import subprocess
import shutil
import ssl
from typing import Optional, Callable, Dict, Any, List

from .engine import TurboDownloadEngine
from .chunk import DownloadChunk
from ..config import IS_WINDOWS
from ..services.youtube_service import (
    YouTubeStreamInfo,
    MediaStreamInfo,
    YouTubeResolver,
    MediaResolver,
    has_ffmpeg,
    find_ffmpeg_bin,
    is_youtube_url,
)

''' + get_slice(4051, 4494) + "\n"
write_module("core/stream_coordinator.py", stream_coordinator_code)

# 4.6 history.py
history_code = '''"""
Download history SQLite persistence and management.
"""
import os
import sqlite3
import time
import threading
import json
from typing import List, Dict, Any, Optional

from ..config import get_config_dir
from ..utils.url_utils import derive_download_filename
from ..utils.file_ops import get_file_category_and_icon

''' + get_slice(6339, 6554) + "\n"
write_module("core/history.py", history_code)

# 4.7 core/__init__.py
core_init = '''from .rate_limiter import TokenBucketRateLimiter
from .chunk import DownloadChunk, get_permissive_ssl_context
from .html_resolver import (
    _HtmlCandidateExtractor,
    resolve_all_download_candidates,
    _HtmlLinkCandidateParser,
    resolve_real_download_url,
    validate_refresh_url,
)
from .engine import TurboDownloadEngine
from .stream_coordinator import StreamDownloadCoordinator
from .history import DownloadHistoryManager

__all__ = [
    "TokenBucketRateLimiter",
    "DownloadChunk",
    "get_permissive_ssl_context",
    "_HtmlCandidateExtractor",
    "resolve_all_download_candidates",
    "_HtmlLinkCandidateParser",
    "resolve_real_download_url",
    "validate_refresh_url",
    "TurboDownloadEngine",
    "StreamDownloadCoordinator",
    "DownloadHistoryManager",
]
'''
write_module("core/__init__.py", core_init)

# 5. services/
# 5.1 startup_service.py
startup_code = '''"""
Windows startup registry, Task Scheduler, and Startup shortcut management.
"""
import os
import sys
import subprocess
import shutil
from typing import Optional, Dict, Any, Tuple

from ..config import IS_WINDOWS

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
    except Exception:
        user32 = None
        kernel32 = None
else:
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
    user32 = None
    kernel32 = None

''' + get_slice(1088, 1466) + "\n"
startup_target = """    # Prioritize compiled standalone binary in dist/ directory or adjacent to script
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
    return f'"{py_exe}" "{script_path}"{flag}'"""

startup_replacement = """    # Prioritize compiled standalone binary in dist/ directory or adjacent to script
    base_dir = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() and isinstance(__file__, str) else os.getcwd()
    if os.path.basename(base_dir).lower() in ("services", "smart_download"):
        cand_root = os.path.abspath(os.path.join(base_dir, "..", "..", ".."))
        if os.path.isdir(cand_root):
            base_dir = cand_root
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
    script_path = os.path.abspath(os.path.join(base_dir, "turbo_downloader.py"))
    return f'"{py_exe}" "{script_path}"{flag}'"""

startup_code = startup_code.replace(startup_target, startup_replacement)
write_module("services/startup_service.py", startup_code)

# 5.2 single_instance.py
single_inst_code = '''"""
Single instance detection and IPC dispatch to running instance.
"""
import sys
import json
import urllib.request
import urllib.error
from typing import Optional

from .browser.bridge_server import DEFAULT_BRIDGE_PORT
from ..utils.url_utils import is_downloadable_url

''' + get_slice(1814, 1852) + "\n"
write_module("services/single_instance.py", single_inst_code)

# 5.3 browser/
# 5.3.1 bridge_server.py
res_bridge = subprocess.run(["git", "show", "HEAD:browser_bridge.py"], capture_output=True, text=True, encoding="utf-8")
write_module("services/browser/bridge_server.py", res_bridge.stdout)

# 5.3.2 native_host.py
res_native = subprocess.run(["git", "show", "HEAD:native_messaging_host.py"], capture_output=True, text=True, encoding="utf-8")
write_module("services/browser/native_host.py", res_native.stdout)

# 5.3.3 registry.py
res_reg = subprocess.run(["git", "show", "HEAD:register_browser.py"], capture_output=True, text=True, encoding="utf-8")
write_module("services/browser/registry.py", res_reg.stdout)

# 5.3.4 browser/__init__.py
browser_init = '''from .bridge_server import BrowserBridgeServer, DEFAULT_BRIDGE_PORT
from .native_host import (
    get_binary_stdin,
    get_binary_stdout,
    read_message,
    send_message,
    handle_payload,
    run_host,
)
from .registry import (
    register_native_host,
    unregister_native_host,
    check_and_register_browser,
    register_browser_extensions,
    unregister_browser_extensions,
    is_registered,
    get_status,
)

handle_native_message = handle_payload
run_native_messaging_host = run_host

__all__ = [
    "BrowserBridgeServer",
    "DEFAULT_BRIDGE_PORT",
    "get_binary_stdin",
    "get_binary_stdout",
    "read_message",
    "send_message",
    "handle_payload",
    "run_host",
    "handle_native_message",
    "run_native_messaging_host",
    "register_native_host",
    "unregister_native_host",
    "check_and_register_browser",
    "register_browser_extensions",
    "unregister_browser_extensions",
    "is_registered",
    "get_status",
]
'''
write_module("services/browser/__init__.py", browser_init)

# 5.4 updater_service.py
res_updater = subprocess.run(["git", "show", "HEAD:updater.py"], capture_output=True, text=True, encoding="utf-8")
updater_src = res_updater.stdout

old_updater_init = """    def __init__(
        self,
        current_version: str = APP_VERSION,
        repo_owner: str = GITHUB_REPO_OWNER,
        repo_name: str = GITHUB_REPO_NAME,
        on_log: Optional[Callable[[str], None]] = None,
        timeout: int = 12
    ):
        self.current_version = str(current_version or APP_VERSION).strip()
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.api_url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/releases/latest"
        self.on_log = on_log
        self.timeout = max(3, int(timeout))"""

new_updater_init = """    def __init__(
        self,
        current_version: str = APP_VERSION,
        repo_owner: str = GITHUB_REPO_OWNER,
        repo_name: str = GITHUB_REPO_NAME,
        on_log: Optional[Callable[[str], None]] = None,
        timeout: int = 12,
        ssl_context: Optional[ssl.SSLContext] = None
    ):
        self.current_version = str(current_version or APP_VERSION).strip()
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.api_url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/releases/latest"
        self.on_log = on_log
        self.timeout = max(3, int(timeout))
        if ssl_context is not None:
            self.ssl_context = ssl_context
        else:
            try:
                self.ssl_context = ssl.create_default_context()
            except Exception:
                self.ssl_context = _get_ssl_context()"""

updater_src = updater_src.replace(old_updater_init, new_updater_init)
updater_src = updater_src.replace("        ctx = _get_ssl_context()\n        try:\n            req = urllib.request.Request(self.api_url", "        ctx = self.ssl_context if hasattr(self, 'ssl_context') and self.ssl_context is not None else _get_ssl_context()\n        try:\n            req = urllib.request.Request(self.api_url")
updater_src = updater_src.replace("        ctx = _get_ssl_context()\n        try:\n            req = urllib.request.Request(download_url", "        ctx = self.ssl_context if hasattr(self, 'ssl_context') and self.ssl_context is not None else _get_ssl_context()\n        try:\n            req = urllib.request.Request(download_url")
updater_src = updater_src.replace('YTDLP_GITHUB_LATEST_API = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"', 'YTDLP_GITHUB_LATEST_API = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"\nYTDLP_GITHUB_RELEASES_API = YTDLP_GITHUB_LATEST_API')

write_module("services/updater_service.py", updater_src)

# 5.5 youtube_service.py
res_yt = subprocess.run(["git", "show", "HEAD:youtube_resolver.py"], capture_output=True, text=True, encoding="utf-8")
youtube_src = res_yt.stdout

old_yt_imp = """from updater import (
    APP_VERSION,
    parse_version,
    is_newer_version,
    YtDlpAutoUpdater,
    AppAutoUpdater,
    get_ytdlp_plugin_dir,
)"""

new_yt_imp = """try:
    from .updater_service import (
        APP_VERSION,
        parse_version,
        is_newer_version,
        YtDlpAutoUpdater,
        AppAutoUpdater,
        get_ytdlp_plugin_dir,
    )
except ImportError:
    from updater import (
        APP_VERSION,
        parse_version,
        is_newer_version,
        YtDlpAutoUpdater,
        AppAutoUpdater,
        get_ytdlp_plugin_dir,
    )"""

youtube_src = youtube_src.replace(old_yt_imp, new_yt_imp)
write_module("services/youtube_service.py", youtube_src)

# 5.6 services/__init__.py
services_init = '''from .startup_service import (
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
    WINDOWS_RUN_KEY,
    STARTUP_REG_KEY_NAME,
    LEGACY_STARTUP_REG_KEY_NAME,
    TASK_NAME,
    LEGACY_TASK_NAME,
    get_installed_exe_path,
    get_startup_folder,
    get_startup_dir,
    is_startup_enabled,
    enable_startup,
    disable_startup,
    get_startup_entry,
)
from .single_instance import notify_running_instance
from .updater_service import (
    APP_VERSION,
    parse_version,
    is_newer_version,
    YtDlpAutoUpdater,
    AppAutoUpdater,
    get_ytdlp_plugin_dir,
)
from .youtube_service import (
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
from .browser import (
    BrowserBridgeServer,
    DEFAULT_BRIDGE_PORT,
    register_native_host,
    unregister_native_host,
    check_and_register_browser,
    register_browser_extensions,
    unregister_browser_extensions,
    is_registered,
    get_status,
)

__all__ = [
    "IS_WINDOWS",
    "GWL_STYLE",
    "GWL_EXSTYLE",
    "WS_EX_APPWINDOW",
    "WS_EX_TOOLWINDOW",
    "WS_MINIMIZEBOX",
    "WS_SYSMENU",
    "SW_HIDE",
    "SW_MINIMIZE",
    "SW_RESTORE",
    "SW_SHOW",
    "WINDOWS_RUN_KEY",
    "STARTUP_REG_KEY_NAME",
    "LEGACY_STARTUP_REG_KEY_NAME",
    "TASK_NAME",
    "LEGACY_TASK_NAME",
    "get_installed_exe_path",
    "get_startup_folder",
    "get_startup_dir",
    "is_startup_enabled",
    "enable_startup",
    "disable_startup",
    "get_startup_entry",
    "notify_running_instance",
    "APP_VERSION",
    "parse_version",
    "is_newer_version",
    "YtDlpAutoUpdater",
    "AppAutoUpdater",
    "get_ytdlp_plugin_dir",
    "YouTubeResolver",
    "MediaResolver",
    "is_youtube_url",
    "is_social_media_url",
    "is_media_url",
    "extract_youtube_id",
    "extract_media_platform",
    "extract_media_id",
    "is_ytdlp_available",
    "get_ytdlp_version",
    "update_ytdlp_engine",
    "has_ffmpeg",
    "find_ffmpeg_bin",
    "sanitize_filename",
    "YouTubeStreamInfo",
    "MediaStreamInfo",
    "VideoFormatOption",
    "format_filesize",
    "SUPPORTED_COOKIE_BROWSERS",
    "detect_installed_cookie_browsers",
    "BrowserBridgeServer",
    "DEFAULT_BRIDGE_PORT",
    "register_native_host",
    "unregister_native_host",
    "check_and_register_browser",
    "register_browser_extensions",
    "unregister_browser_extensions",
    "is_registered",
    "get_status",
]
'''
write_module("services/__init__.py", services_init)

# 6. ui/
# 6.1 components/base_modal.py
base_modal_code = '''"""
SafeModalDialog: Resilient, High-DPI scaled, localized dialog base modal.
"""
import os
import sys
import tkinter as tk
from tkinter import ttk
from typing import Optional, Callable, Dict, Any

from ...config import get_resource_path
from ...locales.i18n import tr, LocalizationManager
from ...utils.tk_helpers import _detach_photo_tk

''' + get_slice(5760, 6008) + "\n"
write_module("ui/components/base_modal.py", base_modal_code)

# 6.2 components/tooltip.py
tooltip_code = '''"""
ToolTip: Lightweight hovered tooltip bubble for widgets.
"""
import tkinter as tk
from typing import Optional, Union, Callable

from ...locales.i18n import tr

''' + get_slice(6011, 6102) + "\n"
write_module("ui/components/tooltip.py", tooltip_code)

# 6.3 components/__init__.py
components_init = '''from .base_modal import SafeModalDialog
from .tooltip import ToolTip

__all__ = ["SafeModalDialog", "ToolTip"]
'''
write_module("ui/components/__init__.py", components_init)

# 6.4 modals/toasts.py
toasts_code = '''"""
Toast notifications: FetchingLinkToast & StartupWelcomeToast.
"""
import os
import sys
import ctypes
import urllib.request
import urllib.parse
import tkinter as tk
from tkinter import ttk
from typing import Optional, Callable, Dict, Any, List
try:
    from PIL import Image, ImageTk
except ImportError:
    Image = None
    ImageTk = None

from ...config import get_resource_path
from ...locales.i18n import tr
from ...utils.dpi import get_windows_work_area
from ...utils.tk_helpers import _detach_photo_tk

''' + get_slice(4501, 5079) + "\n"
write_module("ui/modals/toasts.py", toasts_code)

# 6.5 modals/quality_modal.py
quality_modal_code = '''"""
QualitySelectionModal: Interactive video/audio resolution and stream format picker.
"""
import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog
from typing import Optional, Callable, Dict, Any, List
try:
    from PIL import Image, ImageTk
except ImportError:
    Image = None
    ImageTk = None

from ...config import get_resource_path
from ...locales.i18n import tr
from ...utils.file_ops import CATEGORY_SUBFOLDERS, resolve_categorized_path
from ...services.youtube_service import VideoFormatOption, format_filesize, sanitize_filename
from ...utils.tk_helpers import _detach_photo_tk

''' + get_slice(5265, 5753) + "\n"
write_module("ui/modals/quality_modal.py", quality_modal_code)

# 6.6 modals/confirm_modal.py
confirm_modal_code = '''"""
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

''' + get_slice(6670, 7788) + "\n"
write_module("ui/modals/confirm_modal.py", confirm_modal_code)

# 6.7 modals/candidates_modal.py
candidates_modal_code = '''"""
MultipleCandidatesModal: Interactive selection dialog when page sniffer extracts multiple download links.
"""
import os
import sys
import tkinter as tk
from tkinter import ttk
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

''' + get_slice(7791, 8231) + "\n"
write_module("ui/modals/candidates_modal.py", candidates_modal_code)

# 6.8 modals/refresh_modal.py
refresh_modal_code = '''"""
RefreshLinkModal: Interactive dialog to renew expired temporary download URLs while preserving chunks.
"""
import os
import sys
import threading
import ssl
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Callable, Dict, Any
try:
    from PIL import Image, ImageTk
except ImportError:
    Image = None
    ImageTk = None

from ...config import get_resource_path
from ...locales.i18n import tr
from ..components.base_modal import SafeModalDialog
from ...core.html_resolver import validate_refresh_url
from ...core.chunk import get_permissive_ssl_context
from ...utils.url_utils import derive_download_filename
from ...utils.clipboard import get_clipboard_text
from ...utils.tk_helpers import _detach_photo_tk

''' + get_slice(8234, 8687) + "\n"
write_module("ui/modals/refresh_modal.py", refresh_modal_code)

# 6.9 modals/update_modal.py
update_modal_code = '''"""
AppUpdateModal: Dialog presenting GitHub Release updates with live download progress and installer launch.
"""
import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Callable, Dict, Any
try:
    from PIL import Image, ImageTk
except ImportError:
    Image = None
    ImageTk = None

from ...config import get_resource_path, APP_VERSION
from ...locales.i18n import tr
from ..components.base_modal import SafeModalDialog
from ...services.updater_service import AppAutoUpdater
from ...services.youtube_service import format_filesize
from ...utils.tk_helpers import _detach_photo_tk

''' + get_slice(8690, 9021) + "\n"
write_module("ui/modals/update_modal.py", update_modal_code)

# 6.10 modals/__init__.py
modals_init = '''from .toasts import FetchingLinkToast, StartupWelcomeToast
from .quality_modal import QualitySelectionModal
from .confirm_modal import (
    DownloadConfirmationModal,
    DownloadConfirmationDialog,
    DownloadConfirmModal,
)
from .candidates_modal import MultipleCandidatesModal
from .refresh_modal import RefreshLinkModal, RefreshLinkDialog
from .update_modal import AppUpdateModal

__all__ = [
    "FetchingLinkToast",
    "StartupWelcomeToast",
    "QualitySelectionModal",
    "DownloadConfirmationModal",
    "DownloadConfirmationDialog",
    "DownloadConfirmModal",
    "MultipleCandidatesModal",
    "RefreshLinkModal",
    "RefreshLinkDialog",
    "AppUpdateModal",
]
'''
write_module("ui/modals/__init__.py", modals_init)

# 6.11 system_tray.py
tray_code = '''"""
SystemTrayManager: Windows system tray notification area icon, context menu, and background lifecycle.
"""
import os
import sys
import threading
import weakref
import time
from typing import Optional, Callable, Any
try:
    from PIL import Image
except ImportError:
    Image = None

try:
    import pystray
    from pystray import MenuItem as TrayMenuItem, Menu as TrayMenu
    PYSTRAY_AVAILABLE = True
except Exception:
    pystray = None
    TrayMenuItem = None
    TrayMenu = None
    PYSTRAY_AVAILABLE = False

from ..config import get_resource_path
from ..locales.i18n import tr, LocalizationManager
from ..services.startup_service import is_startup_enabled

''' + get_slice(9028, 9251) + "\n"
write_module("ui/system_tray.py", tray_code)

# 6.12 main_window.py
main_window_code = '''"""
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

''' + get_slice(9258, 13942) + "\n\n" + get_slice(13949, 14058) + "\n"

write_module("ui/main_window.py", main_window_code)

# 6.13 ui/__init__.py
ui_init = '''from .main_window import (
    ModernFramelessGUI,
    main,
    SmartDownloadEngine,
    TurboDownloaderGUI,
    DownloaderApp,
    SmartDownloadGUI,
)
from .system_tray import SystemTrayManager, PYSTRAY_AVAILABLE
from .components import SafeModalDialog, ToolTip
from .modals import (
    FetchingLinkToast,
    StartupWelcomeToast,
    QualitySelectionModal,
    DownloadConfirmationModal,
    DownloadConfirmationDialog,
    DownloadConfirmModal,
    MultipleCandidatesModal,
    RefreshLinkModal,
    RefreshLinkDialog,
    AppUpdateModal,
)

__all__ = [
    "ModernFramelessGUI",
    "main",
    "SmartDownloadEngine",
    "TurboDownloaderGUI",
    "DownloaderApp",
    "SmartDownloadGUI",
    "SystemTrayManager",
    "PYSTRAY_AVAILABLE",
    "SafeModalDialog",
    "ToolTip",
    "FetchingLinkToast",
    "StartupWelcomeToast",
    "QualitySelectionModal",
    "DownloadConfirmationModal",
    "DownloadConfirmationDialog",
    "DownloadConfirmModal",
    "MultipleCandidatesModal",
    "RefreshLinkModal",
    "RefreshLinkDialog",
    "AppUpdateModal",
]
'''
write_module("ui/__init__.py", ui_init)

# 7. src/smart_download/__init__.py
package_init = '''"""
Smart Download (SD) — High-Performance Enterprise Modular Download Engine
"""
__version__ = "2.0.0"

from .config import (
    APP_NAME,
    APP_TITLE,
    APP_ID,
    APP_VERSION,
    get_resource_path,
    get_config_dir,
    get_app_config_dir,
    get_settings_file_path,
    load_settings,
    save_settings,
    get_setting,
    set_setting,
)
from .locales.i18n import LocalizationManager, tr, get_current_language, set_current_language
from .core.engine import TurboDownloadEngine
from .core.chunk import DownloadChunk, get_permissive_ssl_context
from .ui.main_window import ModernFramelessGUI, main

__all__ = [
    "__version__",
    "APP_NAME",
    "APP_TITLE",
    "APP_ID",
    "APP_VERSION",
    "get_resource_path",
    "get_config_dir",
    "get_app_config_dir",
    "get_settings_file_path",
    "load_settings",
    "save_settings",
    "get_setting",
    "set_setting",
    "LocalizationManager",
    "tr",
    "get_current_language",
    "set_current_language",
    "TurboDownloadEngine",
    "DownloadChunk",
    "get_permissive_ssl_context",
    "ModernFramelessGUI",
    "main",
]
'''
write_module("__init__.py", package_init)

# 8. src/smart_download/main.py
main_entry = '''"""
Smart Download entry point script.
"""
import sys
import os

_src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from smart_download.ui.main_window import main

if __name__ == "__main__":
    main()
'''
write_module("main.py", main_entry)

print("[+] All modules created and verified successfully from HEAD!")
