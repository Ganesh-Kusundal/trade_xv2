"""SystemClock / FakeClock — domain Clock protocol implementations."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

from domain.value_objects import Timestamp


def _to_timestamp(value: Timestamp | datetime | None) -> Timestamp:
    """Convert various time types to Timestamp (nanoseconds UTC)."""
    if value is None:
        return Timestamp(value=time.time_ns())
    if isinstance(value, Timestamp):
        return value
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return Timestamp(value=int(value.timestamp() * 1_000_000_000))
    raise TypeError(f"Unsupported type: {type(value)}")


class SystemClock:
    """Wall-clock UTC. Used for PAPER / LIVE."""

    def now(self) -> Timestamp:
        return Timestamp(value=time.time_ns())

    def advance(self, delta: timedelta) -> None:
        raise NotImplementedError("SystemClock cannot advance")


class FakeClock:
    """Deterministic clock for REPLAY / BACKTEST. Call advance() to move time."""

    def __init__(self, start: Timestamp | datetime | None = None) -> None:
        self._now = _to_timestamp(start)

    def now(self) -> Timestamp:
        return self._now

    def advance(self, delta: timedelta) -> None:
        delta_ns = int(delta.total_seconds() * 1_000_000_000)
        self._now = Timestamp(value=self._now.value + delta_ns)
