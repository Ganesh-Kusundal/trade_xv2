"""Broker health monitor — tracks consecutive failures per broker.

Provides a simple, thread-safe mechanism to determine whether a broker
is healthy based on consecutive failure counts. When a broker exceeds
the configured failure threshold it is considered unhealthy until a
successful call resets its counter.

Usage::

    monitor = BrokerHealthMonitor(failure_threshold=5)
    monitor.record_success("dhan")
    monitor.record_failure("upstox")
    if monitor.is_healthy("dhan"):
        ...
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class BrokerHealthStatus:
    """Point-in-time health snapshot for a single broker."""

    last_successful_call: float | None = None
    consecutive_failures: int = 0
    circuit_state: str = "healthy"  # healthy | unhealthy
    last_health_check: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation."""
        return {
            "last_successful_call": self.last_successful_call,
            "consecutive_failures": self.consecutive_failures,
            "circuit_state": self.circuit_state,
            "last_health_check": self.last_health_check,
        }


class BrokerHealthMonitor:
    """Thread-safe health tracker for one or more brokers.

    Parameters
    ----------
    failure_threshold : int
        Number of consecutive failures after which a broker is
        considered unhealthy. Default is 5.
    """

    def __init__(self, failure_threshold: int = 5) -> None:
        if failure_threshold <= 0:
            raise ValueError(
                f"failure_threshold must be positive, got {failure_threshold}"
            )
        self._failure_threshold = failure_threshold
        self._lock = threading.RLock()
        # broker_name -> BrokerHealthStatus
        self._health: dict[str, BrokerHealthStatus] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_success(self, broker: str) -> None:
        """Record a successful call for *broker*.

        Resets the consecutive-failure counter and marks the broker as
        healthy. Thread-safe.
        """
        now = time.monotonic()
        with self._lock:
            status = self._ensure(broker)
            status.last_successful_call = now
            status.consecutive_failures = 0
            status.circuit_state = "healthy"
            status.last_health_check = now

    def record_failure(self, broker: str) -> None:
        """Record a failed call for *broker*.

        Increments the consecutive-failure counter. If the counter
        reaches the configured threshold the broker transitions to
        ``unhealthy``. Thread-safe.
        """
        now = time.monotonic()
        with self._lock:
            status = self._ensure(broker)
            status.consecutive_failures += 1
            status.last_health_check = now
            if status.consecutive_failures >= self._failure_threshold:
                status.circuit_state = "unhealthy"

    def is_healthy(self, broker: str) -> bool:
        """Return True if *broker* is considered healthy.

        A broker that has never been seen is treated as healthy
        (optimistic default). Thread-safe.
        """
        with self._lock:
            status = self._health.get(broker)
            if status is None:
                return True  # optimistic: unknown brokers are healthy
            return status.circuit_state == "healthy"

    def get_health_status(self) -> dict[str, BrokerHealthStatus]:
        """Return a snapshot of every broker's health.

        Thread-safe: returns a shallow copy of the inner dicts so
        callers cannot mutate internal state.
        """
        with self._lock:
            return {
                name: BrokerHealthStatus(
                    last_successful_call=s.last_successful_call,
                    consecutive_failures=s.consecutive_failures,
                    circuit_state=s.circuit_state,
                    last_health_check=s.last_health_check,
                )
                for name, s in self._health.items()
            }

    def any_healthy(self, brokers: list[str] | None = None) -> bool:
        """Return True if at least one broker in *brokers* is healthy.

        If *brokers* is None, checks every tracked broker. An empty
        list returns False (nothing to check). Thread-safe.
        """
        with self._lock:
            targets = brokers if brokers is not None else list(self._health.keys())
            if not targets:
                return False
            return any(self.is_healthy(b) for b in targets)

    def reset(self, broker: str | None = None) -> None:
        """Reset health tracking.

        If *broker* is given, only that broker is reset. Otherwise
        every tracked broker is cleared. Thread-safe.
        """
        with self._lock:
            if broker is not None:
                self._health.pop(broker, None)
            else:
                self._health.clear()

    @property
    def failure_threshold(self) -> int:
        return self._failure_threshold

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure(self, broker: str) -> BrokerHealthStatus:
        """Return (and lazily create) the health status for *broker*.

        NOTE: Caller must hold self._lock.
        """
        if broker not in self._health:
            self._health[broker] = BrokerHealthStatus()
        return self._health[broker]
