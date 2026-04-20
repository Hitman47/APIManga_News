from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    limit: int
    remaining: int
    reset_after_seconds: int
    retry_after_seconds: int


class InMemoryRateLimiter:
    def __init__(self, *, limit: int, window_seconds: int) -> None:
        self.limit = max(1, int(limit))
        self.window_seconds = max(1, int(window_seconds))
        self._lock = threading.Lock()
        self._buckets: dict[str, deque[float]] = {}
        self._events = self._buckets

    def check(self, key: str) -> RateLimitDecision:
        now = time.time()
        with self._lock:
            bucket = self._buckets.setdefault(key, deque())
            cutoff = now - self.window_seconds
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()

            current = len(bucket)
            if current >= self.limit:
                reset_after = max(0, int(bucket[0] + self.window_seconds - now)) if bucket else self.window_seconds
                return RateLimitDecision(
                    allowed=False,
                    limit=self.limit,
                    remaining=0,
                    reset_after_seconds=reset_after,
                    retry_after_seconds=max(1, reset_after),
                )

            bucket.append(now)
            remaining = max(0, self.limit - len(bucket))
            reset_after = max(0, int((bucket[0] + self.window_seconds) - now)) if bucket else self.window_seconds
            return RateLimitDecision(
                allowed=True,
                limit=self.limit,
                remaining=remaining,
                reset_after_seconds=reset_after,
                retry_after_seconds=0,
            )
