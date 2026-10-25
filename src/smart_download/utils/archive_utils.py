"""
File integrity hashing and archive unpacking utilities for Smart Download (SD).
"""
import os
import hashlib
import subprocess
import zipfile
import tarfile
import zlib
import shutil
from typing import Optional, Dict


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


def _safe_extract_zip(zf: zipfile.ZipFile, out_dir: str):
    """
    Safely extracts all members of a ZipFile, blocking Zip-Slip path traversal.
    Validates that every member's resolved path resides strictly within out_dir.
    """
    abs_out_dir = os.path.abspath(out_dir)
    out_drive = os.path.splitdrive(abs_out_dir)[0].lower()
    for member in zf.infolist():
        norm_name = member.filename.replace("\\", "/")
        if ".." in norm_name.split("/"):
            raise ValueError(f"Zip Slip path traversal attempt: {member.filename}")
        target_path = os.path.abspath(os.path.join(abs_out_dir, member.filename))
        if os.path.splitdrive(target_path)[0].lower() != out_drive:
            raise ValueError(f"Zip Slip path traversal attempt: {member.filename}")
        if os.path.commonpath([abs_out_dir, target_path]) != abs_out_dir:
            raise ValueError(f"Zip Slip path traversal attempt: {member.filename}")
    zf.extractall(out_dir)


def _safe_extract_tar(tf: tarfile.TarFile, out_dir: str):
    """
    Safely extracts all members of a TarFile, blocking Tar-Slip path traversal.
    Validates that every member's resolved path resides strictly within out_dir,
    and inspects symlink/hardlink targets.
    """
    abs_out_dir = os.path.abspath(out_dir)
    out_drive = os.path.splitdrive(abs_out_dir)[0].lower()
    for member in tf.getmembers():
        norm_name = member.name.replace("\\", "/")
        if ".." in norm_name.split("/"):
            raise ValueError(f"Tar Slip path traversal attempt: {member.name}")
        target_path = os.path.abspath(os.path.join(abs_out_dir, member.name))
        if os.path.splitdrive(target_path)[0].lower() != out_drive:
            raise ValueError(f"Tar Slip path traversal attempt: {member.name}")
        if os.path.commonpath([abs_out_dir, target_path]) != abs_out_dir:
            raise ValueError(f"Tar Slip path traversal attempt: {member.name}")
        if (member.issym() or member.islnk()) and member.linkname:
            norm_link = member.linkname.replace("\\", "/")
            if ".." in norm_link.split("/"):
                raise ValueError(f"Tar Slip path traversal attempt: {member.name} -> {member.linkname}")
            link_target = os.path.abspath(os.path.join(os.path.dirname(target_path), member.linkname))
            if os.path.splitdrive(link_target)[0].lower() != out_drive or os.path.commonpath([abs_out_dir, link_target]) != abs_out_dir:
                raise ValueError(f"Tar Slip path traversal attempt: {member.name} -> {member.linkname}")
    if hasattr(tarfile, 'data_filter'):
        tf.extractall(out_dir, filter='data')
    else:
        tf.extractall(out_dir)


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

        # 2. Standard zip archives with Zip-Slip protection
        if zipfile.is_zipfile(archive_path):
            with zipfile.ZipFile(archive_path, 'r') as zf:
                _safe_extract_zip(zf, out_dir)
            return out_dir
        # 3. Standard tar / tar.gz / tgz archives with Tar-Slip protection
        elif tarfile.is_tarfile(archive_path):
            with tarfile.open(archive_path, 'r:*') as tf:
                _safe_extract_tar(tf, out_dir)
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


__all__ = ["calculate_file_integrity", "auto_unpack_archive", "_safe_extract_zip", "_safe_extract_tar"]
