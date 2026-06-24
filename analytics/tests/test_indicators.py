"""Tests for technical indicators — migrated to analytics.pipeline.features.

These tests verify parity with the deprecated analytics.indicators.technical
module by testing the canonical Feature classes from analytics.pipeline.features.
"""
from __future__ import annotations

import math

import pandas as pd
import pytest

from analytics.pipeline.features import (
    ATR,
    EMA,
    MACD,
    ROC,
    RSI,
    SMA,
    VWAP,
    BollingerBands,
    HistoricalVolatility,
    Momentum,
)


# ── Helpers — inlined from deprecated analytics.indicators.technical ────────

def _acceleration(prices: pd.Series, periods: int = 1) -> pd.Series:
    """Price acceleration (second derivative)."""
    return prices.pct_change(periods=periods).diff().fillna(0)


def _iv_rank(current_iv: float, iv_low: float, iv_high: float) -> float:
    """IV Rank (position of current IV in historical range)."""
    if iv_high <= iv_low:
        return 50.0
    return max(0.0, min(100.0, (current_iv - iv_low) / (iv_high - iv_low) * 100))


def _iv_percentile(current_iv: float, history: list[float] | pd.Series) -> float:
    """IV Percentile (percentage of historical values below current)."""
    values = pd.Series(history, dtype="float64").dropna()
    if values.empty:
        return 50.0
    return float((values <= current_iv).mean() * 100)


def _realized_volatility(returns: pd.Series, annualization: int = 252) -> float:
    """Realized volatility from returns series."""
    clean = returns.dropna()
    if clean.empty:
        return 0.0
    return float(clean.std() * math.sqrt(annualization) * 100)


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture
def ohlcv() -> pd.DataFrame:
    n = 50
    closes = [100 + i * 0.5 for i in range(n)]
    return pd.DataFrame({
        "open": [c - 0.5 for c in closes],
        "high": [c + 2 for c in closes],
        "low": [c - 2 for c in closes],
        "close": closes,
        "volume": [1000 + (i % 5) * 100 for i in range(n)],
    })


@pytest.fixture
def prices() -> pd.Series:
    return pd.Series([100 + i * 0.5 + (-1) ** i * 0.2 for i in range(50)])


# ── SMA ────────────────────────────────────────────────────────────────────


def test_sma(prices: pd.Series) -> None:
    df = pd.DataFrame({"close": prices})
    result = SMA(period=10).compute(df)
    assert len(result) == len(prices)
    assert result["sma"].iloc[0] == prices.iloc[0]
    assert result["sma"].iloc[-1] == pytest.approx(prices.tail(10).mean(), rel=1e-10)


def test_sma_custom_source(ohlcv: pd.DataFrame) -> None:
    """SMA can be configured to use a different source column."""
    result = SMA(name="sma_high", source="high", period=5).compute(ohlcv)
    assert "sma_high" in result.columns


# ── EMA ────────────────────────────────────────────────────────────────────


def test_ema(prices: pd.Series) -> None:
    df = pd.DataFrame({"close": prices})
    result = EMA(period=10).compute(df)
    assert len(result) == len(prices)
    assert result["ema"].iloc[0] == prices.iloc[0]
    assert result["ema"].iloc[-1] > 0


# ── MACD ───────────────────────────────────────────────────────────────────


def test_macd(prices: pd.Series) -> None:
    df = pd.DataFrame({"close": prices})
    result = MACD().compute(df)
    assert "macd_line" in result.columns
    assert "macd_signal" in result.columns
    assert "macd_histogram" in result.columns
    assert len(result) == len(prices)
    assert result["macd_histogram"].iloc[-1] == pytest.approx(
        result["macd_line"].iloc[-1] - result["macd_signal"].iloc[-1], rel=1e-10
    )


# ── Bollinger Bands ────────────────────────────────────────────────────────


def test_bollinger_bands(prices: pd.Series) -> None:
    df = pd.DataFrame({"close": prices})
    result = BollingerBands(period=20).compute(df)
    assert "bb_upper" in result.columns
    assert "bb_lower" in result.columns
    assert "bb_pct_b" in result.columns
    assert "bb_bandwidth" in result.columns
    assert result["bb_upper"].iloc[-1] >= result["bb_middle"].iloc[-1] >= result["bb_lower"].iloc[-1]


# ── VWAP ───────────────────────────────────────────────────────────────────


def test_vwap(ohlcv: pd.DataFrame) -> None:
    result = VWAP().compute(ohlcv)
    assert len(result) == len(ohlcv)
    assert result["vwap"].iloc[0] > 0
    assert result["vwap"].is_monotonic_increasing


# ── RSI ────────────────────────────────────────────────────────────────────


def test_rsi(ohlcv: pd.DataFrame) -> None:
    result = RSI(period=14).compute(ohlcv)
    assert len(result) == len(ohlcv)
    valid = result["rsi"].dropna()
    assert (valid >= 0).all() and (valid <= 100).all()


# ── ROC ────────────────────────────────────────────────────────────────────


def test_roc(prices: pd.Series) -> None:
    df = pd.DataFrame({"close": prices})
    result = ROC(period=5).compute(df)
    assert len(result) == len(prices)
    assert result["roc"].iloc[0] == 0.0


# ── Momentum ───────────────────────────────────────────────────────────────


def test_momentum(prices: pd.Series) -> None:
    df = pd.DataFrame({"close": prices})
    result = Momentum(period=5).compute(df)
    assert len(result) == len(prices)
    assert result["momentum"].iloc[0] == 0.0


# ── Acceleration (inlined helper) ──────────────────────────────────────────


def test_acceleration(prices: pd.Series) -> None:
    result = _acceleration(prices)
    assert len(result) == len(prices)
    # No nancheck — first row should be 0.0 after fillna(0)
    assert result.iloc[0] == 0.0


# ── ATR ────────────────────────────────────────────────────────────────────


def test_atr(ohlcv: pd.DataFrame) -> None:
    result = ATR(period=14).compute(ohlcv)
    assert len(result) == len(ohlcv)
    assert result["atr"].dropna().iloc[-1] > 0


# ── Historical Volatility ──────────────────────────────────────────────────


def test_historical_volatility(prices: pd.Series) -> None:
    df = pd.DataFrame({"close": prices})
    result = HistoricalVolatility(period=20).compute(df)
    assert len(result) == len(prices)
    valid = result["hist_volatility"].dropna()
    assert (valid >= 0).all()


# ── Realized Volatility (inlined helper) ───────────────────────────────────


def test_realized_volatility(prices: pd.Series) -> None:
    returns = prices.pct_change().dropna()
    result = _realized_volatility(returns)
    assert result >= 0


# ── IV Rank (inlined helper) ───────────────────────────────────────────────


def test_iv_rank() -> None:
    assert _iv_rank(50, 30, 70) == 50.0
    assert _iv_rank(30, 30, 70) == 0.0
    assert _iv_rank(70, 30, 70) == 100.0
    assert _iv_rank(50, 50, 50) == 50.0


# ── IV Percentile (inlined helper) ─────────────────────────────────────────


def test_iv_percentile() -> None:
    history = [30, 40, 50, 60, 70]
    assert _iv_percentile(50, history) == 60.0
    assert _iv_percentile(30, history) == 20.0
    assert _iv_percentile(100, history) == 100.0


# ── FeaturePipeline integration ────────────────────────────────────────────


def test_feature_pipeline_composition(ohlcv: pd.DataFrame) -> None:
    """Multiple features can be composed in a pipeline."""
    from analytics.pipeline.pipeline import FeaturePipeline

    pipeline = (
        FeaturePipeline()
        .add(RSI(period=14))
        .add(ATR(period=14))
        .add(ROC(period=5))
        .add(Momentum(period=1))
    )
    result = pipeline.run(ohlcv)
    assert "rsi" in result.columns
    assert "atr" in result.columns
    assert "roc" in result.columns
    assert "momentum" in result.columns
    assert len(result) == len(ohlcv)
