"""SystemClock / FakeClock — domain Clock protocol implementations."""

from __future__ import annotations

import time
from datetime import timedelta

from domain.value_objects import Timestamp


class SystemClock:
    """Wall-clock UTC. Used for PAPER / LIVE."""

    def now(self) -> Timestamp:
        return Timestamp(value=time.time_ns())

    def advance(self, delta: timedelta) -> None:
        raise NotImplementedError("SystemClock cannot advance")


class FakeClock:
    """Deterministic clock for REPLAY / BACKTEST. Call advance() to move time."""

    def __init__(self, start: Timestamp | None = None) -> None:
        self._now = start if start is not None else Timestamp(value=time.time_ns())

    def now(self) -> Timestamp:
        return self._now

    def advance(self, delta: timedelta) -> None:
        # Convert timedelta to nanoseconds and add
        delta_ns = int(delta.total_seconds() * 1_000_000_000)
        self._now = Timestamp(value=self._now.value + delta_ns)
