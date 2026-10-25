"""
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

class MagicBytesDetector:
    """
    Magic-bytes file type detector inspired by AeroArchive Studio (detector.rs).
    Detects true binary container and format from initial bytes (header signature),
    independent of generic URLs or query parameters.
    """
    SIGNATURES = [
        # (magic_bytes, offset, extension, mime_type, category)
        (b"PK\x03\x04", 0, ".zip", "application/zip", "Compressed"),
        (b"PK\x05\x06", 0, ".zip", "application/zip", "Compressed"),
        (b"PK\x07\x08", 0, ".zip", "application/zip", "Compressed"),
        (b"\x37\x7A\xBC\xAF\x27\x1C", 0, ".7z", "application/x-7z-compressed", "Compressed"),
        (b"Rar!\x1A\x07\x00", 0, ".rar", "application/x-rar-compressed", "Compressed"),
        (b"Rar!\x1A\x07\x01\x00", 0, ".rar", "application/x-rar-compressed", "Compressed"),
        (b"\x1F\x8B", 0, ".gz", "application/gzip", "Compressed"),
        (b"%PDF-", 0, ".pdf", "application/pdf", "Documents"),
        (b"\x89PNG\r\n\x1a\n", 0, ".png", "image/png", "Images"),
        (b"\xFF\xD8\xFF", 0, ".jpg", "image/jpeg", "Images"),
        (b"GIF87a", 0, ".gif", "image/gif", "Images"),
        (b"GIF89a", 0, ".gif", "image/gif", "Images"),
        (b"\x1A\x45\xDF\xA3", 0, ".mkv", "video/x-matroska", "Video"),
        (b"ID3", 0, ".mp3", "audio/mpeg", "Audio"),
        (b"\xFF\xFB", 0, ".mp3", "audio/mpeg", "Audio"),
        (b"\xFF\xF3", 0, ".mp3", "audio/mpeg", "Audio"),
        (b"MZ", 0, ".exe", "application/x-msdownload", "Programs"),
        (b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1", 0, ".msi", "application/x-msi", "Programs"),
    ]

    @classmethod
    def detect_bytes(cls, data: bytes) -> Optional[Tuple[str, str, str]]:
        """
        Returns (extension, mime_type, category) if recognized, or None.
        """
        if not data or len(data) < 2:
            return None

        # Check MP4 / MOV (offset 4: ftyp)
        if len(data) >= 12 and data[4:8] == b"ftyp":
            brand = data[8:12].lower()
            if brand in (b"qt  ", b"moov"):
                return (".mov", "video/quicktime", "Video")
            return (".mp4", "video/mp4", "Video")

        # Check RIFF subtypes (WEBP, WAV, AVI)
        if len(data) >= 12 and data[:4] == b"RIFF":
            form_type = data[8:12]
            if form_type == b"WEBP":
                return (".webp", "image/webp", "Images")
            elif form_type == b"WAVE":
                return (".wav", "audio/wav", "Audio")
            elif form_type == b"AVI ":
                return (".avi", "video/x-msvideo", "Video")

        # Check TAR (offset 257: ustar)
        if len(data) >= 265 and data[257:262] == b"ustar":
            return (".tar", "application/x-tar", "Compressed")

        # Check ISO 9660 (offset 32768: CD001)
        if len(data) >= 32773 and data[32768:32773] == b"CD001":
            return (".iso", "application/x-iso9660-image", "General")

        for sig, offset, ext, mime, cat in cls.SIGNATURES:
            sig_len = len(sig)
            if len(data) >= offset + sig_len and data[offset:offset+sig_len] == sig:
                return (ext, mime, cat)

        return None

    @classmethod
    def detect_file(cls, filepath: str) -> Optional[Tuple[str, str, str]]:
        if not os.path.isfile(filepath):
            return None
        try:
            with open(filepath, "rb") as f:
                header = f.read(512)
            return cls.detect_bytes(header)
        except Exception:
            return None


def calculate_file_integrity(filepath: str) -> Dict[str, str]:
    """
    Computes CRC-32 and SHA-256 integrity hashes for a file.
    Uses 256KB streaming blocks for low memory overhead and high I/O throughput.
    """
    if not os.path.isfile(filepath):
        return {"crc32": "", "sha256": ""}
    crc = 0
    sha = hashlib.sha256()
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(256 * 1024)
            if not chunk:
                break
            crc = zlib.crc32(chunk, crc)
            sha.update(chunk)
    return {
        "crc32": f"{crc & 0xFFFFFFFF:08X}",
        "sha256": sha.hexdigest().lower()
    }


def auto_unpack_archive(archive_path: str, destination_dir: Optional[str] = None) -> Optional[str]:
    """
    Extracts downloaded archive (.zip, .tar, .tar.gz, .tgz, .7z) into a dedicated folder.
    Returns path to extracted folder on success, or None.
    """
    if not os.path.isfile(archive_path):
        return None
    stem = os.path.splitext(os.path.basename(archive_path))[0]
    if archive_path.lower().endswith(".tar.gz"):
        stem = os.path.basename(archive_path)[:-7]
    base_dir = destination_dir or os.path.dirname(archive_path)
    out_dir = os.path.join(base_dir, stem)
    try:
        os.makedirs(out_dir, exist_ok=True)
        # 1. 7z / rar extraction via tar.exe (Windows 10/11 built-in libarchive bsdtar) or 7z CLI
        if archive_path.lower().endswith((".7z", ".rar")):
            tar_tool = shutil.which("tar")
            if tar_tool:
                try:
                    res = subprocess.run([tar_tool, "-xf", archive_path, "-C", out_dir], capture_output=True, timeout=60)
                    if res.returncode == 0:
                        return out_dir
                except Exception:
                    pass
            seven_z = shutil.which("7z") or shutil.which("7za")
            if seven_z:
                try:
                    res = subprocess.run([seven_z, "x", "-y", f"-o{out_dir}", archive_path], capture_output=True, timeout=60)
                    if res.returncode == 0:
                        return out_dir
                except Exception:
                    pass

        # 2. Standard zip archives
        if zipfile.is_zipfile(archive_path):
            with zipfile.ZipFile(archive_path, 'r') as zf:
                zf.extractall(out_dir)
            return out_dir
        # 3. Standard tar / tar.gz / tgz archives
        elif tarfile.is_tarfile(archive_path):
            with tarfile.open(archive_path, 'r:*') as tf:
                if hasattr(tarfile, 'data_filter'):
                    tf.extractall(out_dir, filter='data')
                else:
                    tf.extractall(out_dir)
            return out_dir
        else:
            try:
                shutil.unpack_archive(archive_path, out_dir)
                return out_dir
            except Exception:
                pass
    except Exception:
        pass
    return None


# ======================================================================================
# 3E. TDM-STYLE DOWNLOAD CONFIRMATION MODAL (SAFE, GRAB-FREE, BORDERLESS COMPATIBLE)
# ======================================================================================

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

