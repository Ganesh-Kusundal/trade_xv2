"""Metric type definitions for the metrics system."""
from __future__ import annotations

import time
from collections.abc import Generator
from contextlib import contextmanager
from threading import Lock


class Counter:
    """Monotonically increasing counter metric."""

    def __init__(self, name: str, description: str = "", labels: dict[str, str] | None = None) -> None:
        self.name = name
        self.description = description
        self.labels = labels or {}
        self._value: float = 0
        self._lock = Lock()

    def inc(self, value: float = 1.0) -> None:
        with self._lock:
            self._value += value

    def reset(self) -> None:
        with self._lock:
            self._value = 0

    @property
    def value(self) -> float:
        with self._lock:
            return self._value


class Gauge:
    """Up/down gauge metric."""

    def __init__(self, name: str, description: str = "", labels: dict[str, str] | None = None) -> None:
        self.name = name
        self.description = description
        self.labels = labels or {}
        self._value: float = 0
        self._lock = Lock()

    def set(self, value: float) -> None:
        with self._lock:
            self._value = value

    def inc(self, value: float = 1.0) -> None:
        with self._lock:
            self._value += value

    def dec(self, value: float = 1.0) -> None:
        with self._lock:
            self._value -= value

    @property
    def value(self) -> float:
        with self._lock:
            return self._value


class Histogram:
    """Histogram metric for measuring distributions."""

    def __init__(self, name: str, description: str = "", labels: dict[str, str] | None = None, buckets: list[float] | None = None) -> None:
        self.name = name
        self.description = description
        self.labels = labels or {}
        self.buckets = buckets or [.005, .01, .025, .05, .1, .25, .5, 1, 2.5, 5, 10]
        self._values: list[float] = []
        self._lock = Lock()

    def observe(self, value: float) -> None:
        with self._lock:
            self._values.append(value)

    @contextmanager
    def time(self) -> Generator[None, None, None]:
        start = time.monotonic()
        try:
            yield
        finally:
            self.observe(time.monotonic() - start)

    @property
    def values(self) -> list[float]:
        with self._lock:
            return list(self._values)

    def reset(self) -> None:
        with self._lock:
            self._values.clear()


class Timer:
    """Timer metric for measuring operation duration."""

    def __init__(self, name: str, description: str = "", labels: dict[str, str] | None = None) -> None:
        self.name = name
        self.description = description
        self.labels = labels or {}
        self._values: list[float] = []
        self._lock = Lock()

    @contextmanager
    def time(self) -> Generator[None, None, None]:
        start = time.monotonic()
        try:
            yield
        finally:
            self.observe(time.monotonic() - start)

    def observe(self, value: float) -> None:
        with self._lock:
            self._values.append(value)

    @property
    def values(self) -> list[float]:
        with self._lock:
            return list(self._values)

    def reset(self) -> None:
        with self._lock:
            self._values.clear()
