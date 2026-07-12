"""NSE TradingCalendar — trading session calendar for the National Stock Exchange of India.

Implements ``domain.ports.TradingCalendar`` (ADR-005). Extracted from
``datalake/core/nse_calendar.py`` (which remains as a thin re-export for
backward compatibility until all callers migrate).
"""

from __future__ import annotations

from datetime import date, time
from zoneinfo import ZoneInfo

# NSE holidays 2020-2026 (official + known special sessions).
_NSE_HOLIDAYS: set[date] = {
    # 2020
    date(2020, 1, 26), date(2020, 2, 21), date(2020, 3, 10),
    date(2020, 4, 2), date(2020, 4, 6), date(2020, 4, 10),
    date(2020, 4, 14), date(2020, 5, 1), date(2020, 5, 25),
    date(2020, 10, 2), date(2020, 11, 16), date(2020, 11, 30),
    date(2020, 12, 25),
    # 2021
    date(2021, 1, 26), date(2021, 3, 11), date(2021, 3, 29),
    date(2021, 4, 2), date(2021, 4, 14), date(2021, 4, 21),
    date(2021, 5, 13), date(2021, 7, 20), date(2021, 8, 19),
    date(2021, 10, 15), date(2021, 11, 4), date(2021, 11, 19),
    date(2021, 12, 25),
    # 2022
    date(2022, 1, 26), date(2022, 3, 1), date(2022, 3, 18),
    date(2022, 4, 14), date(2022, 4, 15), date(2022, 4, 22),
    date(2022, 5, 3), date(2022, 6, 27), date(2022, 8, 9),
    date(2022, 8, 15), date(2022, 10, 5), date(2022, 10, 24),
    date(2022, 11, 8), date(2022, 11, 11), date(2022, 12, 25),
    # 2023
    date(2023, 1, 26), date(2023, 3, 7), date(2023, 3, 30),
    date(2023, 4, 4), date(2023, 4, 7), date(2023, 4, 14),
    date(2023, 6, 29), date(2023, 7, 19), date(2023, 8, 15),
    date(2023, 9, 19), date(2023, 10, 2), date(2023, 10, 24),
    date(2023, 11, 14), date(2023, 11, 27), date(2023, 12, 25),
    # 2024
    date(2024, 1, 26), date(2024, 3, 8), date(2024, 3, 25),
    date(2024, 3, 29), date(2024, 4, 11), date(2024, 4, 14),
    date(2024, 4, 17), date(2024, 4, 21), date(2024, 5, 1),
    date(2024, 5, 23), date(2024, 6, 17), date(2024, 7, 17),
    date(2024, 8, 15), date(2024, 10, 2), date(2024, 11, 1),
    date(2024, 11, 15), date(2024, 12, 25),
    # 2025
    date(2025, 1, 26), date(2025, 2, 26), date(2025, 3, 14),
    date(2025, 3, 31), date(2025, 4, 10), date(2025, 4, 14),
    date(2025, 4, 18), date(2025, 4, 30), date(2025, 5, 1),
    date(2025, 5, 12), date(2025, 6, 27), date(2025, 8, 15),
    date(2025, 10, 2), date(2025, 10, 21), date(2025, 11, 5),
    date(2025, 12, 25),
    # 2026
    date(2026, 1, 26), date(2026, 3, 6), date(2026, 3, 20),
    date(2026, 4, 2), date(2026, 4, 14), date(2026, 4, 17),
    date(2026, 5, 1), date(2026, 6, 19), date(2026, 8, 15),
    date(2026, 10, 2), date(2026, 11, 11), date(2026, 12, 25),
}

# NSE session hours (IST).
MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)


class NseTradingCalendar:
    """NSE trading-session calendar."""

    @property
    def exchange(self) -> str:
        return "NSE"

    @property
    def timezone(self) -> str:
        return "Asia/Kolkata"

    def is_trading_day(self, on: date) -> bool:
        if on.weekday() >= 5:
            return False
        return on not in _NSE_HOLIDAYS

    def session_bounds(self, on: date) -> tuple[time, time]:
        """Return (MARKET_OPEN, MARKET_CLOSE) for the NSE session."""
        return MARKET_OPEN, MARKET_CLOSE

    def expected_bars(self, on: date, bar_seconds: int) -> int:
        """Expected number of bars of ``bar_seconds`` length for session ``on``."""
        if not self.is_trading_day(on):
            return 0
        session_minutes = (
            MARKET_CLOSE.hour * 60 + MARKET_CLOSE.minute
            - MARKET_OPEN.hour * 60 - MARKET_OPEN.minute
        )
        session_seconds = session_minutes * 60
        if bar_seconds <= 0:
            return 0
        return max(1, session_seconds // bar_seconds)
