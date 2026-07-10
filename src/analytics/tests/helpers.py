"""Shared test utilities for analytics tests."""

from __future__ import annotations

import pandas as pd


def prices(n: int = 50, start: float = 100.0, trend: float = 1.0) -> pd.DataFrame:
    """Generate synthetic OHLCV data for testing."""
    closes = [start + i * trend + (-1) ** i * 0.3 for i in range(n)]
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=n, freq="D"),
            "open": [c - 0.2 for c in closes],
            "high": [c + 1.5 for c in closes],
            "low": [c - 1.5 for c in closes],
            "close": closes,
            "volume": [1000 + (i % 5) * 100 for i in range(n)],
        }
    )


def option_chain() -> pd.DataFrame:
    """Generate synthetic option chain data for testing."""
    return pd.DataFrame(
        [
            {
                "strike": 100,
                "option_type": "CE",
                "oi": 100,
                "change_in_oi": 20,
                "volume": 500,
                "iv": 0.20,
                "ltp": 5.0,
            },
            {
                "strike": 110,
                "option_type": "CE",
                "oi": 80,
                "change_in_oi": -10,
                "volume": 300,
                "iv": 0.25,
                "ltp": 3.0,
            },
            {
                "strike": 100,
                "option_type": "PE",
                "oi": 90,
                "change_in_oi": 15,
                "volume": 400,
                "iv": 0.22,
                "ltp": 4.0,
            },
            {
                "strike": 90,
                "option_type": "PE",
                "oi": 70,
                "change_in_oi": -5,
                "volume": 200,
                "iv": 0.28,
                "ltp": 6.0,
            },
        ]
    )


def trades() -> pd.DataFrame:
    """Generate synthetic trade data for testing."""
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=30, freq="1min"),
            "price": [100 + i * 0.1 for i in range(30)],
            "quantity": [10 + (i % 3) * 5 for i in range(30)],
            "side": ["BUY"] * 18 + ["SELL"] * 12,
        }
    )
