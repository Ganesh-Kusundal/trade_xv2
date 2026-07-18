"""Shared data helper functions for tests.

Provides reusable factories for creating synthetic market data (OHLCV DataFrames)
in a consistent manner across all test files.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd


def make_ohlcv(
    n: int = 100,
    start_price: float = 100.0,
    symbol: str = "TEST",
    seed: int = 42,
    start_date: datetime | None = None,
    timeframe_minutes: int = 1,
    trend: str = "flat",
) -> pd.DataFrame:
    """Generate deterministic OHLCV data with random walk.

    Parameters
    ----------
    n : int
        Number of bars to generate.
    start_price : float
        Initial close price.
    symbol : str
        Symbol name.
    seed : int
        Random seed for reproducibility.
    start_date : datetime | None
        Start timestamp. Defaults to 2026-01-01 09:15 UTC.
    timeframe_minutes : int
        Minutes between bars.
    trend : str
        Trend direction: "up", "down", or "flat" (default).

    Returns
    -------
    pd.DataFrame with columns: timestamp, open, high, low, close, volume, symbol
    """
    rng = np.random.RandomState(seed)

    if start_date is None:
        start_date = datetime(2026, 1, 1, 9, 15, tzinfo=timezone.utc)

    timestamps = [start_date + timedelta(minutes=i * timeframe_minutes) for i in range(n)]

    # Random walk for close price
    if trend == "up":
        returns = rng.randn(n) * 0.002 + 0.001
    elif trend == "down":
        returns = rng.randn(n) * 0.002 - 0.001
    else:
        returns = rng.randn(n) * 0.002

    close = start_price * np.cumprod(1 + returns)

    # Derive OHLC from close
    high = close + abs(rng.randn(n)) * 0.5
    low = close - abs(rng.randn(n)) * 0.5
    open_ = close + rng.randn(n) * 0.3
    volume = rng.randint(10000, 100000, n).astype(float)

    # Ensure high >= close >= low
    high = np.maximum(high, close)
    low = np.minimum(low, close)

    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "symbol": symbol,
        }
    )
