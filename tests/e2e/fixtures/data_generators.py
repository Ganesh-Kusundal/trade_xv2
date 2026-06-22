"""Synthetic market data generators for deterministic E2E tests.

All generators are deterministic given the same seed.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import numpy as np
import pandas as pd


def generate_ohlcv_data(
    n_bars: int = 100,
    start_price: float = 100.0,
    symbol: str = "RELIANCE",
    seed: int = 42,
    start_date: datetime | None = None,
    timeframe_minutes: int = 1,
) -> pd.DataFrame:
    """Generate deterministic OHLCV data with random walk.

    Parameters
    ----------
    n_bars : int
        Number of bars to generate.
    start_price : float
        Initial close price.
    symbol : str
        Symbol name.
    seed : int
        Random seed for reproducibility.
    start_date : datetime | None
        Start timestamp. Defaults to 2026-01-01 09:15 IST.
    timeframe_minutes : int
        Minutes between bars.

    Returns
    -------
    pd.DataFrame with columns: timestamp, open, high, low, close, volume, symbol
    """
    rng = np.random.RandomState(seed)

    if start_date is None:
        start_date = datetime(2026, 1, 1, 9, 15, tzinfo=timezone.utc)

    timestamps = [start_date + timedelta(minutes=i * timeframe_minutes) for i in range(n_bars)]

    # Random walk for close price
    returns = rng.randn(n_bars) * 0.002  # 0.2% daily volatility
    close = start_price * np.cumprod(1 + returns)

    # Derive OHLC from close
    high = close + abs(rng.randn(n_bars)) * 0.5
    low = close - abs(rng.randn(n_bars)) * 0.5
    open_ = close + rng.randn(n_bars) * 0.3
    volume = rng.randint(10000, 100000, n_bars).astype(float)

    # Ensure high >= close >= low
    high = np.maximum(high, close)
    low = np.minimum(low, close)

    return pd.DataFrame({
        "timestamp": timestamps,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "symbol": symbol,
    })


def generate_multi_symbol_data(
    symbols: list[str] | None = None,
    n_bars: int = 100,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate OHLCV data for multiple symbols.

    Parameters
    ----------
    symbols : list[str] | None
        List of symbols. Defaults to ["RELIANCE", "TCS", "HDFCBANK"].
    n_bars : int
        Bars per symbol.
    seed : int
        Random seed.

    Returns
    -------
    pd.DataFrame with combined data for all symbols.
    """
    if symbols is None:
        symbols = ["RELIANCE", "TCS", "HDFCBANK"]

    frames = []
    for i, sym in enumerate(symbols):
        df = generate_ohlcv_data(
            n_bars=n_bars,
            start_price=100.0 + i * 50,
            symbol=sym,
            seed=seed + i,
        )
        frames.append(df)

    return pd.concat(frames, ignore_index=True)


def generate_trending_data(
    n_bars: int = 100,
    start_price: float = 100.0,
    symbol: str = "TREND",
    trend_strength: float = 0.003,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate OHLCV data with a clear upward trend.

    Useful for testing momentum strategies that require trending data.

    Parameters
    ----------
    trend_strength : float
        Average return per bar (positive for uptrend).
    """
    rng = np.random.RandomState(seed)
    start_date = datetime(2026, 1, 1, 9, 15, tzinfo=timezone.utc)
    timestamps = [start_date + timedelta(minutes=i) for i in range(n_bars)]

    # Trend + noise
    returns = trend_strength + rng.randn(n_bars) * 0.001
    close = start_price * np.cumprod(1 + returns)

    high = close + abs(rng.randn(n_bars)) * 0.3
    low = close - abs(rng.randn(n_bars)) * 0.3
    open_ = close + rng.randn(n_bars) * 0.1
    volume = rng.randint(50000, 200000, n_bars).astype(float)

    high = np.maximum(high, close)
    low = np.minimum(low, close)

    return pd.DataFrame({
        "timestamp": timestamps,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "symbol": symbol,
    })


def generate_mean_reverting_data(
    n_bars: int = 100,
    start_price: float = 100.0,
    symbol: str = "MEANREV",
    mean: float = 100.0,
    reversion_speed: float = 0.05,
    volatility: float = 0.01,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate OHLCV data that mean-reverts around a target price.

    Uses Ornstein-Uhlenbeck process for realistic mean-reverting behavior.

    Parameters
    ----------
    mean : float
        Long-term mean price.
    reversion_speed : float
        How quickly price reverts to mean.
    volatility : float
        Noise level.
    """
    rng = np.random.RandomState(seed)
    start_date = datetime(2026, 1, 1, 9, 15, tzinfo=timezone.utc)
    timestamps = [start_date + timedelta(minutes=i) for i in range(n_bars)]

    # Ornstein-Uhlenbeck process
    close = np.zeros(n_bars)
    close[0] = start_price
    for i in range(1, n_bars):
        close[i] = close[i-1] + reversion_speed * (mean - close[i-1]) + volatility * rng.randn()

    high = close + abs(rng.randn(n_bars)) * 0.5
    low = close - abs(rng.randn(n_bars)) * 0.5
    open_ = close + rng.randn(n_bars) * 0.2
    volume = rng.randint(10000, 80000, n_bars).astype(float)

    high = np.maximum(high, close)
    low = np.minimum(low, close)

    return pd.DataFrame({
        "timestamp": timestamps,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "symbol": symbol,
    })
