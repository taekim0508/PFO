"""A per-visitor request limit, kept in this process's memory.

Each visitor (by IP address) gets a list of the times they asked, trimmed to the last day.
A request is refused when the last minute or the last day already holds the limit. Kept in
memory, so it forgets everything on restart and is per process; with one machine and one
worker that is the whole site. A second instance would need a shared store.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable

MINUTE = 60.0
DAY = 86_400.0


class RateLimiter:
    def __init__(
        self, *, per_minute: int, per_day: int, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._per_minute = per_minute
        self._per_day = per_day
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}

    def check(self, key: str) -> float | None:
        """Record a request from `key` and return None, or refuse it and return the seconds
        until it would be allowed. A refused request is not recorded."""
        now = self._clock()
        hits = self._hits.setdefault(key, deque())
        while hits and hits[0] <= now - DAY:
            hits.popleft()

        if len(hits) >= self._per_day:
            return hits[0] + DAY - now
        in_last_minute = [t for t in hits if t > now - MINUTE]
        if len(in_last_minute) >= self._per_minute:
            return in_last_minute[0] + MINUTE - now

        hits.append(now)
        return None

    def forget_idle(self) -> None:
        """Drop visitors with nothing in the last day, so memory follows active visitors."""
        now = self._clock()
        for key in [k for k, hits in self._hits.items() if not hits or hits[-1] <= now - DAY]:
            del self._hits[key]
