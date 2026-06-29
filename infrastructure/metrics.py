"""Metrics collection for observability.

P5 Stability Engineering: Provides metrics collection for tracking latency,
throughput, error rates, and business metrics. Supports both in-memory
collection (for testing) and export to monitoring systems.

Features:
- Counter metrics (monotonically increasing)
- Gauge metrics (current value, can go up/down)
- Histogram metrics (distribution of values)
- Automatic labeling with correlation IDs
- Thread-safe collection
- Export to JSON for monitoring integration

Usage:
    from infrastructure.metrics import get_metrics_collector
    
    metrics = get_metrics_collector()
    
    # Count events
    metrics.increment("orders.placed", labels={"broker": "dhan"})
    
    # Track latency
    metrics.observe_histogram("order.latency_ms", 45.2, labels={"broker": "dhan"})
    
    # Set current value
    metrics.set_gauge("positions.open", 5)
    
    # Export for monitoring
    snapshot = metrics.get_snapshot()
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MetricLabels:
    """Labels for metric dimensions."""

    _labels: dict[str, str] = field(default_factory=dict)

    def set(self, key: str, value: str) -> None:
        """Set a label value."""
        self._labels[key] = value

    def get(self, key: str) -> str | None:
        """Get a label value."""
        return self._labels.get(key)

    def to_dict(self) -> dict[str, str]:
        """Convert to dictionary."""
        return dict(self._labels)

    def __hash__(self) -> int:
        return hash(tuple(sorted(self._labels.items())))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, MetricLabels):
            return False
        return self._labels == other._labels


@dataclass
class CounterMetric:
    """Monotonically increasing counter."""

    name: str
    labels: MetricLabels
    value: int = 0

    def increment(self, amount: int = 1) -> None:
        """Increment counter by amount."""
        if amount < 0:
            raise ValueError("Counter can only be incremented")
        self.value += amount

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for export."""
        return {
            "name": self.name,
            "type": "counter",
            "value": self.value,
            "labels": self.labels.to_dict(),
        }


@dataclass
class GaugeMetric:
    """Gauge metric that can go up and down."""

    name: str
    labels: MetricLabels
    value: float = 0.0

    def set(self, value: float) -> None:
        """Set gauge to value."""
        self.value = value

    def increment(self, delta: float = 1.0) -> None:
        """Increment gauge by delta."""
        self.value += delta

    def decrement(self, delta: float = 1.0) -> None:
        """Decrement gauge by delta."""
        self.value -= delta

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for export."""
        return {
            "name": self.name,
            "type": "gauge",
            "value": self.value,
            "labels": self.labels.to_dict(),
        }


@dataclass
class HistogramMetric:
    """Histogram metric for tracking distributions."""

    name: str
    labels: MetricLabels
    samples: list[float] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def observe(self, value: float) -> None:
        """Record an observation."""
        with self._lock:
            self.samples.append(value)

    def get_statistics(self) -> dict[str, float]:
        """Get histogram statistics."""
        with self._lock:
            if not self.samples:
                return {
                    "count": 0,
                    "sum": 0.0,
                    "min": 0.0,
                    "max": 0.0,
                    "avg": 0.0,
                    "p50": 0.0,
                    "p95": 0.0,
                    "p99": 0.0,
                }

            sorted_samples = sorted(self.samples)
            count = len(sorted_samples)
            total = sum(sorted_samples)

            return {
                "count": count,
                "sum": total,
                "min": sorted_samples[0],
                "max": sorted_samples[-1],
                "avg": total / count,
                "p50": sorted_samples[int(count * 0.50)],
                "p95": sorted_samples[min(int(count * 0.95), count - 1)],
                "p99": sorted_samples[min(int(count * 0.99), count - 1)],
            }

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for export."""
        stats = self.get_statistics()
        return {
            "name": self.name,
            "type": "histogram",
            "labels": self.labels.to_dict(),
            **stats,
        }


class MetricsCollector:
    """Thread-safe metrics collector."""

    def __init__(self) -> None:
        self._counters: dict[tuple[str, MetricLabels], CounterMetric] = {}
        self._gauges: dict[tuple[str, MetricLabels], GaugeMetric] = {}
        self._histograms: dict[tuple[str, MetricLabels], HistogramMetric] = {}
        self._lock = threading.Lock()

    def increment(self, name: str, labels: dict[str, str] | None = None, amount: int = 1) -> None:
        """Increment a counter metric.

        Args:
            name: Metric name (e.g., "orders.placed")
            labels: Dimensional labels (e.g., {"broker": "dhan"})
            amount: Amount to increment (must be positive)
        """
        label_obj = MetricLabels(labels or {})
        key = (name, label_obj)

        with self._lock:
            if key not in self._counters:
                self._counters[key] = CounterMetric(name, label_obj)
            self._counters[key].increment(amount)

    def set_gauge(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        """Set a gauge metric.

        Args:
            name: Metric name (e.g., "positions.open")
            value: Current value
            labels: Dimensional labels
        """
        label_obj = MetricLabels(labels or {})
        key = (name, label_obj)

        with self._lock:
            if key not in self._gauges:
                self._gauges[key] = GaugeMetric(name, label_obj)
            self._gauges[key].set(value)

    def observe_histogram(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        """Record a histogram observation.

        Args:
            name: Metric name (e.g., "order.latency_ms")
            value: Observed value
            labels: Dimensional labels
        """
        label_obj = MetricLabels(labels or {})
        key = (name, label_obj)

        with self._lock:
            if key not in self._histograms:
                self._histograms[key] = HistogramMetric(name, label_obj)
            self._histograms[key].observe(value)

    def get_snapshot(self) -> dict[str, Any]:
        """Get snapshot of all metrics for export.

        Returns:
            Dictionary containing all metrics with their current values
        """
        with self._lock:
            return {
                "counters": [m.to_dict() for m in self._counters.values()],
                "gauges": [m.to_dict() for m in self._gauges.values()],
                "histograms": [m.to_dict() for m in self._histograms.values()],
                "timestamp": time.time(),
            }

    def reset(self) -> None:
        """Reset all metrics (useful for testing)."""
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()


# Global metrics collector instance
_global_metrics: MetricsCollector | None = None
_metrics_lock = threading.Lock()


def get_metrics_collector() -> MetricsCollector:
    """Get or create the global metrics collector.

    Returns:
        Global MetricsCollector instance
    """
    global _global_metrics

    if _global_metrics is None:
        with _metrics_lock:
            if _global_metrics is None:
                _global_metrics = MetricsCollector()

    return _global_metrics


def reset_metrics_collector() -> None:
    """Reset the global metrics collector (for testing)."""
    global _global_metrics
    with _metrics_lock:
        if _global_metrics is not None:
            _global_metrics.reset()
            _global_metrics = None


# Convenience functions for common metrics
def track_order_placement(broker: str, latency_ms: float) -> None:
    """Track order placement metrics.

    Args:
        broker: Broker name (e.g., "dhan", "upstox")
        latency_ms: Order placement latency in milliseconds
    """
    metrics = get_metrics_collector()
    metrics.increment("orders.placed", labels={"broker": broker})
    metrics.observe_histogram("order.latency_ms", latency_ms, labels={"broker": broker})


def track_order_cancellation(broker: str, latency_ms: float) -> None:
    """Track order cancellation metrics.

    Args:
        broker: Broker name
        latency_ms: Cancellation latency in milliseconds
    """
    metrics = get_metrics_collector()
    metrics.increment("orders.cancelled", labels={"broker": broker})
    metrics.observe_histogram("order.cancel_latency_ms", latency_ms, labels={"broker": broker})


def track_trade_execution(broker: str, symbol: str, latency_ms: float) -> None:
    """Track trade execution metrics.

    Args:
        broker: Broker name
        symbol: Trading symbol
        latency_ms: Execution latency in milliseconds
    """
    metrics = get_metrics_collector()
    metrics.increment("trades.executed", labels={"broker": broker, "symbol": symbol})
    metrics.observe_histogram("trade.latency_ms", latency_ms, labels={"broker": broker, "symbol": symbol})


def track_error(component: str, error_type: str) -> None:
    """Track error metrics.

    Args:
        component: Component where error occurred (e.g., "order_manager", "broker_gateway")
        error_type: Error type (e.g., "ValidationError", "NetworkError")
    """
    metrics = get_metrics_collector()
    metrics.increment("errors.total", labels={"component": component, "error_type": error_type})


def track_event_processing(event_type: str, latency_ms: float, success: bool = True) -> None:
    """Track event processing metrics.

    Args:
        event_type: Event type (e.g., "ORDER_UPDATED", "TRADE")
        latency_ms: Processing latency in milliseconds
        success: Whether processing was successful
    """
    metrics = get_metrics_collector()
    status = "success" if success else "failed"
    metrics.increment(f"events.{status}", labels={"event_type": event_type})
    metrics.observe_histogram("event.processing_latency_ms", latency_ms, labels={"event_type": event_type})


__all__ = [
    "CounterMetric",
    "GaugeMetric",
    "HistogramMetric",
    "MetricLabels",
    "MetricsCollector",
    "get_metrics_collector",
    "reset_metrics_collector",
    "track_error",
    "track_event_processing",
    "track_order_cancellation",
    "track_order_placement",
    "track_trade_execution",
]
