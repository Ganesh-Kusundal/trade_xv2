"""Centralized time service for TradeXV2 — single wall-clock entry point.

Provides a single source of truth for all time-related operations.
Handles timezone conversion, exchange calendars, and timestamp formatting.

**Canonical implementation.** Streaming / composer / provenance should import
the same singleton via ``infrastructure.time.clock`` (thin re-export)::

    from infrastructure.time.clock import time_service
    # or equivalently:
    from infrastructure.time_service import time_service

Contract
--------
- ``now()`` returns **timezone-aware UTC** (``datetime`` with ``tzinfo=timezone.utc``).
- ``exchange_now(exchange)`` returns **exchange-local** time (e.g. NSE → Asia/Kolkata).
- Callers **must not** use naive ``datetime.now()`` for order, audit, stream, or
  reconnect timestamps — always go through this service (or the clock re-export).

Usage::

    now = time_service.now()
    exchange_time = time_service.exchange_now("NSE")
    formatted = time_service.format_timestamp(now)
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


class ExchangeCalendar:
    """Exchange-specific time handling."""

    def __init__(self, tz_name: str, name: str) -> None:
        self.tz = ZoneInfo(tz_name)
        self.name = name

    def now(self) -> datetime:
        return datetime.now(self.tz)


EXCHANGE_CALENDARS: dict[str, ExchangeCalendar] = {
    "NSE": ExchangeCalendar("Asia/Kolkata", "NSE"),
    "BSE": ExchangeCalendar("Asia/Kolkata", "BSE"),
    "MCX": ExchangeCalendar("Asia/Kolkata", "MCX"),
    "NYSE": ExchangeCalendar("America/New_York", "NYSE"),
    "NASDAQ": ExchangeCalendar("America/New_York", "NASDAQ"),
    "LSE": ExchangeCalendar("Europe/London", "LSE"),
}


class TimeService:
    """Centralized wall clock and exchange calendars.

    - ``now()`` — UTC, timezone-aware (order / audit / stream timestamps).
    - ``exchange_now(exchange)`` — exchange-local timezone-aware datetime.
    - Do not call naive ``datetime.now()`` at call sites; use this service.
    """

    def now(self) -> datetime:
        """Return current time as timezone-aware UTC."""
        return datetime.now(timezone.utc)

    def timestamp(self) -> float:
        return time.time()

    def exchange_now(self, exchange: str) -> datetime:
        """Return current time in the exchange's local timezone."""
        calendar = EXCHANGE_CALENDARS.get(exchange)
        if not calendar:
            raise ValueError(f"Unknown exchange: {exchange}")
        return calendar.now()

    def format_timestamp(self, dt: datetime | None = None, fmt: str = "%Y-%m-%dT%H:%M:%S.%fZ") -> str:
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
