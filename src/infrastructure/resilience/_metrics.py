"""Rate limiter metrics collection for observability."""

from __future__ import annotations

import threading
import time
from typing import Any


class DhanRateLimiterMetrics:
    """Collects rate limiter metrics for observability (Dhan + generic).

    Tracks:
      - Request timestamps per category (for requests/sec calculation)
      - Queue depth (waiting acquire calls)
      - Rate limit rejections (timeouts)
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._request_timestamps: dict[str, list[float]] = {}
        self._queue_depth: dict[str, int] = {}
        self._rejections: dict[str, int] = {}

    def record_request(self, category: str) -> None:
        """Record a successful rate limit acquisition."""
        with self._lock:
            timestamps = self._request_timestamps.setdefault(category, [])
            cutoff = time.monotonic() - 60.0
            timestamps[:] = [t for t in timestamps if t > cutoff]
            timestamps.append(time.monotonic())

    def record_rejection(self, category: str) -> None:
        """Record a rate limit rejection (timeout)."""
        with self._lock:
            self._rejections[category] = self._rejections.get(category, 0) + 1

    def increment_queue_depth(self, category: str) -> None:
        """Increment queue depth for a category."""
        with self._lock:
            self._queue_depth[category] = self._queue_depth.get(category, 0) + 1

    def decrement_queue_depth(self, category: str) -> None:
        """Decrement queue depth for a category."""
        with self._lock:
            depth = self._queue_depth.get(category, 0)
            if depth > 0:
                self._queue_depth[category] = depth - 1

    def get_requests_per_second(self, category: str) -> float:
        """Get current request rate for a category (last 10 seconds)."""
        with self._lock:
            timestamps = self._request_timestamps.get(category, [])
            if not timestamps:
                return 0.0
            cutoff = time.monotonic() - 10.0
            recent = [t for t in timestamps if t > cutoff]
            if len(recent) < 2:
                return float(len(recent))
            duration = recent[-1] - recent[0]
            if duration <= 0:
                return float(len(recent))
            return (len(recent) - 1) / duration

    def get_queue_depth(self, category: str) -> int:
        """Get current queue depth for a category."""
        with self._lock:
            return self._queue_depth.get(category, 0)

    def get_rejections(self, category: str) -> int:
        """Get total rejections for a category."""
        with self._lock:
            return self._rejections.get(category, 0)

    def snapshot(self) -> dict[str, Any]:
        """Get a full metrics snapshot for all categories."""
        with self._lock:
            all_categories = set(self._request_timestamps.keys()) | set(self._queue_depth.keys())
            result = {}
            for cat in all_categories:
                result[cat] = {
                    "requests_per_second": self._calc_rps_unsafe(cat),
                    "queue_depth": self._queue_depth.get(cat, 0),
                    "rejections": self._rejections.get(cat, 0),
                }
            return result

    def _calc_rps_unsafe(self, category: str) -> float:
        """Calculate RPS without acquiring lock (caller must hold lock)."""
        timestamps = self._request_timestamps.get(category, [])
        if not timestamps:
            return 0.0
        cutoff = time.monotonic() - 10.0
        recent = [t for t in timestamps if t > cutoff]
        if len(recent) < 2:
            return float(len(recent))
        duration = recent[-1] - recent[0]
        if duration <= 0:
            return float(len(recent))
        return (len(recent) - 1) / duration
