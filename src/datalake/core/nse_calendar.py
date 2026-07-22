"""NSE market holiday calendar — compatibility shim (ADR-005).

Canonical calendar lives in ``plugins.exchanges.nse`` and is accessed via
``datalake.exchange_registry``. This module re-exports registry helpers for
legacy callers; new code must import from ``datalake.exchange_registry``.
"""

from __future__ import annotations

from datetime import date

from datalake.exchange_registry import (
    COMPLETENESS_OK_FRACTION,
    count_trading_days,
    expected_candles,
    expected_candles_per_day,
    is_trading_day,
    trading_days_between,
)

# Early close not modeled on TradingCalendar port yet.
_EARLY_CLOSE_DAYS: set[date] = set()


def is_early_close(d: date) -> bool:
    """Check if a date is an early close day."""
    return d in _EARLY_CLOSE_DAYS


# Re-export session constants for tests that referenced module attrs.
REGULAR_SESSION_MINUTES: int = 375
EARLY_CLOSE_SESSION_MINUTES: int = 255
TIMEFRAME_MINUTES: dict[str, int] = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60}

__all__ = [
    "COMPLETENESS_OK_FRACTION",
    "EARLY_CLOSE_SESSION_MINUTES",
    "REGULAR_SESSION_MINUTES",
    "TIMEFRAME_MINUTES",
    "count_trading_days",
    "expected_candles",
    "expected_candles_per_day",
    "is_early_close",
    "is_trading_day",
    "trading_days_between",
]
