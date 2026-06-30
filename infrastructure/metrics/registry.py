"""Metrics registry for centralized metric management."""
from __future__ import annotations

from threading import Lock
from typing import Any

from infrastructure.metrics.types import Counter, Gauge, Histogram, Timer


class MetricsRegistry:
    """Central registry for all application metrics."""
    
    def __init__(self) -> None:
        self._counters: dict[str, Counter] = {}
        self._gauges: dict[str, Gauge] = {}
        self._histograms: dict[str, Histogram] = {}
        self._timers: dict[str, Timer] = {}
        self._lock = Lock()
    
    def counter(self, name: str, description: str = "", labels: dict[str, str] | None = None) -> Counter:
        with self._lock:
            if name not in self._counters:
                self._counters[name] = Counter(name, description, labels)
            return self._counters[name]
    
    def gauge(self, name: str, description: str = "", labels: dict[str, str] | None = None) -> Gauge:
        with self._lock:
            if name not in self._gauges:
                self._gauges[name] = Gauge(name, description, labels)
            return self._gauges[name]
    
    def histogram(self, name: str, description: str = "", labels: dict[str, str] | None = None, buckets: list[float] | None = None) -> Histogram:
        with self._lock:
            if name not in self._histograms:
                self._histograms[name] = Histogram(name, description, labels, buckets)
            return self._histograms[name]
    
    def timer(self, name: str, description: str = "", labels: dict[str, str] | None = None) -> Timer:
        with self._lock:
            if name not in self._timers:
                self._timers[name] = Timer(name, description, labels)
            return self._timers[name]
    
    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "counters": {n: c.value for n, c in self._counters.items()},
                "gauges": {n: g.value for n, g in self._gauges.items()},
                "histograms": {n: len(h.values) for n, h in self._histograms.items()},
                "timers": {n: len(t.values) for n, t in self._timers.items()},
            }
    
    def reset_all(self) -> None:
        with self._lock:
            for c in self._counters.values():
                c.reset()
            for h in self._histograms.values():
                h.reset()
            for t in self._timers.values():
                t.reset()


metrics_registry = MetricsRegistry()