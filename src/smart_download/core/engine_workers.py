"""
EngineWorkersMixin: Background worker thread pooling and dynamic chunk splitting.
"""
import os
import time
import urllib.request
import urllib.error
import urllib.parse
import threading
from typing import Optional, Dict, Any

from .chunk import DownloadChunk
from .engine_resumer import EngineResumerMixin
from ..utils.url_utils import parse_filename_from_cd_header


class EngineWorkersMixin(EngineResumerMixin):
    """Mixin providing worker management, chunk streaming, dynamic splitting, and rate limiting."""

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
        return parse_filename_from_cd_header(cd)

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
            while self._pause_event.is_set() and not self._cancel_event.is_set() and not self._error_abort_event.is_set() and self.is_running:
                time.sleep(0.1)
            if self._cancel_event.is_set() or self._error_abort_event.is_set() or not self.is_running:
                return
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
                            raise RuntimeError("Server returned HTTP 200 instead of HTTP 206 for non-zero range")

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
                if self._pause_event.is_set():
                    while self._pause_event.is_set() and not self._cancel_event.is_set() and not self._error_abort_event.is_set() and self.is_running:
                        time.sleep(0.1)
                    if self._cancel_event.is_set() or self._error_abort_event.is_set() or not self.is_running:
                        return
                    continue
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
            if not self.allow_dynamic_split or self.is_googlevideo or not getattr(self, "supports_ranges", False):
                return

        while True:
            if self._cancel_event.is_set() or not getattr(self, "is_running", False):
                break
            new_chunk = None
            candidate = None
            split_start = 0
            old_end = 0
            new_id = 0
            with self._lock:
                active_or_pending = sum(1 for c in self.chunks if c.status in ("active", "pending"))
                if active_or_pending >= self.max_connections:
                    break

                candidates = [
                    c for c in self.chunks
                    if c.status in ("active", "pending") and c.remaining_bytes >= self.min_split_threshold * 2
                ]
                if not candidates:
                    candidates = [
                        c for c in self.chunks
                        if c.status in ("active", "pending") and c.remaining_bytes >= self.min_split_threshold
                    ]
                if not candidates:
                    break

                # Select candidate with the largest remaining byte range
                candidate = max(candidates, key=lambda c: c.remaining_bytes)

                with candidate.lock:
                    remaining = candidate.end_byte - (candidate.start_byte + candidate.downloaded_bytes) + 1
                    half = remaining // 2
                    if remaining < self.min_split_threshold or half < 32768 or candidate.status not in ("active", "pending"):
                        break

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

            if new_chunk and candidate:
                self.save_state()
                self.log(f"[SPLIT] Fast Ramp-Up Split: Chunk #{candidate.chunk_id} split! Spawned Chunk #{new_id} [{split_start:,} - {old_end:,}]")
                self._spawn_worker(new_chunk)
            else:
                break

    def _update_progress_metrics(self):
        """Computes smoothed transfer speed, ETA, and progress metrics."""
        now = time.monotonic()
        dt = now - self.last_speed_check_time

        with self._lock:
            total_downloaded = sum(c.downloaded_bytes for c in self.chunks)
            active_count = sum(1 for c in self.chunks if c.status == "active")

        if dt >= 0.12:
            delta_bytes = total_downloaded - self.last_downloaded_bytes
            instant_speed = max(0.0, delta_bytes / dt)
            # Exponential Moving Average for silky smooth speed meter
            if self.current_speed == 0.0:
                self.current_speed = instant_speed
            else:
                self.current_speed = (0.45 * instant_speed) + (0.55 * self.current_speed)

            self.last_downloaded_bytes = total_downloaded
            self.last_speed_check_time = now

        if self.current_speed <= 0.0 and total_downloaded > 0:
            st = getattr(self, "start_time", 0.0)
            elapsed = (time.time() - st) if (isinstance(st, (int, float)) and st > 0) else 0.1
            self.current_speed = total_downloaded / max(0.05, elapsed)

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


__all__ = ["EngineWorkersMixin", "EngineResumerMixin"]
