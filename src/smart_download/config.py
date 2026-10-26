"""
Application configuration, paths, constants, and settings management for Smart Download.
"""
import os
import sys
import json
import shutil
import tempfile
from typing import Dict, Any, Optional, Tuple

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

def get_resource_path(relative_path: str) -> str:
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


def is_test_environment() -> bool:
    """Returns True ONLY when running inside an automated test suite."""
    if getattr(sys, "frozen", False):
        return False
    if os.environ.get("SD_TESTING") == "1":
        return True
    if "pytest" in sys.modules:
        return True
    args = [arg.lower() for arg in sys.argv[:3]] if hasattr(sys, "argv") and sys.argv else []
    return any(
        arg.endswith(("pytest", "unittest"))
        or "unittest" in arg
        or "pytest" in arg
        or "test" in os.path.basename(arg)
        for arg in args
    )


def get_config_dir() -> str:
    """Returns persistent application configuration directory path."""
    cfg_override = os.environ.get("SD_CONFIG_DIR")
    if cfg_override:
        try:
            os.makedirs(cfg_override, exist_ok=True)
        except Exception:
            pass
        return cfg_override
    if is_test_environment():
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

import threading

_settings_lock = threading.RLock()
_cached_settings_data: Optional[Dict[str, Any]] = None
_cached_stat_key: Optional[Tuple[str, int, int]] = None

def _clear_settings_cache():
    """Explicitly invalidates the in-memory settings cache (useful during unit tests)."""
    global _cached_settings_data, _cached_stat_key
    with _settings_lock:
        _cached_settings_data = None
        _cached_stat_key = None

def load_settings() -> Dict[str, Any]:
    """Loads user configuration dictionary from settings.json with mtime-based in-memory caching."""
    path = get_settings_file_path()
    defaults = {
        "minimize_to_tray": True,
        "auto_categorize_folders": True,
        "language": "ar",
        "auto_unpack_archives": False,
        "subtitle_embed_mode": "soft_embed",
    }

    with _settings_lock:
        global _cached_settings_data, _cached_stat_key
        try:
            st = os.stat(path)
            stat_key = (path, st.st_mtime_ns, st.st_size)
        except OSError:
            stat_key = (path, -1, -1)

        if _cached_stat_key == stat_key and _cached_settings_data is not None:
            return dict(_cached_settings_data)

        cur = dict(defaults)
        if stat_key[1] != -1:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        cur.update(data)
            except Exception:
                pass

        _cached_settings_data = cur
        _cached_stat_key = stat_key
        return dict(_cached_settings_data)

def save_settings(settings_dict: Dict[str, Any]) -> bool:
    """Persists updated configuration dictionary to settings.json and refreshes memory cache."""
    path = get_settings_file_path()
    try:
        with _settings_lock:
            global _cached_settings_data, _cached_stat_key
            cur = load_settings()
            cur.update(settings_dict)
            parent_dir = os.path.dirname(path)
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(cur, f, indent=2)
            try:
                st = os.stat(path)
                stat_key = (path, st.st_mtime_ns, st.st_size)
            except OSError:
                stat_key = (path, -1, -1)
            _cached_settings_data = dict(cur)
            _cached_stat_key = stat_key
            return True
    except Exception:
        return False

def get_setting(key: str, default: Any = None) -> Any:
    """Retrieves a single setting value with fallback default."""
    return load_settings().get(key, default)

def set_setting(key: str, value: Any) -> bool:
    """Sets and persists a single setting value."""
    return save_settings({key: value})

