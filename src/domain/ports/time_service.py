"""Clock port — domain-level boundary for time operations.

A single, injectable clock abstraction so that domain events, schedulers,
and time-dependent logic can run against a *virtual* clock in tests and
replay while defaulting to the real wall clock in production.

Why in domain
--------------
``DomainEvent`` (a domain value object) needs a clock without importing
infrastructure. The ``ClockPort`` Protocol and its default implementations
live here, keeping the dependency arrow clean: domain ← infrastructure
(never the reverse).

Usage
-----
    from domain.ports.time_service import get_current_clock, use_clock, VirtualClock

    # Production: real wall clock (default, no setup needed).
    now = get_current_clock().now()

    # Tests / replay: deterministic virtual clock.
    with use_clock(VirtualClock(initial=some_dt)):
        ...  # every DomainEvent.now() uses the virtual time
"""

from __future__ import annotations

import contextvars
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Protocol, runtime_checkable
from zoneinfo import ZoneInfo

# Exchange → IANA timezone. Kept minimal and pure (stdlib only) so domain
# stays independent of infrastructure. Mirrors the common exchanges defined
# in ``infrastructure.time_service.EXCHANGE_CALENDARS``; unknown exchanges
# fall back to UTC.
_EXCHANGE_TZ: dict[str, str] = {
    "NSE": "Asia/Kolkata",
    "BSE": "Asia/Kolkata",
    "MCX": "Asia/Kolkata",
    "NYSE": "America/New_York",
    "NASDAQ": "America/New_York",
    "LSE": "Europe/London",
}


@runtime_checkable
class ClockPort(Protocol):
    """Protocol for time operations used across the runtime."""

    def now(self) -> datetime:
        """Return the current time as timezone-aware UTC."""

    def timestamp(self) -> float:
        """Return seconds since the Unix epoch (float)."""

    def epoch_ms(self) -> int:
        """Return milliseconds since the Unix epoch (int)."""

    def exchange_now(self, exchange: str) -> datetime:
        """Return the current time in ``exchange``'s local timezone."""


# Backward-compatible alias for the previous (dead) port name.
TimeServicePort = ClockPort


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


_REAL_CLOCK = RealClock()

_clock_var: contextvars.ContextVar[ClockPort | None] = contextvars.ContextVar(
    "clock", default=None
)


def get_current_clock() -> ClockPort:
    """Return the clock active on the current context (defaults to real time)."""
    return _clock_var.get() or _REAL_CLOCK


def set_current_clock(clock: ClockPort) -> None:
    """Set the clock for the current context."""
    _clock_var.set(clock)


@contextmanager
def use_clock(clock: ClockPort) -> Iterator[ClockPort]:
    """Context manager to run a block with a specific clock.

    Example::

        with use_clock(VirtualClock(initial=start)):
            event = DomainEvent.now(...)  # uses virtual time
    """
    token = _clock_var.set(clock)
    try:
        yield clock
    finally:
        _clock_var.reset(token)
