"""Centralized time service for TradeXV2 — single wall-clock entry point.

Provides a single source of truth for all time-related operations.
Handles timezone conversion, exchange calendars, and timestamp formatting.

**Canonical implementation.** All modules should import from here::

    from infrastructure.time_service import time_service

Supports dependency injection via ``TimeService.with_clock(...)`` for
deterministic tests. Default uses the real system clock.

Contract
--------
- ``now()`` returns **timezone-aware UTC** (``datetime`` with ``tzinfo=timezone.utc``).
- ``exchange_now(exchange)`` returns **exchange-local** time (e.g. NSE → Asia/Kolkata).
- Callers **must not** use naive ``datetime.now()`` for order, audit, stream, or
  reconnect timestamps — always go through this service.

Usage::

    now = time_service.now()
    exchange_time = time_service.exchange_now("NSE")
    formatted = time_service.format_timestamp(now)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Union
from zoneinfo import ZoneInfo

from domain.ports.time_service_impls import EXCHANGE_TZ
from domain.primitives.value_objects import Clock


ClockSource = Union[Clock, Callable[[], datetime], Any]


class ExchangeCalendar:
    """Exchange-specific time handling."""

    def __init__(self, tz_name: str, name: str) -> None:
        self.tz = ZoneInfo(tz_name)
        self.name = name

    def now(self) -> datetime:
        return datetime.now(self.tz)


#: Derived from the canonical ``domain.ports.time_service_impls.EXCHANGE_TZ``
#: map so the per-exchange timezone is defined in exactly one place.
EXCHANGE_CALENDARS: dict[str, ExchangeCalendar] = {
    exchange: ExchangeCalendar(tz_name, exchange) for exchange, tz_name in EXCHANGE_TZ.items()
}


class SystemClock:
    """Real wall-clock implementation (the production default)."""

    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class FakeClock:
    """Deterministic, controllable clock for tests, replay, and simulation.

    Holds an internal timezone-aware UTC ``datetime`` that can be set or
    advanced. Every ``now()`` returns the current virtual time, so callers get
    fully reproducible timestamps, scheduling, and reconciliation loops.
    """

    def __init__(self, initial: datetime | None = None) -> None:
        if initial is None:
            initial = datetime(2000, 1, 1, tzinfo=timezone.utc)
        elif initial.tzinfo is None:
            initial = initial.replace(tzinfo=timezone.utc)
        self._current = initial

    def now(self) -> datetime:
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


def _wrap(source: ClockSource | None) -> Clock:
    """Coerce an injected source into a :class:`Clock`."""
    if source is None:
        return Clock(_now=SystemClock().now)
    if isinstance(source, Clock):
        return source
    if hasattr(source, "now") and callable(getattr(source, "now")):
        return Clock(_now=source.now)
    if callable(source):
        return Clock(_now=source)
    raise TypeError(f"cannot build a Clock from {type(source).__name__!r}")


@dataclass
class TimeService:
    """Centralized wall clock and exchange calendars.

    Default uses the real system clock. Inject a :class:`FakeClock` or any
    ``now`` callable via ``TimeService.with_clock(...)`` for deterministic
    tests.

    - ``now()`` — UTC, timezone-aware (order / audit / stream timestamps).
    - ``exchange_now(exchange)`` — exchange-local timezone-aware datetime.
    - Do not call naive ``datetime.now()`` at call sites; use this service.
    """

    clock: Clock = field(default_factory=lambda: Clock(_now=SystemClock().now))

    @classmethod
    def with_clock(cls, source: ClockSource) -> TimeService:
        """Build a ``TimeService`` around an injected clock source.

        Accepts a :class:`Clock`, a ``Clock``-like instance with a ``now()``
        method (e.g. :class:`FakeClock`), or a bare ``Callable[[], datetime]``.
        """
        return cls(clock=_wrap(source))

    def now(self) -> datetime:
        """Return the current time from the injected clock (UTC, timezone-aware)."""
        return self.clock.now()

    def now_utc(self) -> datetime:
        """Alias for :meth:`now` (results are timezone-aware UTC)."""
        return self.clock.now()

    def timestamp(self) -> float:
        return time.time()

    def exchange_now(self, exchange: str) -> datetime:
        """Return current time in the exchange's local timezone."""
        calendar = EXCHANGE_CALENDARS.get(exchange)
        if not calendar:
            raise ValueError(f"Unknown exchange: {exchange}")
        return calendar.now()

    def format_timestamp(
        self, dt: datetime | None = None, fmt: str = "%Y-%m-%dT%H:%M:%S.%fZ"
    ) -> str:
        if dt is None:
            dt = self.now()
        return dt.strftime(fmt)

    def parse_iso(self, iso_str: str) -> datetime:
        return datetime.fromisoformat(iso_str.replace("Z", "+00:00"))

    def epoch_now(self) -> int:
        return int(time.time())

    def epoch_ms(self) -> int:
        return int(time.time() * 1000)


time_service = TimeService()
