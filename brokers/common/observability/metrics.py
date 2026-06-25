"""Metrics catalog for multi-broker observability.

Provides in-process metrics counters and gauges that can be exported to
Prometheus or other monitoring systems via the infrastructure layer.

All metrics are thread-safe and can be incremented from any thread.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Counter:
    """Thread-safe monotonic counter."""

    _value: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def inc(self, n: int = 1) -> None:
        with self._lock:
            self._value += n

    @property
    def value(self) -> int:
        with self._lock:
            return self._value

    def reset(self) -> int:
        with self._lock:
            val = self._value
            self._value = 0
            return val


@dataclass
class Gauge:
    """Thread-safe gauge (can go up or down)."""

    _value: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def set(self, value: float) -> None:
        with self._lock:
            self._value = value

    def inc(self, n: float = 1.0) -> None:
        with self._lock:
            self._value += n

    def dec(self, n: float = 1.0) -> None:
        with self._lock:
            self._value -= n

    @property
    def value(self) -> float:
        with self._lock:
            return self._value


class MultiBrokerMetrics:
    """Centralized metrics registry for multi-broker operations.

    Usage::

        metrics = MultiBrokerMetrics.get_instance()
        metrics.routing_decisions_total.inc()
        metrics.quota_utilization.set(0.75)

    Singleton pattern ensures all components share the same metrics instance.
    """

    _instance: MultiBrokerMetrics | None = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        # Routing metrics
        self.routing_decisions_total = Counter()
        self.routing_failures_total = Counter()

        # Historical metrics
        self.historical_chunks_total = Counter()
        self.historical_chunks_failed_total = Counter()
        self.historical_conflicts_total = Counter()
        self.historical_degraded_total = Counter()

        # Quota metrics
        self.quota_acquisitions_total = Counter()
        self.quota_rejections_total = Counter()
        self.quota_utilization = Gauge()

        # Stream metrics
        self.stream_sessions_active = Gauge()
        self.stream_reconnects_total = Counter()
        self.stream_stale_total = Counter()
        self.stream_failovers_total = Counter()

    @classmethod
    def get_instance(cls) -> MultiBrokerMetrics:
        """Return the singleton metrics instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton instance (for testing)."""
        with cls._lock:
            cls._instance = None

    def snapshot(self) -> dict[str, Any]:
        """Return a snapshot of all current metric values."""
        return {
            "routing_decisions_total": self.routing_decisions_total.value,
            "routing_failures_total": self.routing_failures_total.value,
            "historical_chunks_total": self.historical_chunks_total.value,
            "historical_chunks_failed_total": self.historical_chunks_failed_total.value,
            "historical_conflicts_total": self.historical_conflicts_total.value,
            "historical_degraded_total": self.historical_degraded_total.value,
            "quota_acquisitions_total": self.quota_acquisitions_total.value,
            "quota_rejections_total": self.quota_rejections_total.value,
            "quota_utilization": self.quota_utilization.value,
            "stream_sessions_active": self.stream_sessions_active.value,
            "stream_reconnects_total": self.stream_reconnects_total.value,
            "stream_stale_total": self.stream_stale_total.value,
            "stream_failovers_total": self.stream_failovers_total.value,
        }


# Module-level singleton for convenience
metrics = MultiBrokerMetrics.get_instance()
