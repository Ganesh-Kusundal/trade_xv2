"""History defaults constants (REF-13)."""

from __future__ import annotations

#: Default pagination window for historical candle downloads (days).
DEFAULT_HISTORY_PAGE_DAYS: int = 365

#: BrokerCapabilities default for max intraday history (days).
DEFAULT_MAX_INTRADAY_DAYS: int = 90

#: BrokerCapabilities default for max multi-day history (days).
DEFAULT_MAX_DAILY_DAYS: int = 365 * 10

__all__ = [
    "DEFAULT_HISTORY_PAGE_DAYS",
    "DEFAULT_MAX_DAILY_DAYS",
    "DEFAULT_MAX_INTRADAY_DAYS",
]
