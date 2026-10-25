"""
TurboDownloadEngine: Multi-threaded dynamic chunking, resume, assembly, and throttling download engine.
"""
import os
import sys
import time
import math
import urllib.request
import urllib.error
import urllib.parse
import threading
import ssl
import shutil
import tempfile
import json
from typing import List, Optional, Callable, Dict, Any, Union, Tuple

from ..config import (
    get_resource_path,
    get_setting,
    CHUNK_SIZE_KB,
    MAX_CONCURRENT_CHUNKS,
    DEFAULT_CHUNKS,
    MIN_CHUNK_BYTES,
    BUFFER_SIZE,
)
from .rate_limiter import TokenBucketRateLimiter
from .chunk import DownloadChunk, get_permissive_ssl_context
from .html_resolver import validate_refresh_url
from .engine_persistence import EnginePersistenceMixin
from ..utils.url_utils import (
    is_downloadable_url,
    derive_download_filename,
    is_potential_html_url,
    parse_filename_from_cd_header,
)
from ..utils.file_ops import (
    calculate_file_integrity,
    auto_unpack_archive,
    MagicBytesDetector,
)

from .engine_workers import EngineWorkersMixin


class TurboDownloadEngine(EngineWorkersMixin, EnginePersistenceMixin):
    """
    High-throughput download engine featuring dynamic chunking, streaming buffers, and rate limiting.
    """
    def __init__(
        self,
        url: str,
        destination_path: str,
        max_connections: int = 8,
        min_split_threshold: int = 256 * 1024,  # 256 KB minimum remaining to allow split
        rate_limit_bytes_per_sec: float = 0.0,
        ssl_context: Optional[ssl.SSLContext] = None,
        opener: Optional[urllib.request.OpenerDirector] = None,
        headers: Optional[Dict[str, str]] = None,
        allow_dynamic_split: bool = True,
        on_progress: Optional[Callable] = None,
        on_chunk_update: Optional[Callable] = None,
        on_log: Optional[Callable] = None,
        on_complete: Optional[Callable] = None,
        on_error: Optional[Callable] = None
    ):
        self.url = url
        self.destination_path = destination_path
        self.max_connections = max(1, min(max_connections, 32))
        self.min_split_threshold = max(64 * 1024, min_split_threshold)
        self.rate_limiter = TokenBucketRateLimiter(rate_limit_bytes_per_sec)
        self.ssl_context = ssl_context if ssl_context is not None else get_permissive_ssl_context()
        self.opener = opener if opener is not None else urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=self.ssl_context)
        )
        self.headers: Dict[str, str] = dict(headers) if headers else {}

        # YouTube googlevideo CDN detection and concurrency safety
        self.is_googlevideo = self.is_googlevideo_url(self.url)
        self.allow_dynamic_split = allow_dynamic_split and not self.is_googlevideo
        if self.is_googlevideo:
            # YouTube googlevideo CDN issues HTTP 403 Forbidden on concurrent range requests
            # with the same signed token. Enforce safe concurrency (1 connection) & no dynamic splitting.
            self.max_connections = min(self.max_connections, 1)

        self.on_progress = on_progress
        self.on_chunk_update = on_chunk_update
        self.on_log = on_log
        self.on_complete = on_complete
        self.on_error = on_error

        self.total_size = 0
        self.supports_ranges = False
        self.content_type: str = ""
        self.filename = os.path.basename(destination_path)
        self.temp_dir = destination_path + ".sd_parts"
        for legacy_d in [destination_path + ".tdm_parts", destination_path + ".idm_parts"]:
            if os.path.isdir(legacy_d) and not os.path.exists(self.temp_dir):
                try:
                    os.replace(legacy_d, self.temp_dir)
                    break
                except Exception:
                    pass

        self.chunks: List[DownloadChunk] = []
        self.active_workers: List[threading.Thread] = []
        self._active_connections: List[urllib.request.addinfourl] = []

        self._lock = threading.RLock()
        self._cancel_event = threading.Event()
        self._pause_event = threading.Event()
        self._error_abort_event = threading.Event()
        self.is_running = False
        self.is_paused = False
        self.has_expired_link = False
        self.last_http_status = 0
        self._resume_mode = False

        # Speed calculation metrics
        self.start_time = 0.0
        self.last_speed_check_time = 0.0
        self.last_downloaded_bytes = 0
        self.current_speed = 0.0
        self._accumulated_active_sec = 0.0
        self._last_active_start_mono: Optional[float] = None
        self._session_start_bytes: int = 0

    def log(self, message: str):
        timestamp = time.strftime("%H:%M:%S")
        log_msg = f"[{timestamp}] {message}"
        if self.on_log:
            try:
                self.on_log(log_msg)
            except Exception:
                pass

    def set_speed_limit(self, bytes_per_sec: float):
        """Update speed limit on the fly."""
        self.rate_limiter.set_limit(bytes_per_sec)
        if bytes_per_sec <= 0:
            self.log("Speed limit set to: Unlimited")
        else:
            if bytes_per_sec >= 1024 * 1024:
                self.log(f"Speed limit set to: {bytes_per_sec / (1024*1024):.2f} MB/s")
            else:
                self.log(f"Speed limit set to: {bytes_per_sec / 1024:.1f} KB/s")

    def get_chunks_snapshot(self) -> List[DownloadChunk]:
        """Returns a thread-safe snapshot copy of the current chunk list."""
        with self._lock:
            return list(self.chunks)

    def probe(self):
        """
        Inspect target URL for Content-Length, HTTP 206 Accept-Ranges, and file name.
        Uses HEAD with fallback to GET Range: bytes=0-0 to bypass servers blocking HEAD.
        """
        self.log(f"Probing server capabilities: {self.url}")
        req = self._create_request(method="HEAD")

        head_succeeded = False
        try:
            with urllib.request.urlopen(req, timeout=12, context=self.ssl_context) as resp:
                # Update URL if redirected
                redirected_url = resp.geturl()
                if redirected_url and redirected_url != self.url:
                    self.url = redirected_url
                    if self.is_googlevideo_url(self.url):
                        self.is_googlevideo = True
                        self.max_connections = min(self.max_connections, 1)
                        self.allow_dynamic_split = False

                cl = resp.headers.get("Content-Length")
                ar = resp.headers.get("Accept-Ranges", "").lower()
                raw_ct = resp.headers.get("Content-Type", "")
                self.content_type = raw_ct.split(";")[0].strip().lower()
                self.total_size = int(cl) if cl and cl.isdigit() else 0
                self.supports_ranges = (ar == "bytes") and (self.total_size > 0)

                cd = resp.headers.get("Content-Disposition", "")
                cd_fn = self._parse_filename_from_cd(cd)
                if cd_fn:
                    self.filename = cd_fn
                head_succeeded = True
        except urllib.error.HTTPError as e:
            e.close()
            head_succeeded = False
        except Exception:
            head_succeeded = False

        # If HEAD failed or did not confirm range support, test with GET Range: bytes=0-0
        if not head_succeeded or not self.supports_ranges:
            req = self._create_request()
            req.add_header("Range", "bytes=0-0")
            try:
                with urllib.request.urlopen(req, timeout=12, context=self.ssl_context) as resp:
                    redirected_url = resp.geturl()
                    if redirected_url and redirected_url != self.url:
                        self.url = redirected_url
                        if self.is_googlevideo_url(self.url):
                            self.is_googlevideo = True
                            self.max_connections = min(self.max_connections, 1)
                            self.allow_dynamic_split = False

                    raw_ct = resp.headers.get("Content-Type", "")
                    if raw_ct:
                        self.content_type = raw_ct.split(";")[0].strip().lower()

                    cr = resp.headers.get("Content-Range", "")
                    if "/" in cr:
                        total_str = cr.split("/")[-1].strip()
                        if total_str.isdigit():
                            self.total_size = int(total_str)
                            self.supports_ranges = True
                    elif resp.getcode() == 206:
                        self.supports_ranges = True

                    if not self.total_size and resp.getcode() == 200:
                        cl = resp.headers.get("Content-Length")
                        self.total_size = int(cl) if cl and cl.isdigit() else 0

                    cd = resp.headers.get("Content-Disposition", "")
                    cd_fn = self._parse_filename_from_cd(cd)
                    if cd_fn:
                        self.filename = cd_fn
            except Exception as e:
                if isinstance(e, urllib.error.HTTPError):
                    e.close()
                    if e.code in (401, 403, 410):
                        self.has_expired_link = True
                        self.last_http_status = e.code
                # If GET Range failed and HEAD also failed, attempt a plain GET request
                # without Range to follow redirects and probe headers
                if not head_succeeded:
                    try:
                        req_plain = self._create_request()
                        with urllib.request.urlopen(req_plain, timeout=12, context=self.ssl_context) as resp:
                            redirected_url = resp.geturl()
                            if redirected_url and redirected_url != self.url:
                                self.url = redirected_url
                                if self.is_googlevideo_url(self.url):
                                    self.is_googlevideo = True
                                    self.max_connections = min(self.max_connections, 1)
                                    self.allow_dynamic_split = False

                            raw_ct = resp.headers.get("Content-Type", "")
                            if raw_ct:
                                self.content_type = raw_ct.split(";")[0].strip().lower()

                            cl = resp.headers.get("Content-Length")
                            ar = resp.headers.get("Accept-Ranges", "").lower()
                            self.total_size = int(cl) if cl and cl.isdigit() else 0
                            self.supports_ranges = (ar == "bytes") and (self.total_size > 0)

                            cd = resp.headers.get("Content-Disposition", "")
                            cd_fn = self._parse_filename_from_cd(cd)
                            if cd_fn:
                                self.filename = cd_fn
                    except Exception as e_plain:
                        if isinstance(e_plain, urllib.error.HTTPError):
                            e_plain.close()
                            if e_plain.code in (401, 403, 410):
                                self.has_expired_link = True
                                self.last_http_status = e_plain.code
                        raise RuntimeError(f"Connection failed: {e_plain}")

        if self.is_googlevideo and self.total_size > 0:
            self.supports_ranges = True

        # Fallback filename extraction from URL if Content-Disposition was absent
        if not self.filename or os.path.isdir(self.destination_path) or self.filename in (".", "..", "download.bin"):
            try:
                parsed_path = urllib.parse.urlsplit(self.url).path
                url_fn = os.path.basename(urllib.parse.unquote(parsed_path.rstrip("/")))
                if url_fn:
                    self.filename = url_fn
            except Exception:
                pass

        # Update destination path if filename discovered
        if os.path.isdir(self.destination_path) or self.destination_path.endswith(("/", "\\")):
            self.destination_path = os.path.join(self.destination_path, self.filename or "download.bin")
            self.temp_dir = self.destination_path + ".sd_parts"
            for legacy_d in [self.destination_path + ".tdm_parts", self.destination_path + ".idm_parts"]:
                if os.path.isdir(legacy_d) and not os.path.exists(self.temp_dir):
                    try:
                        os.replace(legacy_d, self.temp_dir)
                        break
                    except Exception:
                        pass

        # HTML response safety net: abort if server returned an HTML page instead of a binary file
        fn_to_check = self.filename or os.path.basename(self.destination_path)
        dest_ext = os.path.splitext(fn_to_check)[1].lower() if fn_to_check else ""
        if getattr(self, "content_type", "") == "text/html":
            if not dest_ext or dest_ext == ".bin":
                raise RuntimeError("Server returned a web page (HTML), not a file")

        if self.supports_ranges and self.total_size > 0:
            size_mb = self.total_size / (1024 * 1024)
            self.log(f"Server supports HTTP 206 Multi-threading! Total Size: {size_mb:.2f} MB ({self.total_size:,} bytes).")
        else:
            if self.total_size > 0:
                self.log(f"Server does not support HTTP Range requests. Size: {self.total_size:,} bytes. Single-stream fallback active.")
            else:
                self.log("Server does not support HTTP Range requests and size is dynamic/unknown. Single-stream fallback active.")

    def start(self):
        """Launches the download supervisor thread."""
        self.is_running = True
        self.is_paused = False
        self._cancel_event.clear()
        self._pause_event.clear()
        self.start_time = time.time()
        self._last_active_start_mono = time.monotonic()
        self.last_speed_check_time = time.monotonic()
        self.last_downloaded_bytes = sum(c.downloaded_bytes for c in self.chunks)
        self._session_start_bytes = self.last_downloaded_bytes

        supervisor_thread = threading.Thread(target=self._supervisor_loop, daemon=True)
        supervisor_thread.start()

    def pause(self):
        """Pauses all active chunk downloads."""
        if not self.is_running or self.is_paused:
            return
        self.is_paused = True
        if self._last_active_start_mono is not None:
            self._accumulated_active_sec += max(0.0, time.monotonic() - self._last_active_start_mono)
            self._last_active_start_mono = None
        self._pause_event.set()
        self.save_state()
        self.log("Download paused by user.")

    def resume(self):
        """Resumes all active chunk downloads."""
        if not self.is_running or not self.is_paused:
            return
        self.is_paused = False
        self._last_active_start_mono = time.monotonic()
        self.last_speed_check_time = time.monotonic()
        self.last_downloaded_bytes = sum(c.downloaded_bytes for c in self.chunks)
        self._session_start_bytes = self.last_downloaded_bytes
        self._pause_event.clear()
        self.log("Download resumed.")

    def cancel(self):
        """Cancels download and stops all worker threads immediately."""
        self.is_running = False
        self._cancel_event.set()
        self._pause_event.clear()
        self._last_active_start_mono = None

        # Abort any blocked socket reads immediately
        with self._lock:
            for conn in self._active_connections:
                try:
                    conn.close()
                except Exception:
                    pass
            self._active_connections.clear()

        self.log("Download cancelled by user.")
        self.cleanup_temp_files()

    def cleanup_temp_files(self):
        """Safely cleans up temporary chunk directory and files."""
        try:
            if hasattr(self, "temp_dir") and self.temp_dir and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir, ignore_errors=True)
        except Exception:
            pass

    def _supervisor_loop(self):
        """Master supervisor: manages initial connection, dynamic splitting, and assembly."""
        try:
            is_resuming = bool(
                getattr(self, "_resume_mode", False)
                or (self.chunks and any(c.downloaded_bytes > 0 for c in self.chunks))
            )

            # If not in resume mode, check if state file exists in temp_dir to restore
            if not is_resuming and not self.chunks and os.path.exists(self.temp_dir):
                if self.load_state() and self.chunks:
                    is_resuming = True

            if not is_resuming:
                self.probe()

                if os.path.exists(self.temp_dir):
                    shutil.rmtree(self.temp_dir, ignore_errors=True)
                os.makedirs(self.temp_dir, exist_ok=True)

                # Allocate initial chunk 0
                # If total_size > 0, initial_end MUST be total_size - 1 even in single-stream mode!
                initial_end = (self.total_size - 1) if self.total_size > 0 else 0
                chunk0 = DownloadChunk(
                    chunk_id=0,
                    start_byte=0,
                    end_byte=initial_end,
                    downloaded_bytes=0,
                    status="pending",
                    part_filepath=os.path.join(self.temp_dir, f"{os.path.basename(self.destination_path)}.part_0")
                )
                with self._lock:
                    self.chunks.clear()
                    self.chunks.append(chunk0)

                self.save_state()
                self._spawn_worker(chunk0)
            else:
                self.log(f"Resuming download from existing chunks ({len(self.chunks)} parts)...")
                os.makedirs(self.temp_dir, exist_ok=True)
                prior_workers = []
                with self._lock:
                    prior_workers = list(self.active_workers)
                for w in prior_workers:
                    if w.is_alive() and w != threading.current_thread():
                        w.join(timeout=0.3)
                self._error_abort_event.clear()
                with self._lock:
                    self.active_workers.clear()
                    self._active_connections.clear()
                    for c in self.chunks:
                        with c.lock:
                            expected = c.end_byte - c.start_byte + 1
                            if os.path.exists(c.part_filepath):
                                try:
                                    actual_bytes = os.path.getsize(c.part_filepath)
                                    c.downloaded_bytes = min(actual_bytes, expected)
                                    if actual_bytes > expected:
                                        with open(c.part_filepath, "r+b") as tf:
                                            tf.truncate(expected)
                                except Exception:
                                    pass
                            if self.total_size > 0 and c.downloaded_bytes >= expected:
                                c.status = "completed"
                            else:
                                c.status = "pending"
                                c.error_msg = ""
                    # Spawn workers for pending chunks up to max_connections
                    pending_chunks = [c for c in self.chunks if c.status == "pending"]
                    for c in pending_chunks[:self.max_connections]:
                        self._spawn_worker(c)
                self._resume_mode = False
                self.save_state()

            # Scheduling & Dynamic Splitting Loop
            while self.is_running and not self._cancel_event.is_set():
                time.sleep(0.08)

                if self.is_paused:
                    continue

                # Schedule pending chunks if worker slots available
                with self._lock:
                    active_count = sum(1 for c in self.chunks if c.status == "active")
                    if active_count < self.max_connections:
                        pending = [c for c in self.chunks if c.status == "pending"]
                        for c in pending[:self.max_connections - active_count]:
                            self._spawn_worker(c)

                # Check if we should dynamically split active chunks
                if self.supports_ranges and self.total_size > 0:
                    self._dynamic_split_check()

                # Update progress & calculate real-time speed
                self._update_progress_metrics()

                # Check completion or failure
                with self._lock:
                    all_finished = all(c.status in ("completed", "failed") for c in self.chunks)
                    any_failed = any(c.status == "failed" for c in self.chunks)

                # Fail fast if a chunk failed permanently
                if any_failed:
                    failed_chunks = [c for c in self.chunks if c.status == "failed"]
                    err = failed_chunks[0].error_msg if failed_chunks else "Chunk transfer failure"
                    self._stop_workers_for_error()
                    self.save_state()
                    raise RuntimeError(f"Download failed in chunk: {err}")

                if all_finished:
                    break

            if self._cancel_event.is_set():
                return

            # Perform strict sequential assembly
            self.assemble()

            active_elapsed = self._accumulated_active_sec
            if self._last_active_start_mono is not None:
                active_elapsed += max(0.0, time.monotonic() - self._last_active_start_mono)

            if active_elapsed > 0.001:
                elapsed = max(0.01, active_elapsed)
            else:
                elapsed = max(0.01, time.time() - self.start_time)

            total_downloaded = sum(c.downloaded_bytes for c in self.chunks)
            if self.total_size > 0:
                total_downloaded = max(total_downloaded, self.total_size)
            session_transferred = max(0, total_downloaded - getattr(self, "_session_start_bytes", 0))
            bytes_for_speed = session_transferred if session_transferred > 0 else (self.total_size if self.total_size > 0 else total_downloaded)

            avg_speed = (bytes_for_speed / elapsed) if elapsed > 0 else 0
            speed_str = f"{avg_speed / (1024*1024):.2f} MB/s" if avg_speed >= 1024*1024 else f"{avg_speed / 1024:.1f} KB/s"
            self.log(f"[SUCCESS] Download finished successfully in {elapsed:.1f}s (Average Speed: {speed_str})!")

            if self.on_complete:
                self.on_complete(self.destination_path, self.total_size, elapsed)

        except Exception as e:
            self.log(f"[ERROR] {e}")
            if self.on_error:
                self.on_error(str(e))
        finally:
            self.is_running = False
            if self._cancel_event.is_set():
                self.cleanup_temp_files()


__all__ = ["TurboDownloadEngine", "EngineWorkersMixin"]
