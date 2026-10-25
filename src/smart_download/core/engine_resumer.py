"""
Engine resumer and dynamic URL refresh mixin for Smart Download (SD).
"""
import time
import threading
from typing import Optional, Dict, Tuple

from .html_resolver import validate_refresh_url


class EngineResumerMixin:
    """Provides methods for updating download URLs, validating refreshed links, and resuming transfers."""

    def update_url(self, new_url: str, headers: Optional[Dict[str, str]] = None):
        """
        Updates target download URL and session headers on the fly.
        Propagates to active workers and persists state.
        """
        with self._lock:
            self.url = str(new_url).strip()
            if headers:
                self.headers.update(headers)

            if hasattr(self, "is_googlevideo_url"):
                self.is_googlevideo = self.is_googlevideo_url(self.url)
            else:
                self.is_googlevideo = "googlevideo.com" in self.url.lower()

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


__all__ = ["EngineResumerMixin"]
