"""NSE exchange plugin."""

from __future__ import annotations

from plugins.exchanges.nse.calendar import NSETradingCalendar


def register() -> dict[str, object]:
    """Entry-point hook for tradex.exchanges — returns calendar surface."""
    return {"exchange_id": "NSE", "calendar": NSETradingCalendar()}
