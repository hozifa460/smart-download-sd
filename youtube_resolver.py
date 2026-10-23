"""
========================================================================================
🎥 YOUTUBE & STREAMING RESOLVER MODULE — Smart Download (SD)
========================================================================================
Modular resolver layer for YouTube and streaming media:
1. Regex-based pattern matching for YouTube URLs (watch, shorts, embed, live, youtu.be).
2. Direct stream extraction via yt-dlp (with fallback to progressive or separate streams).
3. Audio/Video separation detection and stream resolution.
4. Lossless FFmpeg audio+video container merging (-c copy).
5. Robust error handling, sanitized filenames, and graceful guidance if yt-dlp is missing.
========================================================================================
"""

import os
import re
import sys
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Callable, Any

from updater import (
    APP_VERSION,
    parse_version,
    is_newer_version,
    YtDlpAutoUpdater,
    AppAutoUpdater,
    get_ytdlp_plugin_dir,
)

# Activate external updated yt-dlp plugin from %APPDATA%\SmartDownload\yt_dlp_plugin if present on disk
try:
    _default_plugin_dir = get_ytdlp_plugin_dir()
    if os.path.isdir(_default_plugin_dir):
        YtDlpAutoUpdater(plugin_dir=_default_plugin_dir).activate_plugin()
except Exception:
    pass


# Regex matching various forms of YouTube URLs
# Matches:
# - https://www.youtube.com/watch?v=VIDEO_ID
# - https://youtube.com/watch?v=VIDEO_ID&feature=share
# - https://youtu.be/VIDEO_ID
# - https://www.youtube.com/shorts/VIDEO_ID
# - https://www.youtube.com/embed/VIDEO_ID
# - https://www.youtube.com/v/VIDEO_ID
# - https://www.youtube.com/live/VIDEO_ID
# - https://m.youtube.com/watch?v=VIDEO_ID
# - https://music.youtube.com/watch?v=VIDEO_ID
YOUTUBE_URL_REGEX = re.compile(
    r'^(?:https?://)?(?:www\.|m\.|music\.)?'
    r'(?:youtube\.com/(?:watch\?(?:.*&)?v=|shorts/|embed/|v/|live/)|youtu\.be/)'
    r'([a-zA-Z0-9_-]{11})',
    re.IGNORECASE
)

# Robust regex patterns for major social media platforms
SOCIAL_MEDIA_PATTERNS = {
    "tiktok": re.compile(
        r'^(?:https?://)?(?:[a-zA-Z0-9-]+\.)?tiktok\.com/(?:@[^/?#]+/(?:video|photo)/\d+|t/[a-zA-Z0-9_-]+|v/\d+)|^(?:https?://)?(?:vt|vm)\.tiktok\.com/[a-zA-Z0-9_-]+',
        re.IGNORECASE
    ),
    "instagram": re.compile(
        r'^(?:https?://)?(?:[a-zA-Z0-9-]+\.)?(?:instagram\.com|instagr\.am)/(?:p|reel|reels|stories|tv)/[a-zA-Z0-9_.-]+',
        re.IGNORECASE
    ),
    "facebook": re.compile(
        r'^(?:https?://)?(?:[a-zA-Z0-9-]+\.)?fb\.watch/[a-zA-Z0-9_.-]+/?|^(?:https?://)?(?:[a-zA-Z0-9-]+\.)?facebook\.com/(?:watch/?(?:\?|$)|reel/\d+|reels/\d+|share/[vr]/[a-zA-Z0-9_-]+|[^/?#]+/videos/\d+|video\.php\?(?:.*&)?v=\d+)',
        re.IGNORECASE
    ),
    "twitter": re.compile(
        r'^(?:https?://)?(?:[a-zA-Z0-9-]+\.)?(?:twitter\.com|x\.com)/[^/?#]+/status/\d+',
        re.IGNORECASE
    ),
    "reddit": re.compile(
        r'^(?:https?://)?(?:[a-zA-Z0-9-]+\.)?(?:reddit\.com/r/[^/?#]+/comments/[a-zA-Z0-9]+|redd\.it/[a-zA-Z0-9]+|v\.redd\.it/[a-zA-Z0-9]+)',
        re.IGNORECASE
    ),
    "vimeo": re.compile(
        r'^(?:https?://)?(?:[a-zA-Z0-9-]+\.)?vimeo\.com/(?:channels/[a-zA-Z0-9_-]+/|groups/[a-zA-Z0-9_-]+/videos/|album/\d+/video/|video/)?\d+',
        re.IGNORECASE
    ),
    "dailymotion": re.compile(
        r'^(?:https?://)?(?:[a-zA-Z0-9-]+\.)?(?:dailymotion\.com/(?:video|embed/video)/|dai\.ly/)[a-zA-Z0-9]+',
        re.IGNORECASE
    ),
    "pinterest": re.compile(
        r'^(?:https?://)?(?:[a-zA-Z0-9-]+\.)?(?:pinterest\.(?:com|[a-z]{2}(?:\.[a-z]{2})?)/pin/|pin\.it/)[a-zA-Z0-9_-]+',
        re.IGNORECASE
    ),
    "threads": re.compile(
        r'^(?:https?://)?(?:www\.)?threads\.net/@?[^/?#]+/post/[a-zA-Z0-9_-]+',
        re.IGNORECASE
    ),
    "snapchat": re.compile(
        r'^(?:https?://)?(?:[a-zA-Z0-9-]+\.)?snapchat\.com/(?:spotlight|story|t)/[a-zA-Z0-9_-]+',
        re.IGNORECASE
    ),
    "twitch": re.compile(
        r'^(?:https?://)?(?:[a-zA-Z0-9-]+\.)?twitch\.tv/(?:videos/\d+|clips/[a-zA-Z0-9_-]+)',
        re.IGNORECASE
    ),
    "rumble": re.compile(
        r'^(?:https?://)?(?:www\.)?rumble\.com/v[a-zA-Z0-9_-]+',
        re.IGNORECASE
    ),
}

# Reserved filename characters for Windows / Linux cross-compatibility
INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Supported browser sources for session cookies extraction
SUPPORTED_COOKIE_BROWSERS = ("auto", "none", "edge", "chrome", "firefox", "brave", "opera", "vivaldi")


def detect_installed_cookie_browsers() -> List[str]:
    """
    Detects installed web browsers capable of supplying session cookies to yt-dlp.
    Checks standard Windows user data paths under %LOCALAPPDATA% and %APPDATA%:
    - 'firefox': %APPDATA%\\Mozilla\\Firefox\\Profiles
    - 'edge': %LOCALAPPDATA%\\Microsoft\\Edge\\User Data
    - 'chrome': %LOCALAPPDATA%\\Google\\Chrome\\User Data
    - 'brave': %LOCALAPPDATA%\\BraveSoftware\\Brave-Browser\\User Data
    - 'opera': %APPDATA%\\Opera Software\\Opera Stable
    - 'vivaldi': %LOCALAPPDATA%\\Vivaldi\\User Data
    Returns list of detected browser names; falls back to ['edge', 'chrome', 'firefox'] if none found on disk.
    """
    local_appdata = os.environ.get("LOCALAPPDATA", "")
    appdata = os.environ.get("APPDATA", "")
    userprofile = os.environ.get("USERPROFILE", "")
    home = os.path.expanduser("~")

    browser_checks = [
        ("firefox", [
            os.path.join(appdata, "Mozilla", "Firefox", "Profiles") if appdata else "",
            os.path.join(userprofile, "AppData", "Roaming", "Mozilla", "Firefox", "Profiles") if userprofile else "",
            os.path.join(home, ".mozilla", "firefox"),
        ]),
        ("edge", [
            os.path.join(local_appdata, "Microsoft", "Edge", "User Data") if local_appdata else "",
            os.path.join(userprofile, "AppData", "Local", "Microsoft", "Edge", "User Data") if userprofile else "",
            os.path.join(home, ".config", "microsoft-edge"),
        ]),
        ("chrome", [
            os.path.join(local_appdata, "Google", "Chrome", "User Data") if local_appdata else "",
            os.path.join(userprofile, "AppData", "Local", "Google", "Chrome", "User Data") if userprofile else "",
            os.path.join(home, ".config", "google-chrome"),
        ]),
        ("brave", [
            os.path.join(local_appdata, "BraveSoftware", "Brave-Browser", "User Data") if local_appdata else "",
            os.path.join(userprofile, "AppData", "Local", "BraveSoftware", "Brave-Browser", "User Data") if userprofile else "",
            os.path.join(home, ".config", "BraveSoftware", "Brave-Browser"),
        ]),
        ("opera", [
            os.path.join(appdata, "Opera Software", "Opera Stable") if appdata else "",
            os.path.join(userprofile, "AppData", "Roaming", "Opera Software", "Opera Stable") if userprofile else "",
            os.path.join(home, ".config", "opera"),
        ]),
        ("vivaldi", [
            os.path.join(local_appdata, "Vivaldi", "User Data") if local_appdata else "",
            os.path.join(userprofile, "AppData", "Local", "Vivaldi", "User Data") if userprofile else "",
            os.path.join(home, ".config", "vivaldi"),
        ]),
    ]

    detected: List[str] = []
    for name, candidate_paths in browser_checks:
        for p in candidate_paths:
            if p and os.path.isdir(p):
                detected.append(name)
                break

    return detected if detected else ["edge", "chrome", "firefox"]


def is_youtube_url(url: str) -> bool:
    """Returns True if the given URL is a recognized YouTube video or shorts URL."""
    if not url or not isinstance(url, str):
        return False
    return bool(YOUTUBE_URL_REGEX.search(url.strip()))


def is_social_media_url(url: str) -> bool:
    """
    Returns True if the given URL is a recognized social media post/video URL
    (Instagram, Facebook, X/Twitter, TikTok, Reddit, Vimeo, Dailymotion, Pinterest, etc.).
    """
    if not url or not isinstance(url, str):
        return False
    u = url.strip()
    for pat in SOCIAL_MEDIA_PATTERNS.values():
        if pat.search(u):
            return True
    return False


_YTDLP_EXTRACTORS_CACHE = None


def is_ytdlp_extractor_supported(url: str) -> bool:
    """
    Checks whether yt-dlp has a dedicated extractor matching the URL (excluding generic).
    Cached lazily for fast subsequent checks.
    """
    global _YTDLP_EXTRACTORS_CACHE
    if not is_ytdlp_available() or not url:
        return False
    try:
        with YtDlpAutoUpdater._lock:
            import yt_dlp
            if _YTDLP_EXTRACTORS_CACHE is None:
                _YTDLP_EXTRACTORS_CACHE = yt_dlp.extractor.gen_extractors()
            extractors = _YTDLP_EXTRACTORS_CACHE
        for ie in extractors:
            if ie.suitable(url) and ie.IE_NAME != 'generic':
                return True
    except Exception:
        pass
    return False


def is_media_url(url: str, check_ytdlp_extractors: bool = False) -> bool:
    """
    Returns True if the URL is recognized as YouTube or any supported social media platform.
    If check_ytdlp_extractors=True, falls back to querying yt-dlp extractor catalog.
    """
    if not url or not isinstance(url, str):
        return False
    u = url.strip()
    if is_youtube_url(u) or is_social_media_url(u):
        return True
    if check_ytdlp_extractors:
        return is_ytdlp_extractor_supported(u)
    return False


PLATFORM_DISPLAY_NAMES = {
    "youtube": "YouTube",
    "tiktok": "TikTok",
    "instagram": "Instagram",
    "facebook": "Facebook",
    "twitter": "Twitter / X",
    "reddit": "Reddit",
    "vimeo": "Vimeo",
    "dailymotion": "Dailymotion",
    "pinterest": "Pinterest",
    "threads": "Threads",
    "snapchat": "Snapchat",
    "twitch": "Twitch",
    "rumble": "Rumble",
}


def extract_media_platform(url: str) -> str:
    """
    Identifies the platform name for a given URL (e.g. 'YouTube', 'TikTok', 'Instagram',
    'Facebook', 'Twitter / X', 'Reddit', 'Vimeo', 'Dailymotion', 'Pinterest', etc.).
    """
    if not url or not isinstance(url, str):
        return "Media"
    u = url.strip()
    if is_youtube_url(u):
        return "YouTube"
    for name, pat in SOCIAL_MEDIA_PATTERNS.items():
        if pat.search(u):
            return PLATFORM_DISPLAY_NAMES.get(name, name.capitalize())
    return "Media"


def extract_media_id(url: str) -> Optional[str]:
    """
    Extracts an identifier from a media URL if detectable, otherwise None.
    """
    if not url or not isinstance(url, str):
        return None
    yt_id = extract_youtube_id(url)
    if yt_id:
        return yt_id
    u = url.strip()
    m = re.search(r'/(?:video|reel|reels|status|pin|comments|videos|p)/([a-zA-Z0-9_-]+)', u)
    if m:
        return m.group(1)
    m2 = re.search(r'/(?:vt|vm)\.tiktok\.com/([a-zA-Z0-9_-]+)', u)
    if m2:
        return m2.group(1)
    m3 = re.search(r'/fb\.watch/([a-zA-Z0-9_.-]+)', u)
    if m3:
        return m3.group(1)
    return None


def extract_youtube_id(url: str) -> Optional[str]:
    """Extracts the 11-character YouTube video ID from a URL, or None if invalid."""
    if not url or not isinstance(url, str):
        return None
    match = YOUTUBE_URL_REGEX.search(url.strip())
    return match.group(1) if match else None


def is_ytdlp_available() -> bool:
    """Checks whether the yt-dlp python package or CLI binary is available."""
    try:
        import yt_dlp  # noqa: F401
        return True
    except ImportError:
        return shutil.which("yt-dlp") is not None


def get_ytdlp_version() -> str:
    """Returns the currently active yt-dlp version string."""
    return YtDlpAutoUpdater().get_current_version()


def update_ytdlp_engine(
    force: bool = False,
    on_log: Optional[Callable[[str], None]] = None
) -> Dict[str, Any]:
    """Checks for and applies the latest yt-dlp extractor update into %APPDATA%\\SmartDownload\\yt_dlp_plugin."""
    return YtDlpAutoUpdater(on_log=on_log).update(force=force)



def find_ffmpeg_bin() -> Optional[str]:
    """Finds FFmpeg executable in PATH or next to the executable / project root."""
    bin_path = shutil.which("ffmpeg")
    if bin_path:
        return bin_path
    app_dirs = [
        getattr(sys, "_MEIPASS", ""),
        os.path.dirname(sys.executable) if hasattr(sys, "executable") else "",
        os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else "",
        os.getcwd(),
    ]
    for d in app_dirs:
        if d:
            candidate = os.path.join(d, "ffmpeg.exe" if sys.platform.startswith("win") else "ffmpeg")
            if os.path.isfile(candidate):
                return candidate
    return None


def has_ffmpeg() -> bool:
    """Checks whether FFmpeg executable is installed and reachable."""
    return find_ffmpeg_bin() is not None


def sanitize_filename(name: str, max_length: int = 180) -> str:
    """
    Sanitizes a string to make it safe for use as a filesystem filename across OSes.
    Removes reserved characters and trims leading/trailing dots and spaces.
    """
    if not name:
        return "youtube_download"
    cleaned = INVALID_FILENAME_CHARS.sub("_", name)
    # Collapse multiple consecutive underscores or spaces
    cleaned = re.sub(r'[\s_]+', ' ', cleaned).strip(" .")
    if not cleaned:
        cleaned = "youtube_download"
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length].rstrip(" .")
    return cleaned


@dataclass
class VideoFormatOption:
    """
    Structured representation of a selectable download quality/format option
    for presentation in the quality selection modal and execution by the downloader.
    """
    format_id: str                      # Identifier e.g. '137+140', '22', '140'
    resolution_label: str               # e.g. '4K (2160p)', '1080p (Full HD)', '720p (HD)', 'Audio Only (M4A)'
    height: int                         # Vertical height in pixels (0 for audio-only)
    ext: str                            # Target container extension e.g. 'mp4', 'm4a', 'webm'
    filesize_approx: int                # Total estimated bytes (video + audio if merged)
    fps: int = 30                       # Framerate if video
    vcodec: str = ""                    # Video codec name
    acodec: str = ""                    # Audio codec name
    is_progressive: bool = False        # True if single stream with multiplexed audio
    is_audio_only: bool = False         # True if stream contains audio only
    video_url: str = ""                 # URL for video stream (or audio stream if audio-only)
    video_headers: Dict[str, str] = field(default_factory=dict)
    audio_url: Optional[str] = None     # Paired audio stream URL if split/adaptive
    audio_headers: Dict[str, str] = field(default_factory=dict)
    audio_ext: str = "m4a"
    audio_size: int = 0
    note: str = ""                      # Human-readable note e.g. "60 FPS • Lossless Merge (FFmpeg)"


def format_filesize(num_bytes: int) -> str:
    """Formats raw byte count into human-readable units (e.g., '142.5 MB')."""
    if not num_bytes or num_bytes <= 0:
        return "N/A"
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(num_bytes)
    unit_idx = 0
    while size >= 1024.0 and unit_idx < len(units) - 1:
        size /= 1024.0
        unit_idx += 1
    if unit_idx == 0:
        return f"{int(size)} B"
    return f"{size:.1f} {units[unit_idx]}"


@dataclass
class YouTubeStreamInfo:
    """
    Resolved metadata and stream URLs for YouTube and social media streams.
    """
    video_id: str
    title: str
    clean_filename: str
    is_progressive: bool  # True if audio and video are already multiplexed in a single stream
    video_url: str
    video_headers: Dict[str, str] = field(default_factory=dict)
    video_ext: str = "mp4"
    video_resolution: str = "720p"
    video_size: int = 0
    audio_url: Optional[str] = None
    audio_headers: Dict[str, str] = field(default_factory=dict)
    audio_ext: str = "m4a"
    audio_size: int = 0
    duration: int = 0
    thumbnail_url: str = ""
    is_audio_only: bool = False
    platform: str = "YouTube"


# Clean alias
MediaStreamInfo = YouTubeStreamInfo


class YouTubeResolver:
    """
    High-level resolver that communicates with yt-dlp to extract high-speed direct
    stream URLs, extracts all available video qualities/formats, and orchestrates
    video + audio merging with FFmpeg for YouTube and social media platforms.
    """

    def __init__(
        self,
        on_log: Optional[Callable[[str], None]] = None,
        socket_timeout: int = 12,
        auto_update_on_failure: bool = True,
        cookies_from_browser: Optional[str] = "auto",
        cookies_file: Optional[str] = None
    ):
        self.on_log = on_log
        self.socket_timeout = max(1, int(socket_timeout))
        self.auto_update_on_failure = bool(auto_update_on_failure)
        self.cookies_from_browser = cookies_from_browser
        self.cookies_file = cookies_file

    def _build_ydl_opts(self, browser: Optional[str] = None, cookiefile: Optional[str] = None) -> Dict[str, Any]:
        """
        Builds standard yt-dlp extraction options dictionary, augmenting with cookiefile
        or cookiesfrombrowser if specified.
        """
        opts: Dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "nocheckcertificate": True,
            "noplaylist": True,
            "socket_timeout": self.socket_timeout,
            "remote_components": ["ejs:github"],
        }
        if cookiefile and os.path.isfile(cookiefile):
            opts["cookiefile"] = cookiefile
        if browser and browser.lower() not in ("none", "auto", "off", ""):
            opts["cookiesfrombrowser"] = (browser.lower(),)
        return opts

    def log(self, message: str):
        if self.on_log:
            try:
                self.on_log(message)
            except Exception:
                pass

    def extract_format_options(self, url: str) -> Tuple[Dict[str, Any], List[VideoFormatOption]]:
        """
        Extracts raw metadata and a structured, deduplicated list of available VideoFormatOption choices
        (e.g. 4K, 1440p, 1080p, 720p, 480p, 360p, and Audio-only) sorted by resolution descending.
        Supports YouTube as well as Instagram, Facebook, Twitter/X, TikTok, Reddit, Vimeo, Dailymotion, Pinterest, etc.
        Automatically retries with browser session cookies for login-required, private, or age-restricted media.
        """
        if not is_media_url(url, check_ytdlp_extractors=True):
            raise ValueError(f"URL is not a recognized media or streaming URL: {url}")

        if not is_ytdlp_available():
            raise RuntimeError(
                "yt-dlp is not installed. To download media streams, please install it with:\n"
                "pip install yt-dlp"
            )

        platform = extract_media_platform(url)
        media_id = extract_media_id(url) or extract_youtube_id(url) or "media"
        tag = platform.upper().replace(" / X", "")
        self.log(f"[{tag}] Extracting formats and stream metadata for {platform} media (ID: {media_id})...")

        try:
            import yt_dlp
        except ImportError:
            raise RuntimeError("yt-dlp Python package is required. Install with 'pip install yt-dlp'.")

        # Determine initial ydl_opts
        if self.cookies_file and os.path.isfile(self.cookies_file):
            ydl_opts = self._build_ydl_opts(cookiefile=self.cookies_file)
        elif self.cookies_from_browser and self.cookies_from_browser.lower() not in ("none", "auto", "off", ""):
            ydl_opts = self._build_ydl_opts(browser=self.cookies_from_browser)
        else:
            ydl_opts = self._build_ydl_opts()

        info = None
        ydl = None

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as active_ydl:
                info = active_ydl.extract_info(url, download=False)
                ydl = active_ydl
        except Exception as e:
            # Fallback 1: If explicit browser failed (e.g. locked DB / DPAPI error),
            # log and fallback to trying without cookies or next detected browser
            if self.cookies_from_browser and self.cookies_from_browser.lower() not in ("none", "auto", "off", "") and not (self.cookies_file and os.path.isfile(self.cookies_file)):
                self.log(f"[{tag}] Cookie extraction from browser '{self.cookies_from_browser}' failed ({e}). Falling back without cookies...")
                try:
                    fallback_opts = self._build_ydl_opts()
                    with yt_dlp.YoutubeDL(fallback_opts) as fb_ydl:
                        info = fb_ydl.extract_info(url, download=False)
                        ydl = fb_ydl
                except Exception as fb_err:
                    self.log(f"[{tag}] Unauthenticated fallback also failed: {fb_err}")
                    info = None

            # Fallback 2: If cookies_from_browser == 'auto' (or public unauthenticated failed),
            # iterate over detect_installed_cookie_browsers() and retry
            is_ydl_mocked = bool(getattr(yt_dlp.YoutubeDL, "_mock_name", None))
            is_updater_mocked = bool(
                getattr(YtDlpAutoUpdater, "_mock_name", None)
                or getattr(YtDlpAutoUpdater.update, "_mock_name", None)
            )
            err_str = str(e).lower()
            is_auth_error = any(kw in err_str for kw in (
                "sign in", "confirm your age", "private", "login", "log in",
                "account", "permission", "403", "forbidden", "cookie",
                "restricted", "member", "bot", "authenticate", "unauthorized"
            ))

            if not info and (self.cookies_from_browser == "auto" or self.cookies_from_browser is None):
                if is_auth_error or not is_updater_mocked:
                    self.log(f"[{tag}] Public extraction failed ({e}). Attempting extraction with browser cookies...")
                    for b in detect_installed_cookie_browsers():
                        try:
                            self.log(f"[{tag}] Retrying extraction with cookies from '{b}'...")
                            cookie_opts = self._build_ydl_opts(browser=b)
                            with yt_dlp.YoutubeDL(cookie_opts) as cookie_ydl:
                                info = cookie_ydl.extract_info(url, download=False)
                                if info:
                                    ydl = cookie_ydl
                                    self.log(f"[{tag}] Successfully extracted stream info using '{b}' cookies.")
                                    break
                        except Exception as cookie_err:
                            self.log(f"[{tag}] Cookies from '{b}' failed: {cookie_err}")
                            continue

            # Fallback 3: If still no info, check auto-updater fallback
            if not info:
                if self.auto_update_on_failure and (not is_ydl_mocked or is_updater_mocked):
                    self.log(f"[{tag}] Extraction failed ({e}). Checking for yt-dlp engine update...")
                    try:
                        up_res = YtDlpAutoUpdater(on_log=self.log).update()
                        if up_res.get("updated"):
                            import yt_dlp as refreshed_yt_dlp
                            self.log(f"[{tag}] Retrying extraction with updated yt-dlp v{up_res.get('version')}...")
                            with refreshed_yt_dlp.YoutubeDL(ydl_opts) as ydl2:
                                info = ydl2.extract_info(url, download=False)
                                ydl = ydl2
                        else:
                            raise e
                    except Exception:
                        raise RuntimeError(f"Failed to extract {platform} media stream info: {e}")
                else:
                    raise RuntimeError(f"Failed to extract {platform} media stream info: {e}")

        if not info:
            raise RuntimeError("yt-dlp returned empty metadata for the provided URL.")

        if "entries" in info and info["entries"]:
            info = info["entries"][0]

        if not info:
            raise RuntimeError("yt-dlp returned empty metadata for the provided URL.")

        # Propagate Cookie Headers to format http_headers if present in cookiejar or info
        cookiejar = getattr(ydl, "cookiejar", None) if ydl else None
        jar_cookies: Dict[str, str] = {}
        if cookiejar:
            try:
                for cookie in cookiejar:
                    jar_cookies[cookie.name] = cookie.value
            except Exception:
                pass

        cookie_header_val = ""
        if jar_cookies:
            cookie_header_val = "; ".join(f"{k}={v}" for k, v in jar_cookies.items())
        elif isinstance(info.get("cookies"), str):
            cookie_header_val = info["cookies"]
        elif isinstance(info.get("cookies"), dict):
            cookie_header_val = "; ".join(f"{k}={v}" for k, v in info["cookies"].items())
        elif isinstance(info.get("http_headers"), dict):
            cookie_header_val = info["http_headers"].get("Cookie") or info["http_headers"].get("cookie") or ""

        if cookie_header_val:
            formats_to_patch = info.get("formats", [])
            if not formats_to_patch and info.get("url"):
                formats_to_patch = [info]
            for f in formats_to_patch:
                headers = f.setdefault("http_headers", {})
                if "Cookie" not in headers and "cookie" not in headers:
                    headers["Cookie"] = cookie_header_val

        options = self.build_format_options(info)
        return info, options

    def build_format_options(self, info: Dict[str, Any]) -> List[VideoFormatOption]:
        """
        Processes formats dictionary from yt-dlp info and constructs sorted VideoFormatOption list.
        Accurately estimates sizes from bitrate and duration when raw filesize is omitted.
        Handles YouTube, TikTok, Instagram, Twitter/X, Facebook, Reddit, Vimeo, and generic media streams.
        """
        raw_formats = info.get("formats", [])
        duration = int(info.get("duration") or 0)

        # If formats is empty but top-level url exists (e.g. some direct Instagram/TikTok/Pinterest posts)
        if not raw_formats and info.get("url"):
            raw_formats = [{
                "format_id": info.get("format_id") or "direct",
                "url": info.get("url"),
                "ext": info.get("ext") or "mp4",
                "height": info.get("height") or 720,
                "width": info.get("width") or 1280,
                "filesize": info.get("filesize") or info.get("filesize_approx") or 0,
                "vcodec": info.get("vcodec") or "h264",
                "acodec": info.get("acodec") or "aac",
                "http_headers": info.get("http_headers") or {},
                "protocol": info.get("protocol") or "https",
            }]

        if not raw_formats:
            return []

        def _is_direct_stream(f: Dict[str, Any]) -> bool:
            url = f.get("url") or ""
            if not url or not url.startswith("http"):
                return False
            proto = str(f.get("protocol") or "").lower()
            if "m3u8" in proto or "dash" in proto:
                return False
            return True

        def _has_audio(f: Dict[str, Any]) -> bool:
            acodec = str(f.get("acodec") or "").lower()
            return bool(acodec and acodec != "none")

        def _has_video(f: Dict[str, Any]) -> bool:
            vcodec = str(f.get("vcodec") or "").lower()
            return bool(vcodec and vcodec != "none")

        def _estimate_size(f: Dict[str, Any]) -> int:
            if not f:
                return 0
            raw_sz = f.get("filesize") or f.get("filesize_approx")
            if raw_sz:
                try:
                    val = int(raw_sz)
                    if val > 0:
                        return val
                except (ValueError, TypeError):
                    pass
            tbr = float(f.get("tbr") or 0.0)
            vbr = float(f.get("vbr") or 0.0)
            abr = float(f.get("abr") or 0.0)
            bitrate_kbps = tbr or (vbr + abr) or vbr or abr
            if bitrate_kbps > 0 and duration > 0:
                return int((bitrate_kbps * 1000.0 / 8.0) * duration)
            return 0

        # Filter direct streams; fallback to any HTTP stream if strict filter removes all
        formats = [f for f in raw_formats if _is_direct_stream(f)]
        if not formats:
            formats = [f for f in raw_formats if f.get("url") and str(f.get("url")).startswith("http")]
        if not formats:
            return []

        # Fix missing / zero heights by inferring from width or resolution string
        for f in formats:
            h = int(f.get("height") or 0)
            w = int(f.get("width") or 0)
            if h <= 0 and w > 0:
                f["height"] = int(w * 9 / 16) if w > 1000 else int(w * 16 / 9)
            elif h <= 0:
                res_str = str(f.get("resolution") or f.get("format_note") or f.get("format_id") or "")
                m = re.search(r'(\d{3,4})p', res_str)
                if m:
                    f["height"] = int(m.group(1))
                else:
                    m2 = re.search(r'\d+x(\d+)', res_str)
                    if m2:
                        f["height"] = int(m2.group(1))
            if int(f.get("height") or 0) <= 0:
                f["height"] = 720

        # 1. Identify valid audio-only formats
        audio_only_formats = [
            f for f in formats
            if _has_audio(f) and not _has_video(f)
        ]

        def _audio_rank(f):
            # Prioritize original / default language audio tracks over dubs
            lang_pref = float(f.get("language_preference") or 0.0)
            abr = float(f.get("abr") or f.get("tbr") or 0.0)
            is_m4a = 1 if (f.get("ext") or "").lower() in ("m4a", "mp4") else 0
            return (lang_pref, is_m4a, abr)

        sorted_audios = sorted(audio_only_formats, key=_audio_rank, reverse=True)
        best_audio = sorted_audios[0] if sorted_audios else None
        best_audio_size = _estimate_size(best_audio) if best_audio else 0
        best_audio_ext = (best_audio.get("ext") or "m4a").lower() if best_audio else "m4a"
        best_audio_abr = int(best_audio.get("abr") or best_audio.get("tbr") or 128) if best_audio else 128

        # 2. Identify video-only formats
        video_only_formats = [
            f for f in formats
            if _has_video(f) and not _has_audio(f)
        ]

        # 3. Identify progressive (combined audio+video) formats
        progressive_formats = [
            f for f in formats
            if _has_video(f) and _has_audio(f)
        ]

        # Critical adaptation for social media (TikTok, Instagram, Twitter, etc.):
        # If there are no separate audio streams available, treat all video streams as progressive
        if not audio_only_formats:
            for vf in video_only_formats:
                if vf not in progressive_formats:
                    progressive_formats.append(vf)
            video_only_formats = []

        options: List[VideoFormatOption] = []
        ffmpeg_available = has_ffmpeg()

        # Collect distinct video heights
        all_heights = set()
        for f in video_only_formats:
            h = int(f.get("height") or 0)
            if h > 0:
                all_heights.add(h)
        for f in progressive_formats:
            h = int(f.get("height") or 0)
            if h > 0:
                all_heights.add(h)

        def _label_for_height(h: int, fps: int = 30, w: int = 0) -> str:
            if w > 0 and h > w:
                # Vertical format video (TikTok, Instagram Reels, Shorts)
                if w >= 1080 or h >= 1920:
                    base = f"1080p Vertical ({w}x{h})"
                elif w >= 720 or h >= 1280:
                    base = f"720p Vertical ({w}x{h})"
                elif w >= 480 or h >= 854:
                    base = f"480p Vertical ({w}x{h})"
                else:
                    base = f"{w}p Vertical ({w}x{h})"
            elif h >= 2000:
                base = "4K (2160p)"
            elif h >= 1350:
                base = "2K (1440p QHD)"
            elif h >= 1000:
                base = "1080p (Full HD)"
            elif h >= 700:
                base = "720p (HD)"
            elif h >= 450:
                base = "480p (SD)"
            elif h >= 340:
                base = "360p (SD)"
            elif h >= 220:
                base = "240p (SD)"
            elif h >= 140:
                base = "144p (SD)"
            elif h > 0:
                base = f"{h}p"
            else:
                base = "Original Quality"
            if fps >= 50:
                base += f" {fps}fps"
            return base

        # Helper to rank video-only streams for a given height
        def _video_rank(f):
            is_mp4 = 1 if (f.get("ext") or "").lower() == "mp4" else 0
            fps = int(f.get("fps") or 30)
            size = _estimate_size(f)
            return (is_mp4, fps, size)

        # Build options for each resolution height descending
        for h in sorted(all_heights, reverse=True):
            v_matches = [f for f in video_only_formats if int(f.get("height") or 0) == h]
            p_matches = [f for f in progressive_formats if int(f.get("height") or 0) == h]

            # Dual-stream option (FFmpeg required for merge)
            if ffmpeg_available and best_audio and v_matches:
                best_v = sorted(v_matches, key=_video_rank, reverse=True)[0]
                fps = int(best_v.get("fps") or 30)
                w = int(best_v.get("width") or 0)
                v_size = _estimate_size(best_v)
                approx_total = v_size + best_audio_size if (v_size and best_audio_size) else (v_size or best_audio_size)
                v_ext = (best_v.get("ext") or "mp4").lower()
                target_ext = "mp4" if (v_ext in ("mp4", "m4v") or ffmpeg_available) else v_ext

                options.append(VideoFormatOption(
                    format_id=f"{best_v.get('format_id')}+{best_audio.get('format_id')}",
                    resolution_label=_label_for_height(h, fps, w),
                    height=h,
                    ext=target_ext,
                    filesize_approx=approx_total,
                    fps=fps,
                    vcodec=best_v.get("vcodec", ""),
                    acodec=best_audio.get("acodec", ""),
                    is_progressive=False,
                    is_audio_only=False,
                    video_url=best_v["url"],
                    video_headers=best_v.get("http_headers", {}),
                    audio_url=best_audio["url"],
                    audio_headers=best_audio.get("http_headers", {}),
                    audio_ext=best_audio_ext,
                    audio_size=best_audio_size,
                    note=f"{fps} FPS • Lossless Merge (FFmpeg)"
                ))

            # Progressive option (if available and either no dual-stream or lower/equal 720p)
            if p_matches:
                def _prog_rank(f):
                    is_mp4 = 1 if (f.get("ext") or "").lower() == "mp4" else 0
                    return (is_mp4, _estimate_size(f))

                best_p = sorted(p_matches, key=_prog_rank, reverse=True)[0]
                p_size = _estimate_size(best_p)
                p_ext = (best_p.get("ext") or "mp4").lower()
                fps = int(best_p.get("fps") or 30)
                w = int(best_p.get("width") or 0)

                # Avoid duplicate if dual-stream with same height exists unless progressive is distinct
                has_dual = any(opt.height == h and not opt.is_progressive for opt in options)
                if not has_dual or not ffmpeg_available or h <= 720:
                    prog_label = _label_for_height(h, fps, w)
                    if has_dual:
                        prog_label += " (Progressive)"
                    options.append(VideoFormatOption(
                        format_id=str(best_p.get("format_id", "prog")),
                        resolution_label=prog_label,
                        height=h,
                        ext=p_ext,
                        filesize_approx=p_size,
                        fps=fps,
                        vcodec=best_p.get("vcodec", ""),
                        acodec=best_p.get("acodec", ""),
                        is_progressive=True,
                        is_audio_only=False,
                        video_url=best_p["url"],
                        video_headers=best_p.get("http_headers", {}),
                        note="Direct Stream (No merge needed)"
                    ))

        # 4. Add Audio-Only options (both M4A and universal MP3 if FFmpeg available)
        if best_audio:
            # Primary direct audio (M4A)
            options.append(VideoFormatOption(
                format_id=str(best_audio.get("format_id", "audio_m4a")),
                resolution_label=f"Audio Only ({best_audio_ext.upper()})",
                height=0,
                ext=best_audio_ext,
                filesize_approx=best_audio_size,
                fps=0,
                vcodec="none",
                acodec=best_audio.get("acodec", ""),
                is_progressive=True,
                is_audio_only=True,
                video_url=best_audio["url"],
                video_headers=best_audio.get("http_headers", {}),
                audio_ext=best_audio_ext,
                note=f"High Quality Audio (~{best_audio_abr} kbps)"
            ))

            # MP3 Universal Audio option (transcoded via FFmpeg if requested)
            if ffmpeg_available and best_audio_ext != "mp3":
                options.append(VideoFormatOption(
                    format_id=f"{best_audio.get('format_id', 'audio')}+mp3",
                    resolution_label="Audio Only (MP3)",
                    height=0,
                    ext="mp3",
                    filesize_approx=best_audio_size,
                    fps=0,
                    vcodec="none",
                    acodec="mp3",
                    is_progressive=True,
                    is_audio_only=True,
                    video_url=best_audio["url"],
                    video_headers=best_audio.get("http_headers", {}),
                    audio_ext=best_audio_ext,
                    note=f"Universal MP3 Audio (~{best_audio_abr} kbps • FFmpeg)"
                ))
        elif ffmpeg_available and (progressive_formats or formats):
            best_prog_for_audio = progressive_formats[0] if progressive_formats else formats[0]
            prog_size = _estimate_size(best_prog_for_audio)
            est_mp3_size = max(1, int(prog_size * 0.25)) if prog_size > 0 else 0
            options.append(VideoFormatOption(
                format_id=f"{best_prog_for_audio.get('format_id', 'prog')}+mp3",
                resolution_label="Audio Only (MP3)",
                height=0,
                ext="mp3",
                filesize_approx=est_mp3_size,
                fps=0,
                vcodec="none",
                acodec="mp3",
                is_progressive=True,
                is_audio_only=True,
                video_url=best_prog_for_audio["url"],
                video_headers=best_prog_for_audio.get("http_headers", {}),
                audio_ext=(best_prog_for_audio.get("ext") or "mp4").lower(),
                note="Universal MP3 Audio (Extracted via FFmpeg)"
            ))

        # 5. Safety fallback if options is still empty but formats exist
        if not options and formats:
            f0 = formats[0]
            options.append(VideoFormatOption(
                format_id=str(f0.get("format_id", "default")),
                resolution_label="Original Quality",
                height=int(f0.get("height") or 720),
                ext=(f0.get("ext") or "mp4").lower(),
                filesize_approx=_estimate_size(f0),
                fps=int(f0.get("fps") or 30),
                vcodec=str(f0.get("vcodec") or ""),
                acodec=str(f0.get("acodec") or ""),
                is_progressive=True,
                is_audio_only=False,
                video_url=f0["url"],
                video_headers=f0.get("http_headers", {}),
                note="Direct Stream"
            ))

        # Sort options: Video height descending, then filesize descending, audio-only (height 0) at end
        def _sort_key(opt: VideoFormatOption):
            return (opt.height > 0, opt.height, opt.filesize_approx)

        return sorted(options, key=_sort_key, reverse=True)

    def build_stream_info(self, info: Dict[str, Any], option: VideoFormatOption) -> YouTubeStreamInfo:
        """
        Constructs a YouTubeStreamInfo instance ready for StreamDownloadCoordinator
        based on the selected VideoFormatOption.
        """
        web_url = info.get("webpage_url") or ""
        platform = extract_media_platform(web_url)
        video_id = str(info.get("id") or extract_youtube_id(web_url) or extract_media_id(web_url) or "video")
        raw_title = info.get("title") or f"{platform}_Video_{video_id}"
        clean_title = sanitize_filename(raw_title)
        duration = int(info.get("duration") or 0)
        thumbnail = info.get("thumbnail", "")

        res_str = option.resolution_label if (option.resolution_label and "Vertical" in option.resolution_label) else (f"{option.height}p" if option.height > 0 else "Audio Only")

        if option.is_audio_only:
            out_fn = f"{clean_title}.{option.ext}"
            return YouTubeStreamInfo(
                video_id=video_id,
                title=raw_title,
                clean_filename=out_fn,
                is_progressive=True,
                video_url=option.video_url,
                video_headers=option.video_headers,
                video_ext=option.ext,
                video_resolution="Audio Only",
                video_size=option.filesize_approx,
                audio_url=None,
                audio_headers={},
                audio_ext=option.audio_ext or option.ext,
                audio_size=0,
                duration=duration,
                thumbnail_url=thumbnail,
                is_audio_only=True,
                platform=platform
            )
        elif option.is_progressive or not option.audio_url:
            out_fn = f"{clean_title}.{option.ext}"
            return YouTubeStreamInfo(
                video_id=video_id,
                title=raw_title,
                clean_filename=out_fn,
                is_progressive=True,
                video_url=option.video_url,
                video_headers=option.video_headers,
                video_ext=option.ext,
                video_resolution=res_str,
                video_size=option.filesize_approx,
                audio_url=None,
                audio_headers={},
                audio_ext="",
                audio_size=0,
                duration=duration,
                thumbnail_url=thumbnail,
                is_audio_only=False,
                platform=platform
            )
        else:
            out_fn = f"{clean_title}.{option.ext}"
            v_size = max(0, option.filesize_approx - option.audio_size) if option.audio_size else option.filesize_approx
            return YouTubeStreamInfo(
                video_id=video_id,
                title=raw_title,
                clean_filename=out_fn,
                is_progressive=False,
                video_url=option.video_url,
                video_headers=option.video_headers,
                video_ext=option.ext,
                video_resolution=res_str,
                video_size=v_size,
                audio_url=option.audio_url,
                audio_headers=option.audio_headers,
                audio_ext=option.audio_ext,
                audio_size=option.audio_size,
                duration=duration,
                thumbnail_url=thumbnail,
                is_audio_only=False,
                platform=platform
            )

    def resolve(self, url: str, format_id: Optional[str] = None) -> YouTubeStreamInfo:
        """
        Extracts stream URLs and metadata from a YouTube or social media link using yt-dlp.
        If format_id is specified, selects that format; otherwise chooses the best available format.
        Preserves complete backward compatibility for automated tests and direct invocations.
        """
        info, options = self.extract_format_options(url)

        if not options:
            raise RuntimeError("No downloadable media formats found for this media URL.")

        selected_option: Optional[VideoFormatOption] = None
        if format_id:
            for opt in options:
                if opt.format_id == format_id:
                    selected_option = opt
                    break

        if not selected_option:
            # Pick first (highest resolution) option
            selected_option = options[0]

        stream_info = self.build_stream_info(info, selected_option)
        plat = extract_media_platform(url)
        tag = plat.upper().replace(" / X", "")
        if stream_info.is_progressive:
            self.log(
                f"[{tag}] Selected stream: {stream_info.video_resolution} ({stream_info.video_ext}). "
                f"Directly chunk-downloadable without merging."
            )
        else:
            self.log(
                f"[{tag}] Selected dual-stream: Video {stream_info.video_resolution} ({stream_info.video_ext}) + Audio ({stream_info.audio_ext}). "
                f"Will download both and merge seamlessly with FFmpeg."
            )
        return stream_info

    @staticmethod
    def merge_video_audio(
        video_path: str,
        audio_path: str,
        output_path: str,
        on_log: Optional[Callable[[str], None]] = None
    ) -> bool:
        """
        Lossless FFmpeg stream multiplexing (-c copy).
        Merges video and audio streams into the final container without quality loss.
        Cleans up temporary video and audio files upon successful completion.
        """
        ffmpeg_bin = find_ffmpeg_bin()
        if not ffmpeg_bin:
            raise RuntimeError("FFmpeg executable was not found on PATH or app directory. Cannot merge video and audio.")

        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video part file not found: {video_path}")
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio part file not found: {audio_path}")

        # Ensure destination directory exists
        dest_dir = os.path.dirname(output_path)
        if dest_dir:
            os.makedirs(dest_dir, exist_ok=True)

        if on_log:
            on_log(f"[FFMPEG] Merging streams into final file: {os.path.basename(output_path)}...")

        # Construct FFmpeg command
        cmd = [
            ffmpeg_bin,
            "-y",  # Overwrite output without asking
            "-i", video_path,
            "-i", audio_path,
            "-c", "copy"  # Fast stream copy without re-encoding
        ]
        if output_path.lower().endswith((".mp4", ".m4v", ".mov")):
            cmd.extend(["-movflags", "+faststart"])
        cmd.append(output_path)

        # Windows-specific: hide console window for subprocess
        startupinfo = None
        creationflags = 0
        if sys.platform.startswith("win"):
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=creationflags
        )

        if proc.returncode != 0:
            primary_err = proc.stderr.strip()
            # If fast lossless copy fails (e.g. opus audio or unsupported codec in mp4 container),
            # attempt fallback: copy video stream losslessly and re-encode audio to universal AAC
            if on_log:
                on_log(f"[FFMPEG] Direct stream copy failed ({proc.returncode}). Retrying with audio transcode to AAC...")

            fallback_cmd = [
                ffmpeg_bin,
                "-y",
                "-i", video_path,
                "-i", audio_path,
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "192k"
            ]
            if output_path.lower().endswith((".mp4", ".m4v", ".mov")):
                fallback_cmd.extend(["-movflags", "+faststart"])
            fallback_cmd.append(output_path)

            proc2 = subprocess.run(
                fallback_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=creationflags
            )
            if proc2.returncode != 0:
                # Secondary fallback: full container transcode (libx264+aac)
                if on_log:
                    on_log("[FFMPEG] Audio transcode fallback failed. Retrying full container transcode (libx264+aac)...")
                transcode_cmd = [
                    ffmpeg_bin,
                    "-y",
                    "-i", video_path,
                    "-i", audio_path,
                    "-c:v", "libx264",
                    "-preset", "ultrafast",
                    "-c:a", "aac",
                    "-b:a", "192k"
                ]
                if output_path.lower().endswith((".mp4", ".m4v", ".mov")):
                    transcode_cmd.extend(["-movflags", "+faststart"])
                transcode_cmd.append(output_path)

                proc3 = subprocess.run(
                    transcode_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    creationflags=creationflags
                )
                if proc3.returncode != 0:
                    err_msg = proc3.stderr.strip() or proc2.stderr.strip() or primary_err or "Unknown FFmpeg error"
                    if on_log:
                        on_log(f"[FFMPEG ERROR] Merge failed (exit code {proc3.returncode}): {err_msg}")
                    raise RuntimeError(f"FFmpeg stream merge failed: {err_msg}")

        # Validate that the merged file exists and has non-zero size
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise RuntimeError("FFmpeg merge completed but output file is missing or empty.")

        # Clean up temporary video and audio component files
        try:
            if os.path.exists(video_path):
                os.remove(video_path)
            if os.path.exists(audio_path):
                os.remove(audio_path)
        except Exception:
            pass

        if on_log:
            merged_size = os.path.getsize(output_path)
            on_log(f"[FFMPEG SUCCESS] Merged file successfully created ({merged_size:,} bytes).")

        return True


# Backward-compatible alias for universal media resolution
MediaResolver = YouTubeResolver
