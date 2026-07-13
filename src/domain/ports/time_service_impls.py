"""Concrete clock implementations — RealClock and VirtualClock.

Moved out of ``domain.ports.time_service`` to keep ports focused on the
Protocol and context-management functions.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

_EXCHANGE_TZ: dict[str, str] = {
    "NSE": "Asia/Kolkata",
    "BSE": "Asia/Kolkata",
    "MCX": "Asia/Kolkata",
    "NYSE": "America/New_York",
    "NASDAQ": "America/New_York",
    "LSE": "Europe/London",
}


class RealClock:
    """Wall-clock implementation of :class:`ClockPort`."""

    def now(self) -> datetime:
        return datetime.now(timezone.utc)

    def timestamp(self) -> float:
        return datetime.now(timezone.utc).timestamp()

    def epoch_ms(self) -> int:
        return int(self.timestamp() * 1000)

    def exchange_now(self, exchange: str) -> datetime:
        tz_name = _EXCHANGE_TZ.get(exchange, "UTC")
        return datetime.now(ZoneInfo(tz_name))


class VirtualClock:
    """Mutable, deterministic clock for tests and replay.

    Holds an internal ``datetime`` (timezone-aware UTC) that can be set or
    advanced. Every call to ``now()`` returns the current virtual time,
    enabling fully deterministic event timestamps, scheduling, and
    reconciliation loops.
    """

    def __init__(self, initial: datetime | None = None) -> None:
        self._current = initial or datetime.now(timezone.utc)

    def now(self) -> datetime:
        return self._current

    def timestamp(self) -> float:
        return self._current.timestamp()

    def epoch_ms(self) -> int:
        return int(self._current.timestamp() * 1000)

    def exchange_now(self, exchange: str) -> datetime:
        # Virtual clocks are UTC-only; exchange-local conversion would
        # require a calendar we intentionally avoid importing. Callers
        # needing exchange-local virtual time can advance the clock manually.
        return self._current

    def set(self, value: datetime) -> None:
        """Set the virtual time absolutely (naive values treated as UTC)."""
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        self._current = value

    def advance(self, delta: timedelta) -> None:
        """Advance the virtual time by ``delta``."""
        self._current = self._current + delta

    @property
    def current(self) -> datetime:
        return self._current
