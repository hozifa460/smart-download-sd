"""
EngineWorkersMixin: Background worker thread pooling, dynamic chunk splitting, and URL refreshing.
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
from typing import List, Optional, Callable, Dict, Any, Union, Tuple

from ..config import BUFFER_SIZE
from .rate_limiter import TokenBucketRateLimiter
from .chunk import DownloadChunk, get_permissive_ssl_context
from .html_resolver import validate_refresh_url
from ..utils.url_utils import parse_filename_from_cd_header


class EngineWorkersMixin:
    """Mixin providing worker management, chunk streaming, dynamic splitting, and link refreshing."""

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

