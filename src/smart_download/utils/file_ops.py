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


def generate_unique_destination_path(dest_path: str) -> str:
    """
    If dest_path already exists on disk and is not an incomplete download (does not have .sd_parts or .tdm_parts),
    generates a non-colliding filename e.g. 'Title (1).mp4', 'Title (2).mp4'.
    """
    if not dest_path:
        return dest_path

    parts_dir = dest_path + ".sd_parts"
    tdm_parts = dest_path + ".tdm_parts"
    if os.path.isdir(parts_dir) or os.path.isdir(tdm_parts):
        return dest_path

    if not os.path.exists(dest_path):
        return dest_path

    dirname, filename = os.path.split(dest_path)
    base, ext = os.path.splitext(filename)

    import re
    m = re.match(r'^(.*?)\s*\((\d+)\)$', base)
    if m:
        root_base = m.group(1).rstrip()
        counter = int(m.group(2)) + 1
    else:
        root_base = base
        counter = 1

    while True:
        candidate = os.path.join(dirname, f"{root_base} ({counter}){ext}")
        c_parts = candidate + ".sd_parts"
        if not os.path.exists(candidate) and not os.path.isdir(c_parts):
            return candidate
        counter += 1


def apply_media_filename_tags(
    dest_path: str,
    quality_label: Optional[str] = None,
    is_sub_burned: bool = False,
    ext: Optional[str] = None
) -> str:
    """
    Formats destination path to include quality tag (e.g. [1080p], [720p], [Audio])
    and subtitle burn-in tag [Sub], stripping any older tags first.
    """
    if not dest_path:
        return dest_path

    import re
    dirname, filename = os.path.split(dest_path)
    base, old_ext = os.path.splitext(filename)

    clean_base = re.sub(r'\s*\[(?:\d{3,4}p|2160p|1440p|1080p|720p|480p|360p|240p|144p|4k|8k|audio|mp3|m4a)\]', '', base, flags=re.IGNORECASE)
    clean_base = re.sub(r'\s*\[sub\]', '', clean_base, flags=re.IGNORECASE)
    clean_base = clean_base.strip()

    q_tag = ""
    if quality_label:
        ql = str(quality_label).strip()
        qm = re.search(r'(\d{3,4}p|4K|8K)', ql, flags=re.IGNORECASE)
        if qm:
            q_tag = f"[{qm.group(1)}]"
        elif "audio" in ql.lower():
            q_tag = "[Audio]"
        elif ql:
            clean_ql = re.sub(r'[\(\)\[\]]', '', ql).split('—')[0].split('-')[0].strip()
            if clean_ql:
                q_tag = f"[{clean_ql}]"

    sub_tag = "[Sub]" if is_sub_burned else ""

    parts = [clean_base]
    if q_tag:
        parts.append(q_tag)
    if sub_tag:
        parts.append(sub_tag)

    new_base = " ".join(parts).strip()
    target_ext = ext if ext else old_ext
    if target_ext and not target_ext.startswith("."):
        target_ext = "." + target_ext

    return os.path.join(dirname, f"{new_base}{target_ext}")


__all__ = [
    "MagicBytesDetector",
    "calculate_file_integrity",
    "auto_unpack_archive",
    "get_file_category_and_icon",
    "CATEGORY_SUBFOLDERS",
    "resolve_categorized_path",
    "open_downloaded_file",
    "open_containing_folder",
    "generate_unique_destination_path",
    "apply_media_filename_tags",
]

