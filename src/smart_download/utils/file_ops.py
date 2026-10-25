"""
File categorization, destination path resolving, and OS shell launch utilities for Smart Download (SD).
"""
import os
import sys
import subprocess
from typing import Tuple, Dict

from ..config import IS_WINDOWS
from .magic_detector import MagicBytesDetector
from .archive_utils import calculate_file_integrity, auto_unpack_archive


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


__all__ = [
    "MagicBytesDetector",
    "calculate_file_integrity",
    "auto_unpack_archive",
    "get_file_category_and_icon",
    "CATEGORY_SUBFOLDERS",
    "resolve_categorized_path",
    "open_downloaded_file",
    "open_containing_folder",
]
