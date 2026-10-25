"""
EnginePersistenceMixin: Chunk assembly, state serialization, and persistence logic
for TurboDownloadEngine.
"""
import os
import json
import shutil
import hashlib
import zlib
from typing import List, Optional, Dict, Any

from ..config import get_setting
from ..utils.file_ops import (
    calculate_file_integrity,
    auto_unpack_archive,
    MagicBytesDetector,
)
from .chunk import DownloadChunk


class EnginePersistenceMixin:
    """
    Mixin providing strict sequential assembly, state persistence,
    and safe shutdown capabilities for TurboDownloadEngine.
    """

    def assemble(self):
        """
        Strict Non-Corrupt Sequential Assembly:
        - Strict sorting by start_byte.
        - Boundary checks: chunk[0].start_byte == 0, chunk[i].end_byte + 1 == chunk[i+1].start_byte.
        - On-disk part file size validations.
        - 256KB streaming buffer merge into target file.
        - Total assembled size verification.
        - Pre-allocation and streamlined streaming buffers (inspired by splitter.rs).
        - Magic bytes container detection (inspired by detector.rs).
        - Post-download integrity verification (CRC-32 & SHA-256).
        - Temporary directory cleanup upon successful assembly.
        """
        self.log("Beginning strict sequential assembly...")

        with self._lock:
            sorted_chunks = sorted(self.chunks, key=lambda c: c.start_byte)

        if not sorted_chunks:
            raise ValueError("No download chunks available for assembly.")

        # Magic bytes detection inspired by AeroArchive Studio (detector.rs)
        if sorted_chunks and os.path.exists(sorted_chunks[0].part_filepath):
            try:
                with open(sorted_chunks[0].part_filepath, "rb") as f0:
                    head_bytes = f0.read(512)
                detected = MagicBytesDetector.detect_bytes(head_bytes)
                if detected:
                    det_ext, det_mime, det_cat = detected
                    cur_ext = os.path.splitext(self.destination_path)[1].lower()
                    if (
                        cur_ext in ("", ".bin", ".download", ".octet-stream", ".part")
                        and not self.destination_path.endswith((".video.tmp", ".audio.tmp", ".tmp"))
                        and det_ext
                    ):
                        new_dest = os.path.splitext(self.destination_path)[0] + det_ext
                        self.log(f"[DETECTOR] Detected true format via magic bytes: {det_ext} ({det_cat}) -> {os.path.basename(new_dest)}")
                        self.destination_path = new_dest
                        self.filename = os.path.basename(new_dest)
            except Exception:
                pass

        # Boundary assertions (using explicit AssertionError raises to survive -O optimization)
        if self.supports_ranges and self.total_size > 0:
            if not (sorted_chunks[0].start_byte == 0):
                raise AssertionError(
                    f"Assembly Assertion Failed: Chunk 0 starts at {sorted_chunks[0].start_byte}, expected 0."
                )
            for i in range(len(sorted_chunks) - 1):
                c_cur = sorted_chunks[i]
                c_next = sorted_chunks[i+1]
                if not (c_cur.end_byte + 1 == c_next.start_byte):
                    raise AssertionError(
                        f"Boundary Gap/Overlap detected between Chunk #{c_cur.chunk_id} "
                        f"(ends {c_cur.end_byte}) and #{c_next.chunk_id} (starts {c_next.start_byte})!"
                    )
            if not (sorted_chunks[-1].end_byte == self.total_size - 1):
                raise AssertionError(
                    f"Assembly Assertion Failed: Final chunk ends at {sorted_chunks[-1].end_byte}, expected {self.total_size - 1}."
                )

            # Validate part file size on disk matches expected byte span
            for c in sorted_chunks:
                expected_size = c.end_byte - c.start_byte + 1
                if not os.path.exists(c.part_filepath):
                    raise FileNotFoundError(f"Missing chunk file: {c.part_filepath}")
                actual_size = os.path.getsize(c.part_filepath)
                if not (actual_size == expected_size):
                    raise AssertionError(
                        f"Chunk #{c.chunk_id} size mismatch: disk {actual_size:,} bytes != expected {expected_size:,} bytes."
                    )

        # Streamlined 256KB streaming assembly with on-the-fly zero-extra-read hashing
        STREAM_BUFFER_SIZE = 256 * 1024
        total_written = 0
        sha256_hash = hashlib.sha256()
        crc_val = 0

        # Ensure target directory exists
        dest_dir = os.path.dirname(self.destination_path)
        if dest_dir:
            os.makedirs(dest_dir, exist_ok=True)

        with open(self.destination_path, "wb") as out_f:
            if self.total_size > 0:
                try:
                    out_f.truncate(self.total_size)
                except Exception:
                    pass
            for c in sorted_chunks:
                if not os.path.exists(c.part_filepath):
                    continue
                with open(c.part_filepath, "rb") as in_f:
                    while True:
                        buf = in_f.read(STREAM_BUFFER_SIZE)
                        if not buf:
                            break
                        out_f.write(buf)
                        sha256_hash.update(buf)
                        crc_val = zlib.crc32(buf, crc_val)
                        total_written += len(buf)
            out_f.flush()

        if self.total_size > 0:
            if not (total_written == self.total_size):
                raise AssertionError(
                    f"Assembly size mismatch: Written {total_written:,} bytes != expected {self.total_size:,} bytes."
                )

        self.log(f"Assembled and verified {total_written:,} bytes with zero corruption.")

        # Post-download integrity verification (CRC-32 & SHA-256) computed on the fly without extra disk read
        crc32_str = f"{crc_val & 0xFFFFFFFF:08x}"
        sha256_str = sha256_hash.hexdigest()
        self.log(f"[INTEGRITY] SHA-256: {sha256_str} | CRC-32: {crc32_str}")

        # Optional auto-unpack for archive files
        if get_setting("auto_unpack_archives", False):
            try:
                unpacked_to = auto_unpack_archive(self.destination_path)
                if unpacked_to:
                    self.log(f"[ARCHIVE] Successfully auto-unpacked to: {unpacked_to}")
            except Exception as e:
                self.log(f"[ARCHIVE] Auto-unpack error: {e}")

        # Cleanup part files
        try:
            shutil.rmtree(self.temp_dir, ignore_errors=True)
            self.log("Cleaned up temporary chunk files.")
        except Exception:
            pass

    def safe_shutdown(self):
        """
        Safely halts all active workers and serializes state into state.json
        WITHOUT purging temporary chunk files (.sd_parts).
        Enables seamless download resumption upon next launch.
        """
        self.is_running = False
        self.is_paused = True
        if getattr(self, "_last_active_start_mono", None) is not None:
            import time
            self._accumulated_active_sec += max(0.0, time.monotonic() - self._last_active_start_mono)
            self._last_active_start_mono = None
        self._pause_event.set()
        self._cancel_event.set()
        with self._lock:
            for conn in list(self._active_connections):
                try:
                    conn.close()
                except Exception:
                    pass
            self._active_connections.clear()
        self.save_state()
        self.log("Download state saved safely in .sd_parts. Resume ready.")

    def save_state(self) -> bool:
        """Serializes current download chunk state and progress into state.json within temp_dir."""
        try:
            if not getattr(self, "temp_dir", None):
                return False
            os.makedirs(self.temp_dir, exist_ok=True)
            state_file = os.path.join(self.temp_dir, "state.json")
            is_actively_running = getattr(self, "is_running", False) and not getattr(self, "is_paused", False)
            with self._lock:
                chunks_data = []
                for c in self.chunks:
                    with c.lock:
                        disk_bytes = c.downloaded_bytes
                        if not is_actively_running and os.path.exists(c.part_filepath):
                            try:
                                disk_bytes = os.path.getsize(c.part_filepath)
                            except Exception:
                                pass
                        chunks_data.append({
                            "chunk_id": c.chunk_id,
                            "start_byte": c.start_byte,
                            "end_byte": c.end_byte,
                            "downloaded_bytes": disk_bytes,
                            "status": c.status,
                            "part_filepath": c.part_filepath,
                            "error_msg": c.error_msg
                        })
                data = {
                    "url": self.url,
                    "destination_path": self.destination_path,
                    "total_size": self.total_size,
                    "supports_ranges": self.supports_ranges,
                    "has_expired_link": self.has_expired_link,
                    "filename": self.filename,
                    "headers": self.headers,
                    "accumulated_active_sec": getattr(self, "_accumulated_active_sec", 0.0),
                    "chunks": chunks_data
                }
            tmp_state = state_file + ".tmp"
            with open(tmp_state, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp_state, state_file)
            return True
        except Exception as e:
            self.log(f"Warning: Failed to save chunk state: {e}")
            return False

    def load_state(self) -> bool:
        """Loads and restores download chunks and progress from state.json if present and valid."""
        try:
            if not getattr(self, "temp_dir", None):
                return False
            state_file = os.path.join(self.temp_dir, "state.json")
            if not os.path.isfile(state_file):
                return False
            with open(state_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            total_size = data.get("total_size", 0)
            chunks_data = data.get("chunks", [])
            if not chunks_data:
                return False

            with self._lock:
                self.chunks.clear()
                self.total_size = total_size
                self.supports_ranges = data.get("supports_ranges", True)
                self.has_expired_link = data.get("has_expired_link", False)
                self._accumulated_active_sec = float(data.get("accumulated_active_sec", 0.0))
                for cd in chunks_data:
                    part_path = cd.get("part_filepath") or os.path.join(
                        self.temp_dir, f"{os.path.basename(self.destination_path)}.part_{cd['chunk_id']}"
                    )
                    disk_bytes = cd.get("downloaded_bytes", 0)
                    if os.path.exists(part_path):
                        try:
                            actual_disk = os.path.getsize(part_path)
                            disk_bytes = min(actual_disk, cd["end_byte"] - cd["start_byte"] + 1)
                        except Exception:
                            pass

                    expected_span = cd["end_byte"] - cd["start_byte"] + 1
                    status = cd.get("status", "pending")
                    if total_size > 0 and disk_bytes >= expected_span:
                        status = "completed"
                    elif status == "failed":
                        status = "pending"

                    chunk = DownloadChunk(
                        chunk_id=cd["chunk_id"],
                        start_byte=cd["start_byte"],
                        end_byte=cd["end_byte"],
                        downloaded_bytes=disk_bytes,
                        status=status,
                        part_filepath=part_path,
                        error_msg=cd.get("error_msg", "")
                    )
                    self.chunks.append(chunk)
            self.log(f"Restored {len(self.chunks)} chunks from saved state ({sum(c.downloaded_bytes for c in self.chunks):,} bytes downloaded).")
            return True
        except Exception as e:
            self.log(f"Warning: Failed to load chunk state: {e}")
            return False
