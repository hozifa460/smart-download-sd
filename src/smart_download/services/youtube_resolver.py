"""
YouTube & Streaming Resolver module alias.
Re-exports all symbols from youtube_service and youtube_models for backward compatibility.
"""
from .youtube_service import *
from .youtube_models import (
    YOUTUBE_URL_REGEX,
    SOCIAL_MEDIA_PATTERNS,
    INVALID_FILENAME_CHARS,
    SUPPORTED_COOKIE_BROWSERS,
    detect_installed_cookie_browsers,
    is_youtube_url,
    is_social_media_url,
    is_ytdlp_available,
    get_ytdlp_version,
    update_ytdlp_engine,
    is_ytdlp_extractor_supported,
    is_media_url,
    PLATFORM_DISPLAY_NAMES,
    extract_media_platform,
    extract_media_id,
    extract_youtube_id,
    find_ffmpeg_bin,
    has_ffmpeg,
    sanitize_filename,
    VideoFormatOption,
    format_filesize,
    YouTubeStreamInfo,
    MediaStreamInfo,
)
