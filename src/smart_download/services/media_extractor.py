"""
Media extractor service providing lazy loading and background warmup for yt_dlp.
"""
import os
import sys
import threading
import types
from typing import Any, Optional

yt_dlp: Any = None
_yt_dlp_lock = threading.Lock()
_plugin_activated = False


def _get_yt_dlp() -> Any:
    """
    Lazily imports and returns the yt_dlp module on demand.
    Thread-safe and keeps module-level yt_dlp updated for mock compatibility.
    """
    global yt_dlp, _plugin_activated
    # 1. Fast path: check sys.modules first for dynamic reloads, mocks, or deactivations
    mod_sys = sys.modules.get("yt_dlp")
    if mod_sys is not None:
        yt_dlp = mod_sys
        return yt_dlp
    if yt_dlp is not None:
        if not isinstance(yt_dlp, types.ModuleType) or hasattr(yt_dlp, "_mock_name"):
            return yt_dlp
        yt_dlp = None

    with _yt_dlp_lock:
        mod_sys = sys.modules.get("yt_dlp")
        if mod_sys is not None:
            yt_dlp = mod_sys
            return yt_dlp
        if yt_dlp is not None:
            if not isinstance(yt_dlp, types.ModuleType) or hasattr(yt_dlp, "_mock_name"):
                return yt_dlp
            yt_dlp = None

        if not _plugin_activated:
            _plugin_activated = True
            try:
                try:
                    from .updater_service import YtDlpAutoUpdater, get_ytdlp_plugin_dir
                except ImportError:
                    try:
                        from smart_download.services.updater_service import YtDlpAutoUpdater, get_ytdlp_plugin_dir
                    except ImportError:
                        from updater import YtDlpAutoUpdater, get_ytdlp_plugin_dir
                plugin_dir = get_ytdlp_plugin_dir()
                if os.path.isdir(plugin_dir):
                    YtDlpAutoUpdater(plugin_dir=plugin_dir).activate_plugin()
            except Exception:
                pass

        if "yt_dlp" in sys.modules and sys.modules["yt_dlp"] is not None:
            yt_dlp = sys.modules["yt_dlp"]
            return yt_dlp
        try:
            import yt_dlp as _mod
            yt_dlp = _mod
            return yt_dlp
        except ImportError:
            return None


def _reset_plugin_state() -> None:
    """Resets internal plugin activation and yt_dlp cache for clean testing."""
    global yt_dlp, _plugin_activated
    with _yt_dlp_lock:
        yt_dlp = None
        _plugin_activated = False


def warmup_yt_dlp_background(delay_seconds: float = 3.0) -> None:
    """
    Kicks off a lightweight daemon thread that pre-warms yt_dlp extractors in the background
    after the main UI / tray icon has loaded.
    """
    def _warmup():
        import time
        time.sleep(delay_seconds)
        try:
            _get_yt_dlp()
        except Exception:
            pass

    t = threading.Thread(target=_warmup, name="YtDlpWarmupThread", daemon=True)
    t.start()


__all__ = ["_get_yt_dlp", "warmup_yt_dlp_background", "yt_dlp", "_reset_plugin_state"]
