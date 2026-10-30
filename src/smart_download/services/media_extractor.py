"""
Media extractor service providing lazy loading and background warmup for yt_dlp.
"""
import os
import sys
import threading
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
    if yt_dlp is not None:
        return yt_dlp
    with _yt_dlp_lock:
        if yt_dlp is not None:
            return yt_dlp

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


__all__ = ["_get_yt_dlp", "warmup_yt_dlp_background", "yt_dlp"]
