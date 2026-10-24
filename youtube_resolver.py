"""
Backward compatibility entry-point for youtube_resolver.
Logic has moved to smart_download.services.youtube_service.
"""
import sys
import os
import types

_src_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if os.path.isdir(_src_dir) and _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from smart_download.services.youtube_service import *
from smart_download.services.youtube_service import (
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
    detect_installed_cookie_browsers,
)

_SYNC_ACTIVE = False

class _YouTubeResolverShim(types.ModuleType):
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
            td = sys.modules.get("turbo_downloader")
            if td is not None and hasattr(td, name):
                try:
                    setattr(td, name, value)
                except Exception:
                    pass
        finally:
            _SYNC_ACTIVE = False

sys.modules[__name__].__class__ = _YouTubeResolverShim
