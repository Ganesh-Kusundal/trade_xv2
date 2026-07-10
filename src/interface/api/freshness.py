"""Data freshness validation for API endpoints.

Ensures market data is not stale before serving it to clients.
Freshness thresholds:
- Intraday (1m-1h): data must be from today (0 days old)
- Daily (1d, 1w): data must be within last 2 trading days
- Weekly+: data must be within last 7 days

Usage:
    from interface.api.freshness import check_data_freshness

    @router.get("/candles")
    async def get_candles(...):
        freshness = check_data_freshness(df, timeframe)
        if freshness.is_stale:
            # Return stale data with warning header
            response.headers["X-Data-Stale"] = "true"
            response.headers["X-Data-Last-Update"] = freshness.last_update.isoformat()
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class FreshnessResult:
    """Result of data freshness check."""

    is_stale: bool
    last_update: date | None
    days_old: int
    threshold_days: int
    status: str  # "FRESH", "STALE", "MISSING"


# Freshness thresholds by timeframe
FRESHNESS_THRESHOLDS = {
    "1m": 0,  # Must be today
    "3m": 0,
    "5m": 0,
    "15m": 0,
    "30m": 0,
    "1h": 0,
    "4h": 1,  # Within last trading day
    "1d": 2,  # Within last 2 trading days
    "1w": 7,  # Within last week
}


def check_data_freshness(
    df: pd.DataFrame,
    timeframe: str,
    timestamp_col: str = "timestamp",
) -> FreshnessResult:
    """Check if market data is fresh enough to serve.

    Parameters
    ----------
    df:
        DataFrame with timestamp column
    timeframe:
        Candle timeframe (1m, 5m, 1d, etc.)
    timestamp_col:
        Name of timestamp column

    Returns
    -------
    FreshnessResult with staleness status
    """
    if df is None or df.empty:
        return FreshnessResult(
            is_stale=True,
            last_update=None,
            days_old=-1,
            threshold_days=FRESHNESS_THRESHOLDS.get(timeframe, 7),
            status="MISSING",
        )

    # Get threshold for this timeframe
    threshold_days = FRESHNESS_THRESHOLDS.get(timeframe, 7)

    # Get latest date in data
    if timestamp_col not in df.columns:
        # Try index
        if isinstance(df.index, pd.DatetimeIndex):
            latest_ts = df.index.max()
        else:
            logger.warning("No timestamp column found in DataFrame")
            return FreshnessResult(
                is_stale=True,
                last_update=None,
                days_old=-1,
                threshold_days=threshold_days,
                status="MISSING",
            )
    else:
        latest_ts = df[timestamp_col].max()

    # Convert to date
    if isinstance(latest_ts, pd.Timestamp | datetime):
        latest_date = latest_ts.date()
    else:
        latest_date = pd.Timestamp(latest_ts).date()

    # Calculate age
    today = date.today()
    days_old = (today - latest_date).days

    # Check staleness
    is_stale = days_old > threshold_days
    status = "FRESH" if not is_stale else "STALE"

    if is_stale:
        logger.warning(
            "Data staleness detected: %s timeframe, %d days old (threshold: %d)",
            timeframe,
            days_old,
            threshold_days,
        )

    return FreshnessResult(
        is_stale=is_stale,
        last_update=latest_date,
        days_old=days_old,
        threshold_days=threshold_days,
        status=status,
    )
