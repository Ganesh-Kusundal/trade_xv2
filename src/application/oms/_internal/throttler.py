"""Submit/modify rate throttler — sliding window rate limiter.

Prevents order spam by limiting the number of submit/modify requests
within a time window. Modeled after Nautilus RiskEngine throttler.
"""
from __future__ import annotations

import time
from collections import deque


class Throttler:
    """Sliding-window rate limiter for order submissions."""

    def __init__(self, max_per_second: int = 10, window_seconds: float = 1.0) -> None:
        self._max_per_second = max_per_second
        self._window = window_seconds
        self._timestamps: deque[float] = deque()

    def allow(self) -> bool:
        """Check if a submission is allowed. Records the attempt."""
        now = time.monotonic()
        cutoff = now - self._window
        while self._timestamps and self._timestamps[0] < cutoff:
            self._timestamps.popleft()
        if len(self._timestamps) >= self._max_per_second:
            return False
        self._timestamps.append(now)
        return True

    @property
    def remaining(self) -> int:
        """Number of remaining allowed submissions in current window."""
        now = time.monotonic()
        cutoff = now - self._window
        while self._timestamps and self._timestamps[0] < cutoff:
            self._timestamps.popleft()
        return max(0, self._max_per_second - len(self._timestamps))

    def reset(self) -> None:
        """Clear the throttle window."""
        self._timestamps.clear()
