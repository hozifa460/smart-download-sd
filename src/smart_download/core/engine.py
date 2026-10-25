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

class TurboDownloadEngine(EnginePersistenceMixin):
    """
    High-throughput download engine featuring:
    - Dynamic on-the-fly chunk splitting (largest remaining space candidate + midpoint split).
    - Strict non-corrupt sequential assembly with 64KB streaming buffers & boundary assertions.
    - Integrated per-download token bucket rate limiting.
    - Robust range fallback, transient error retries, and atomic chunk boundary clamping.
    - Permissive SSL context for expired/self-signed certificates across all probes & chunk workers.
    """
    @staticmethod
    def is_googlevideo_url(url: str) -> bool:
        """Detects if a URL is hosted on YouTube CDN (googlevideo.com)."""
        if not url or not isinstance(url, str):
            return False
        try:
            parsed = urllib.parse.urlsplit(url)
            host = (parsed.hostname or "").lower()
            if host.endswith(".googlevideo.com") or host == "googlevideo.com":
                return True
            if any(dom in host for dom in ("youtube.com", "youtu.be", "ytimg.com")):
                return True
            path = (parsed.path or "").lower()
            if "videoplayback" in path:
                return True
        except Exception:
            pass
        url_lower = str(url).lower()
        return "googlevideo.com" in url_lower or "videoplayback" in url_lower

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

    def _parse_filename_from_cd(self, cd: str) -> Optional[str]:
        """Extracts clean filename from Content-Disposition header, ignoring parameters."""
        if not cd:
            return None
        parts = cd.split(";")
        for p in parts:
            p = p.strip()
            if p.lower().startswith("filename="):
                raw = p[9:].strip("\"' ")
                if raw:
                    return os.path.basename(raw)
        return None

    def _create_request(self, method: Optional[str] = None) -> urllib.request.Request:
        """Constructs an HTTP request pre-populated with standard headers and custom headers."""
        if method:
            req = urllib.request.Request(self.url, method=method)
        else:
            req = urllib.request.Request(self.url)

        has_ua = any(k.lower() == "user-agent" for k in self.headers)
        if not has_ua:
            req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0")

        for k, v in self.headers.items():
            req.add_header(k, v)
        return req

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

    def _spawn_worker(self, chunk: DownloadChunk):
        """Spawns an asynchronous worker thread for a specific chunk."""
        t = threading.Thread(target=self._chunk_worker, args=(chunk,), daemon=True)
        with self._lock:
            self.active_workers.append(t)
        t.start()

    def _chunk_worker(self, chunk: DownloadChunk):
        """
        Worker thread with automatic transient retry, safe boundary clamping,
        smooth single-connection streaming for YouTube/googlevideo CDN, and single-handle file streaming.
        """
        max_retries = 3
        retry_count = 0

        while retry_count < max_retries and not self._cancel_event.is_set() and not self._error_abort_event.is_set() and self.is_running:
            resp = None
            seg_bytes_read = 0
            try:
                # Streaming loop across byte range until chunk is fully downloaded
                while not self._cancel_event.is_set() and not self._error_abort_event.is_set() and self.is_running:
                    with chunk.lock:
                        chunk.status = "active"
                        cur_offset = chunk.start_byte + chunk.downloaded_bytes
                        target_end = chunk.end_byte
                        if self.total_size > 0 and cur_offset > target_end:
                            chunk.status = "completed"
                            return
                        if self.total_size == 0 and chunk.downloaded_bytes > 0 and chunk.status == "completed":
                            return

                    # Compute end byte for this request (single continuous stream from cur_offset to target_end)
                    if self.supports_ranges and self.total_size > 0:
                        req_end = target_end
                    else:
                        req_end = None

                    end_str = f"{req_end:,}" if req_end is not None else "end"
                    self.log(
                        f"Connection #{chunk.chunk_id} (Attempt {retry_count+1}): "
                        f"Byte range [{cur_offset:,} - {end_str}]"
                    )
                    if self.on_chunk_update:
                        self.on_chunk_update()

                    req = self._create_request()
                    if self.supports_ranges and self.total_size > 0 and req_end is not None:
                        req.add_header("Range", f"bytes={cur_offset}-{req_end}")
                        if chunk.downloaded_bytes > 0 and os.path.exists(chunk.part_filepath):
                            try:
                                with open(chunk.part_filepath, "r+b") as tf:
                                    tf.seek(chunk.downloaded_bytes)
                                    tf.truncate()
                            except Exception:
                                pass
                            file_mode = "ab"
                        else:
                            file_mode = "wb"
                    else:
                        chunk.downloaded_bytes = 0
                        file_mode = "wb"

                    resp = urllib.request.urlopen(req, timeout=15, context=self.ssl_context)
                    if self.supports_ranges and self.total_size > 0:
                        code = resp.getcode()
                        if code not in (200, 206):
                            raise RuntimeError(f"Unexpected HTTP status {code}")
                        if code == 200 and cur_offset > 0:
                            raise RuntimeError(f"Server returned HTTP 200 instead of HTTP 206 for non-zero range")

                    with self._lock:
                        self._active_connections.append(resp)

                    BUF_SIZE = 131072
                    seg_bytes_read = 0
                    expected_seg_bytes = (req_end - cur_offset + 1) if (req_end is not None) else None

                    with open(chunk.part_filepath, file_mode) as f:
                        while not self._cancel_event.is_set() and not self._error_abort_event.is_set() and self.is_running:
                            # Handle pause
                            while self._pause_event.is_set() and not self._cancel_event.is_set() and not self._error_abort_event.is_set() and self.is_running:
                                time.sleep(0.1)

                            if self._cancel_event.is_set() or self._error_abort_event.is_set() or not self.is_running:
                                return

                            with chunk.lock:
                                cur_end = chunk.end_byte
                                pos = chunk.start_byte + chunk.downloaded_bytes
                                if self.total_size > 0 and pos > cur_end:
                                    chunk.status = "completed"
                                    return
                                effective_end = min(cur_end, req_end) if req_end is not None else cur_end
                                to_read = min(BUF_SIZE, effective_end - pos + 1) if self.total_size > 0 else BUF_SIZE

                            if to_read <= 0:
                                break

                            data = resp.read(to_read)
                            if not data:
                                if expected_seg_bytes is not None and seg_bytes_read < expected_seg_bytes:
                                    raise RuntimeError(
                                        f"Premature EOF from server: received {seg_bytes_read:,} of {expected_seg_bytes:,} bytes"
                                    )
                                break

                            # Enforce per-download speed limit with cancel responsiveness
                            self.rate_limiter.acquire(len(data), self._cancel_event)

                            # Atomic boundary clamp before writing to disk
                            with chunk.lock:
                                cur_end = chunk.end_byte
                                pos = chunk.start_byte + chunk.downloaded_bytes
                                effective_end = min(cur_end, req_end) if req_end is not None else cur_end
                                if self.total_size > 0:
                                    if pos > effective_end:
                                        break
                                    needed = effective_end - pos + 1
                                    if len(data) > needed:
                                        data = data[:needed]

                                f.write(data)
                                chunk.downloaded_bytes += len(data)
                                seg_bytes_read += len(data)

                                if self.total_size > 0 and (chunk.start_byte + chunk.downloaded_bytes > chunk.end_byte):
                                    chunk.status = "completed"
                                    return

                    with self._lock:
                        if resp in self._active_connections:
                            self._active_connections.remove(resp)
                    try:
                        resp.close()
                    except Exception:
                        pass
                    resp = None

                    # Check if entire chunk is finished
                    with chunk.lock:
                        if self.total_size > 0 and (chunk.start_byte + chunk.downloaded_bytes > chunk.end_byte):
                            chunk.status = "completed"
                            return
                        if self.total_size == 0:
                            chunk.status = "completed"
                            return

                    # If single request completed without reaching chunk end, treat as premature EOF to retry
                    with chunk.lock:
                        if self.total_size > 0 and (chunk.start_byte + chunk.downloaded_bytes <= chunk.end_byte):
                            raise RuntimeError(
                                f"Premature EOF from server before chunk completion "
                                f"({chunk.downloaded_bytes:,}/{chunk.end_byte - chunk.start_byte + 1:,} bytes)"
                            )
                        chunk.status = "completed"
                        return

            except Exception as e:
                if self._cancel_event.is_set() or self._error_abort_event.is_set() or not self.is_running:
                    return
                if isinstance(e, urllib.error.HTTPError):
                    e.close()
                    self.last_http_status = e.code
                    if e.code in (401, 403, 410):
                        self.has_expired_link = True
                        chunk.error_msg = f"HTTP {e.code}: {e.reason} (Expired or Forbidden Link)"
                        break
                if self._cancel_event.is_set() or self._error_abort_event.is_set() or not self.is_running:
                    return
                if seg_bytes_read > 0:
                    retry_count = max(0, retry_count - 1)
                retry_count += 1
                self.log(f"Connection #{chunk.chunk_id} error: {e}. Retry {retry_count}/{max_retries} in 1s...")
                time.sleep(1.0)
            finally:
                if resp:
                    with self._lock:
                        if resp in self._active_connections:
                            self._active_connections.remove(resp)
                    try:
                        resp.close()
                    except Exception:
                        pass
                if self.on_chunk_update:
                    self.on_chunk_update()

        # If retries exhausted or cancelled/aborted and chunk did not complete
        if self._cancel_event.is_set() or self._error_abort_event.is_set() or not self.is_running:
            return

        with chunk.lock:
            if chunk.status != "completed":
                chunk.status = "failed"
                if not chunk.error_msg:
                    chunk.error_msg = f"Connection failed after {max_retries} attempts"
                self.log(f"Chunk #{chunk.chunk_id} failed permanently: {chunk.error_msg}")
        self.save_state()
        if self.on_chunk_update:
            self.on_chunk_update()

    def _dynamic_split_check(self):
        """
        TDM Adaptive Dynamic Midpoint Splitting Mechanism:
        1. Evaluates active worker count against max_connections.
        2. Candidate selection: selects active chunk with largest remaining un-downloaded space.
        3. Threshold condition: remaining must be >= min_split_threshold and remaining // 2 >= 32KB.
        4. Mid-point split: candidate's end_byte shrinks to mid - 1; new chunk created for [mid, old_end].
        5. Atomic lock synchronization prevents gaps or race conditions.
        6. New connection spawned immediately on new chunk.
        """
        with self._lock:
            if not self.allow_dynamic_split or self.is_googlevideo:
                return

            active_count = sum(1 for c in self.chunks if c.status == "active")
            if active_count >= self.max_connections:
                return

            candidates = [
                c for c in self.chunks
                if c.status == "active" and c.remaining_bytes >= self.min_split_threshold
            ]
            if not candidates:
                return

            # Select candidate with the largest remaining byte range
            candidate = max(candidates, key=lambda c: c.remaining_bytes)

            with candidate.lock:
                remaining = candidate.end_byte - (candidate.start_byte + candidate.downloaded_bytes) + 1
                half = remaining // 2
                if remaining < self.min_split_threshold or half < 32768 or candidate.status != "active":
                    return

                split_start = candidate.start_byte + candidate.downloaded_bytes + half
                old_end = candidate.end_byte

                # Candidate's new end is adjusted atomically
                candidate.end_byte = split_start - 1

            # Create the new chunk atomically inside self._lock
            new_id = len(self.chunks)
            part_path = os.path.join(self.temp_dir, f"{os.path.basename(self.destination_path)}.part_{new_id}")
            new_chunk = DownloadChunk(
                chunk_id=new_id,
                start_byte=split_start,
                end_byte=old_end,
                downloaded_bytes=0,
                status="pending",
                part_filepath=part_path
            )
            self.chunks.append(new_chunk)

        self.save_state()
        self.log(f"[SPLIT] Dynamic Split: Chunk #{candidate.chunk_id} split! Spawned Chunk #{new_id} [{split_start:,} - {old_end:,}]")
        self._spawn_worker(new_chunk)

    def _update_progress_metrics(self):
        """Computes smoothed transfer speed, ETA, and progress metrics."""
        now = time.monotonic()
        dt = now - self.last_speed_check_time

        with self._lock:
            total_downloaded = sum(c.downloaded_bytes for c in self.chunks)
            active_count = sum(1 for c in self.chunks if c.status == "active")

        if dt >= 0.4:
            delta_bytes = total_downloaded - self.last_downloaded_bytes
            instant_speed = max(0.0, delta_bytes / dt)
            # Exponential Moving Average for silky smooth speed meter
            if self.current_speed == 0.0:
                self.current_speed = instant_speed
            else:
                self.current_speed = (0.45 * instant_speed) + (0.55 * self.current_speed)

            self.last_downloaded_bytes = total_downloaded
            self.last_speed_check_time = now

        # Compute ETA
        if self.current_speed > 1024 and self.total_size > total_downloaded:
            rem_bytes = self.total_size - total_downloaded
            eta_sec = int(rem_bytes / self.current_speed)
            eta_str = f"{eta_sec // 3600:02d}:{(eta_sec % 3600) // 60:02d}:{eta_sec % 60:02d}"
        else:
            eta_str = "--:--:--"

        if self.on_progress:
            self.on_progress(total_downloaded, self.total_size, self.current_speed, eta_str, active_count)

    def _stop_workers_for_error(self):
        """Closes active socket connections and signals all workers to abort immediately."""
        self._error_abort_event.set()
        with self._lock:
            for conn in list(self._active_connections):
                try:
                    conn.close()
                except Exception:
                    pass
            self._active_connections.clear()

    def update_url(self, new_url: str, headers: Optional[Dict[str, str]] = None):
        """
        Updates target download URL and session headers on the fly.
        Propagates to active workers and persists state.
        """
        with self._lock:
            self.url = str(new_url).strip()
            if headers:
                self.headers.update(headers)

            self.is_googlevideo = self.is_googlevideo_url(self.url)
            if self.is_googlevideo:
                self.allow_dynamic_split = False
                self.max_connections = min(self.max_connections, 1)

            for conn in list(self._active_connections):
                try:
                    conn.close()
                except Exception:
                    pass
            self._active_connections.clear()
            self.save_state()
            self.log(f"Download URL updated: {self.url}")

    def validate_new_url(self, new_url: str, headers: Optional[Dict[str, str]] = None) -> Tuple[bool, str, int]:
        """Validates new URL against current total_size and range requirements."""
        is_valid, msg, size, ranges = validate_refresh_url(
            new_url=new_url,
            expected_size=self.total_size,
            check_range=self.supports_ranges,
            ssl_context=self.ssl_context,
            headers=headers or self.headers
        )
        return is_valid, msg, size

    def resume_transfer(self):
        """Resumes download transfer using existing chunks and part files."""
        if self.is_running:
            if self.is_paused:
                self.resume()
            return

        self._error_abort_event.clear()
        with self._lock:
            prior_workers = list(self.active_workers)
        for w in prior_workers:
            if w.is_alive() and w != threading.current_thread():
                w.join(timeout=0.3)

        self._resume_mode = True
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

    def refresh_link(self, new_url: str, headers: Optional[Dict[str, str]] = None, auto_resume: bool = True) -> bool:
        """
        Validates new URL, updates download address and headers, and resumes downloading
        seamlessly from existing chunk progress without losing downloaded parts.
        """
        is_valid, err_msg, new_size, new_ranges = validate_refresh_url(
            new_url=new_url,
            expected_size=self.total_size,
            check_range=self.supports_ranges,
            timeout=12.0,
            ssl_context=self.ssl_context,
            headers=headers or self.headers
        )
        if not is_valid:
            self.log(f"[REFRESH ERROR] Validation failed: {err_msg}")
            raise ValueError(err_msg)

        self.update_url(new_url, headers)
        self.has_expired_link = False
        self._error_abort_event.clear()

        if auto_resume:
            if self.is_running:
                with self._lock:
                    for c in self.chunks:
                        with c.lock:
                            if c.status == "failed":
                                c.status = "pending"
                                c.error_msg = ""
                if self.is_paused:
                    self.resume()
                else:
                    with self._lock:
                        active_count = sum(1 for c in self.chunks if c.status == "active")
                        pending = [c for c in self.chunks if c.status == "pending"]
                        to_spawn = pending[:max(0, self.max_connections - active_count)]
                    for c in to_spawn:
                        self._spawn_worker(c)
            else:
                self.resume_transfer()

        self.log(f"[REFRESH SUCCESS] Link refreshed successfully: {new_url}")
        return True

