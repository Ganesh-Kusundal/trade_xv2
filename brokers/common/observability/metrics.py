"""Metrics collection for operation monitoring."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class OperationMetrics:
    """Represents metrics for a single operation."""

    operation: str
    latency_ms: float
    success: bool
    error: str = ""


class MetricsCollector:
    """Collects and aggregates operation metrics."""

    def __init__(self) -> None:
        self._metrics: list[OperationMetrics] = []

    def record(self, metrics: OperationMetrics) -> None:
        """Record an operation's metrics."""
        self._metrics.append(metrics)

    def time_operation(self, operation: str, fn: Callable[[], Any]) -> Any:
        """Time a synchronous function execution and record metrics.

        Args:
            operation: Name of the operation being timed.
            fn: Callable to execute.

        Returns:
            The result of calling fn().

        Raises:
            Exception: Re-raises any exception from fn after recording failure metrics.
        """
        start = time.perf_counter()
        try:
            result = fn()
            elapsed_ms = (time.perf_counter() - start) * 1000
            self.record(
                OperationMetrics(
                    operation=operation,
                    latency_ms=elapsed_ms,
                    success=True,
                )
            )
            return result
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000
            self.record(
                OperationMetrics(
                    operation=operation,
                    latency_ms=elapsed_ms,
                    success=False,
                    error=str(exc),
                )
            )
            raise

    def get_all(self) -> list[OperationMetrics]:
        """Return all recorded metrics."""
        return list(self._metrics)

    def get_summary(self) -> dict:
        """Return an aggregated summary of all recorded metrics.

        Returns a dict with keys: total_count, success_count, failure_count,
        avg_latency_ms, and p95_latency_ms.
        """
        if not self._metrics:
            return {
                "total_count": 0,
                "success_count": 0,
                "failure_count": 0,
                "avg_latency_ms": 0.0,
                "p95_latency_ms": 0.0,
            }

        latencies = [m.latency_ms for m in self._metrics]
        success_count = sum(1 for m in self._metrics if m.success)
        failure_count = len(self._metrics) - success_count

        sorted_latencies = sorted(latencies)
        p95_index = int(len(sorted_latencies) * 0.95)
        # Clamp to last valid index
        p95_index = min(p95_index, len(sorted_latencies) - 1)
        p95_latency_ms = sorted_latencies[p95_index]

        return {
            "total_count": len(self._metrics),
            "success_count": success_count,
            "failure_count": failure_count,
            "avg_latency_ms": sum(latencies) / len(latencies),
            "p95_latency_ms": p95_latency_ms,
        }

    def clear(self) -> None:
        """Clear all recorded metrics."""
        self._metrics.clear()
