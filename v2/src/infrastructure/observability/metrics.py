"""In-memory metrics collector (ponytail: no OTLP export yet)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any


class Metrics:
    def __init__(self) -> None:
        self._counters: dict[str, float] = defaultdict(float)
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, list[float]] = defaultdict(list)

    def increment(
        self,
        name: str,
        value: int = 1,
        labels: dict[str, Any] | None = None,
    ) -> None:
        self._counters[self._key(name, labels)] += value

    def observe(
        self,
        name: str,
        value: float,
        labels: dict[str, Any] | None = None,
    ) -> None:
        self._histograms[self._key(name, labels)].append(value)

    def gauge(
        self,
        name: str,
        value: float,
        labels: dict[str, Any] | None = None,
    ) -> None:
        self._gauges[self._key(name, labels)] = value

    def get(self, name: str, labels: dict[str, Any] | None = None) -> float:
        key = self._key(name, labels)
        if key in self._counters:
            return self._counters[key]
        if key in self._gauges:
            return self._gauges[key]
        if key in self._histograms:
            return float(len(self._histograms[key]))
        return 0.0

    @staticmethod
    def _key(name: str, labels: dict[str, Any] | None) -> str:
        if not labels:
            return name
        parts = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{parts}}}"
