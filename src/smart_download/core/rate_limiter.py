"""
Token bucket rate limiter for dynamic live download speed regulation.
"""
import time
import threading
from typing import Optional

class TokenBucketRateLimiter:
    """
    Thread-safe Token Bucket Rate Limiter for dynamic bandwidth throttling.
    Shared across all concurrent chunk download threads for a given file.
    Can be adjusted instantaneously while downloads are actively running.
    Features dynamic capacity adaptation and cancel awareness to prevent thread hangs.
    """
    def __init__(self, rate_limit_bytes_per_sec: float = 0.0):
        # 0 or negative indicates Unlimited speed
        self.rate_limit = float(rate_limit_bytes_per_sec)
        self.capacity = max(self.rate_limit * 0.5, 65536.0) if self.rate_limit > 0 else 0.0
        self.tokens = min(self.capacity, 65536.0)
        self.last_update = time.monotonic()
        self._lock = threading.Lock()

    def set_limit(self, bytes_per_sec: float):
        """Thread-safe dynamic adjustment of bandwidth limit."""
        with self._lock:
            self.rate_limit = float(bytes_per_sec)
            if self.rate_limit > 0:
                self.capacity = max(self.rate_limit * 0.5, 65536.0)
                self.tokens = min(self.tokens, self.capacity)
            else:
                self.capacity = 0.0
                self.tokens = 0.0
            self.last_update = time.monotonic()

    def acquire(self, num_bytes: int, cancel_event: Optional[threading.Event] = None):
        """
        Paces data transfer by consuming tokens or sleeping if the rate limit is exceeded.
        Releases internal lock before sleeping to avoid blocking other threads or UI updates.
        Supports cancel_event for instant awakening on download cancellation.
        """
        if num_bytes <= 0:
            return

        while True:
            if cancel_event and cancel_event.is_set():
                return
            if self.rate_limit <= 0:
                return  # Unlimited speed

            with self._lock:
                if self.rate_limit <= 0:
                    return

                # Dynamically expand capacity if request exceeds current bucket size
                if num_bytes > self.capacity:
                    self.capacity = float(num_bytes * 2)

                now = time.monotonic()
                elapsed = now - self.last_update
                self.last_update = now

                # Replenish tokens based on elapsed time
                self.tokens = min(self.capacity, self.tokens + elapsed * self.rate_limit)

                if self.tokens >= num_bytes:
                    self.tokens -= num_bytes
                    return

                needed = num_bytes - self.tokens
                wait_time = needed / self.rate_limit

            sleep_step = min(wait_time, 0.05)
            if cancel_event:
                if cancel_event.wait(timeout=sleep_step):
                    return
            else:
                time.sleep(sleep_step)

