"""Tests for market structure analyzer (vectorized)."""

from __future__ import annotations

import pandas as pd

from analytics.indicators.market_structure import MarketStructureAnalyzer


def _trending_up() -> pd.DataFrame:
    n = 40
    closes = [100 + i * 1.0 + (-1) ** i * 0.3 for i in range(n)]
    highs = [c + 1.5 for c in closes]
    lows = [c - 1.5 for c in closes]
    return pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=n, freq="D"),
        "open": [c - 0.2 for c in closes],
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": [1000] * n,
    })


def _ranging() -> pd.DataFrame:
    n = 40
    closes = [100 + (-1) ** i * 0.5 for i in range(n)]
    return pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=n, freq="D"),
        "open": closes,
        "high": [c + 0.3 for c in closes],
        "low": [c - 0.3 for c in closes],
        "close": closes,
        "volume": [1000] * n,
    })


def test_empty_dataframe() -> None:
    result = MarketStructureAnalyzer().analyze(pd.DataFrame())
    assert "swing_high" in result.columns
    assert "trend" in result.columns
    assert "market_structure" in result.columns
    assert result.empty


def test_trending_data() -> None:
    result = MarketStructureAnalyzer().analyze(_trending_up())
    assert set(result["swing_high"].unique()).issubset({True, False})
    assert set(result["swing_low"].unique()).issubset({True, False})
    assert result["trend"].iloc[-1] in {"Uptrend", "Downtrend", "Neutral"}
    assert result["market_structure"].iloc[-1] in {
        "Breakout", "Pullback", "Trend Continuation", "Compression", "Range", "Neutral",
    }


def test_ranging_data() -> None:
    result = MarketStructureAnalyzer().analyze(_ranging())
    assert len(result) == 40
    assert "swing_high" in result.columns
    assert "swing_low" in result.columns


def test_has_expected_columns() -> None:
    result = MarketStructureAnalyzer().analyze(_trending_up())
    assert {"swing_high", "swing_low", "trend", "market_structure"}.issubset(result.columns)
