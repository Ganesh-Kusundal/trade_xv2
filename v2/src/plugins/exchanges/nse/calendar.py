"""NSE trading calendar — weekends off; optional holiday set.

ponytail: holiday set empty/few by default — full NSE holiday calendar later.
"""

from __future__ import annotations

from datetime import date


class NSETradingCalendar:
    """Minimal NSE calendar: Sat/Sun + explicit holidays are non-trading."""

    def __init__(self, holidays: set[date] | None = None) -> None:
        self._holidays = holidays if holidays is not None else set()

    def is_trading_day(self, day: date) -> bool:
        if day.weekday() >= 5:  # Saturday=5, Sunday=6
            return False
        return day not in self._holidays
