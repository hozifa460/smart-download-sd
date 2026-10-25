"""
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


def format_speed(speed: Any, allow_unlimited: bool = False) -> str:
    """Format speed value in bytes/sec into a human-readable string (e.g. '0 B/s', '500 B/s', '1.0 KB/s', '2.50 MB/s', '1.00 GB/s')."""
    try:
        val = float(speed)
    except (TypeError, ValueError):
        val = 0.0

    if val <= 0:
        return "Unlimited" if allow_unlimited else "0 B/s"

    if val >= 1024 * 1024 * 1024:
        return f"{val / (1024 * 1024 * 1024):.2f} GB/s"
    if val >= 1024 * 1024:
        return f"{val / (1024 * 1024):.2f} MB/s"
    if val >= 1024:
        return f"{val / 1024:.1f} KB/s"
    return f"{val:.0f} B/s"


