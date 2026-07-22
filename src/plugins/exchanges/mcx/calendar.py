"""MCX TradingCalendar — trading session calendar for Multi Commodity Exchange of India.

Implements ``domain.ports.TradingCalendar`` (ADR-005). MCX commodity
sessions run ~09:00–23:30 IST with weekend skip; holidays are maintained
in ``_MCX_HOLIDAYS`` (empty until sourced from official circulars).
"""

from __future__ import annotations

from datetime import date, time

from domain.constants.market import (
    MCX_CLOSE_HOUR_IST,
    MCX_CLOSE_MINUTE_IST,
    MCX_OPEN_HOUR_IST,
    MCX_OPEN_MINUTE_IST,
)

# ponytail: empty until MCX holiday circulars are ingested; weekend skip only.
_MCX_HOLIDAYS: set[date] = set()

MARKET_OPEN: time = time(MCX_OPEN_HOUR_IST, MCX_OPEN_MINUTE_IST)
MARKET_CLOSE: time = time(MCX_CLOSE_HOUR_IST, MCX_CLOSE_MINUTE_IST)


class McxTradingCalendar:
    """MCX trading-session calendar."""

    @property
    def exchange(self) -> str:
        return "MCX"

    @property
    def timezone(self) -> str:
        return "Asia/Kolkata"

    def is_trading_day(self, on: date) -> bool:
        if on.weekday() >= 5:
            return False
        return on not in _MCX_HOLIDAYS

    def session_bounds(self, on: date) -> tuple[time, time]:
        """Return (MARKET_OPEN, MARKET_CLOSE) for the MCX session."""
        return MARKET_OPEN, MARKET_CLOSE

    def expected_bars(self, on: date, bar_seconds: int) -> int:
        """Expected number of bars of ``bar_seconds`` length for session ``on``."""
        if not self.is_trading_day(on):
            return 0
        session_minutes = (
            MARKET_CLOSE.hour * 60
            + MARKET_CLOSE.minute
            - MARKET_OPEN.hour * 60
            - MARKET_OPEN.minute
        )
        session_seconds = session_minutes * 60
        if bar_seconds <= 0:
            return 0
        return max(1, session_seconds // bar_seconds)
