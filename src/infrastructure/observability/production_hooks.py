"""Phase 7 — Production observability hooks.

Lightweight, zero-dependency helpers for:
  - Timing decorators (sync and async)
  - Error rate tracking (rolling window counters)
  - Health check helpers (liveness, readiness, deep)

Designed for composition-root wiring — no global singletons.

Usage::

    from infrastructure.observability.production_hooks import (
        timed,
        ErrorRateTracker,
        HealthAggregator,
    )

    @timed("order_placement")
    def place_order(request):
        ...

    tracker = ErrorRateTracker(window_seconds=60.0)
    tracker.record("TICK", success=True)
    tracker.error_rate("TICK")  # 0.0
"""

from __future__ import annotations

import functools
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


# ---------------------------------------------------------------------------
# 1. Timing Decorators
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TimingResult:
    """Result of a timed operation."""

    operation: str
    duration_ms: float
    success: bool
    error: str | None = None


class _TimingStore:
    """Thread-safe rolling store of timing results."""

    def __init__(self, max_entries: int = 1_000) -> None:
        self._lock = threading.Lock()
        self._entries: deque[TimingResult] = deque(maxlen=max_entries)

    def record(self, result: TimingResult) -> None:
        with self._lock:
            self._entries.append(result)

    def stats(self, operation: str | None = None) -> dict[str, Any]:
        with self._lock:
            entries = list(self._entries)

        if operation:
            entries = [e for e in entries if e.operation == operation]

        if not entries:
            return {"count": 0, "p50_ms": 0.0, "p99_ms": 0.0, "error_rate": 0.0}

        durations = sorted(e.duration_ms for e in entries)
        errors = sum(1 for e in entries if not e.success)
        n = len(durations)

        return {
            "count": n,
            "p50_ms": durations[n // 2],
            "p99_ms": durations[int(n * 0.99)],
            "error_rate": errors / n if n > 0 else 0.0,
            "min_ms": durations[0],
            "max_ms": durations[-1],
        }

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


# Module-level store (replaced per-test via monkeypatch or direct assignment)
_timing_store = _TimingStore()


def get_timing_store() -> _TimingStore:
    """Return the global timing store (injectable for testing)."""
    return _timing_store


def timed(operation: str) -> callable:
    """Decorator that measures and records execution time.

    Records to the global timing store and logs at DEBUG level.

    Args:
        operation: Human-readable operation name (e.g. "order_placement")

    Example:
        @timed("order_placement")
        def place_order(request):
            ...
    """

    def decorator(func: callable) -> callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                duration_ms = (time.perf_counter() - start) * 1000
                _timing_store.record(TimingResult(operation, duration_ms, True))
                logger.debug(
                    "timed: %s completed in %.2fms",
                    operation,
                    duration_ms,
                )
                return result
            except Exception as exc:
                duration_ms = (time.perf_counter() - start) * 1000
                _timing_store.record(
                    TimingResult(operation, duration_ms, False, error=str(exc))
                )
                logger.warning(
                    "timed: %s failed after %.2fms: %s",
                    operation,
                    duration_ms,
                    exc,
                )
                raise

        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# 2. Error Rate Tracking
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ErrorSnapshot:
    """Point-in-time error rate for a metric key."""

    total: int
    errors: int
    rate: float  # 0.0 .. 1.0
    window_seconds: float


class ErrorRateTracker:
    """Rolling-window error rate tracker per metric key.

    Thread-safe. Old entries are pruned on every ``record`` call to
    prevent unbounded memory growth.

    Parameters
    ----------
    window_seconds:
        Rolling window width. Default 60s.
    max_entries_per_key:
        Hard cap on stored timestamps per key.
    """

    def __init__(
        self,
        window_seconds: float = 60.0,
        max_entries_per_key: int = 10_000,
    ) -> None:
        self._lock = threading.Lock()
        self._window = window_seconds
        self._max = max_entries_per_key
        # key -> deque of (timestamp, is_error)
        self._data: dict[str, deque[tuple[float, bool]]] = {}

    def record(self, key: str, success: bool) -> None:
        """Record an event outcome."""
        now = time.time()
        with self._lock:
            dq = self._data.setdefault(key, deque(maxlen=self._max))
            dq.append((now, not success))
            self._prune(key, dq)

    def _prune(self, key: str, dq: deque) -> None:
        cutoff = time.time() - self._window
        while dq and dq[0][0] < cutoff:
            dq.popleft()

    def error_rate(self, key: str) -> float:
        """Return the error rate (0.0 .. 1.0) for the rolling window."""
        cutoff = time.time() - self._window
        with self._lock:
            dq = self._data.get(key, deque())
            self._prune(key, dq)
            if not dq:
                return 0.0
            errors = sum(1 for _, is_err in dq if is_err)
            return errors / len(dq)

    def snapshot(self, key: str) -> ErrorSnapshot:
        """Return a detailed snapshot for the given key."""
        cutoff = time.time() - self._window
        with self._lock:
            dq = self._data.get(key, deque())
            self._prune(key, dq)
            total = len(dq)
            errors = sum(1 for _, is_err in dq if is_err)
        return ErrorSnapshot(
            total=total,
            errors=errors,
            rate=errors / total if total > 0 else 0.0,
            window_seconds=self._window,
        )

    def all_snapshots(self) -> dict[str, ErrorSnapshot]:
        """Return snapshots for all tracked keys."""
        with self._lock:
            keys = list(self._data.keys())
        return {k: self.snapshot(k) for k in keys}

    def reset(self, key: str | None = None) -> None:
        """Clear data for one or all keys."""
        with self._lock:
            if key:
                self._data.pop(key, None)
            else:
                self._data.clear()


# ---------------------------------------------------------------------------
# 3. Health Check Helpers
# ---------------------------------------------------------------------------

class HealthState(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class ComponentHealth:
    """Health status of a single component."""

    name: str
    state: HealthState
    message: str = ""
    latency_ms: float = 0.0
    last_check: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


class HealthAggregator:
    """Aggregates component health into a system-wide status.

    Usage::

        aggregator = HealthAggregator()
        aggregator.register("event_bus", lambda: ComponentHealth("event_bus", HealthState.HEALTHY))
        aggregator.register("broker", lambda: check_broker_health)

        overall = aggregator.check()  # ComponentHealth with rolled-up state
    """

    def __init__(self) -> None:
        self._checks: dict[str, callable] = {}
        self._lock = threading.Lock()

    def register(self, name: str, check_fn: callable) -> None:
        """Register a health check function.

        Args:
            name: Component name (e.g. "event_bus", "broker_dhan")
            check_fn: Callable returning ComponentHealth
        """
        with self._lock:
            self._checks[name] = check_fn

    def unregister(self, name: str) -> None:
        with self._lock:
            self._checks.pop(name, None)

    def check(self) -> ComponentHealth:
        """Run all checks and return aggregated health."""
        results: list[ComponentHealth] = []

        with self._lock:
            checks = dict(self._checks)

        for name, check_fn in checks.items():
            try:
                start = time.perf_counter()
                health = check_fn()
                latency_ms = (time.perf_counter() - start) * 1000
                # Update latency if the component didn't set it
                if health.latency_ms == 0:
                    health = ComponentHealth(
                        name=health.name,
                        state=health.state,
                        message=health.message,
                        latency_ms=latency_ms,
                        last_check=time.time(),
                        metadata=health.metadata,
                    )
                results.append(health)
            except Exception as exc:
                results.append(
                    ComponentHealth(
                        name=name,
                        state=HealthState.UNHEALTHY,
                        message=f"Check failed: {type(exc).__name__}: {exc}",
                    )
                )

        if not results:
            return ComponentHealth(
                name="system",
                state=HealthState.HEALTHY,
                message="No components registered",
            )

        # Roll up: worst state wins
        states = [r.state for r in results]
        if HealthState.UNHEALTHY in states:
            overall = HealthState.UNHEALTHY
        elif HealthState.DEGRADED in states:
            overall = HealthState.DEGRADED
        else:
            overall = HealthState.HEALTHY

        unhealthy = [r.name for r in results if r.state == HealthState.UNHEALTHY]
        degraded = [r.name for r in results if r.state == HealthState.DEGRADED]

        msg_parts = []
        if unhealthy:
            msg_parts.append(f"unhealthy: {unhealthy}")
        if degraded:
            msg_parts.append(f"degraded: {degraded}")
        if not msg_parts:
            msg_parts.append("all healthy")

        return ComponentHealth(
            name="system",
            state=overall,
            message="; ".join(msg_parts),
            metadata={
                "components": {
                    r.name: {
                        "state": r.state.value,
                        "latency_ms": round(r.latency_ms, 2),
                        "message": r.message,
                    }
                    for r in results
                }
            },
        )

    def check_component(self, name: str) -> ComponentHealth | None:
        """Run a single component check."""
        with self._lock:
            check_fn = self._checks.get(name)
        if check_fn is None:
            return None
        try:
            return check_fn()
        except Exception as exc:
            return ComponentHealth(
                name=name,
                state=HealthState.UNHEALTHY,
                message=f"Check failed: {type(exc).__name__}: {exc}",
            )
