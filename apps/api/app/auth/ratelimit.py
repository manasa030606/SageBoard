"""In-process sliding-window rate limiter.

Good for one API instance (ADR-0004). With several instances, move the counters to
PostgreSQL or Redis; the interface stays the same.
"""

from __future__ import annotations

import math
import time
from collections import deque
from collections.abc import Callable
from threading import Lock

MAX_KEYS = 50_000


class RateLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._hits: dict[str, deque[float]] = {}
        self._lock = Lock()
        self._clock = clock

    def hit(self, key: str, limit: int, window_s: float) -> int | None:
        """Record an attempt. Returns seconds to wait if over the limit, else None."""
        now = self._clock()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] <= now - window_s:
                hits.popleft()
            if len(hits) >= limit:
                return max(1, math.ceil(hits[0] + window_s - now))
            hits.append(now)
            if len(self._hits) > MAX_KEYS:
                self._prune(now, window_s)
            return None

    def _prune(self, now: float, window_s: float) -> None:
        for key in [k for k, v in self._hits.items() if not v or v[-1] <= now - window_s]:
            del self._hits[key]
