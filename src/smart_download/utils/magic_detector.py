"""
Magic bytes file type detector for Smart Download (SD).
"""
import os
from typing import Optional, Tuple


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


__all__ = ["MagicBytesDetector"]
