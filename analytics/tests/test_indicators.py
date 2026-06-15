"""Tests for technical indicators."""

from __future__ import annotations

import pandas as pd
import pytest

from analytics.indicators.technical import (
    acceleration,
    atr,
    bollinger_bands,
    ema,
    historical_volatility,
    iv_percentile,
    iv_rank,
    macd,
    momentum,
    normalize_score,
    realized_volatility,
    roc,
    rsi,
    sma,
    vwap,
)


@pytest.fixture
def prices() -> pd.Series:
    return pd.Series([100 + i * 0.5 + (-1) ** i * 0.2 for i in range(50)])


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


def test_sma(prices: pd.Series) -> None:
    result = sma(prices, period=10)
    assert len(result) == len(prices)
    assert result.iloc[0] == prices.iloc[0]
    assert result.iloc[-1] == pytest.approx(prices.tail(10).mean(), rel=1e-10)


def test_ema(prices: pd.Series) -> None:
    result = ema(prices, period=10)
    assert len(result) == len(prices)
    assert result.iloc[0] == prices.iloc[0]
    assert result.iloc[-1] > 0


def test_macd(prices: pd.Series) -> None:
    result = macd(prices)
    assert "macd" in result.columns
    assert "signal" in result.columns
    assert "histogram" in result.columns
    assert len(result) == len(prices)
    assert result["histogram"].iloc[-1] == pytest.approx(
        result["macd"].iloc[-1] - result["signal"].iloc[-1], rel=1e-10
    )


def test_bollinger_bands(prices: pd.Series) -> None:
    result = bollinger_bands(prices, period=20)
    assert "upper" in result.columns
    assert "lower" in result.columns
    assert "pct_b" in result.columns
    assert "bandwidth" in result.columns
    assert result["upper"].iloc[-1] >= result["middle"].iloc[-1] >= result["lower"].iloc[-1]


def test_vwap(ohlcv: pd.DataFrame) -> None:
    result = vwap(ohlcv["high"], ohlcv["low"], ohlcv["close"], ohlcv["volume"])
    assert len(result) == len(ohlcv)
    assert result.iloc[0] > 0
    assert result.is_monotonic_increasing


def test_rsi(prices: pd.Series) -> None:
    result = rsi(prices, period=14)
    assert len(result) == len(prices)
    valid = result.dropna()
    assert (valid >= 0).all() and (valid <= 100).all()


def test_roc(prices: pd.Series) -> None:
    result = roc(prices, periods=5)
    assert len(result) == len(prices)
    assert result.iloc[0] == 0.0


def test_momentum(prices: pd.Series) -> None:
    result = momentum(prices, periods=5)
    assert len(result) == len(prices)
    assert result.iloc[0] == 0.0


def test_acceleration(prices: pd.Series) -> None:
    result = acceleration(prices)
    assert len(result) == len(prices)


def test_atr(ohlcv: pd.DataFrame) -> None:
    result = atr(ohlcv["high"], ohlcv["low"], ohlcv["close"], period=14)
    assert len(result) == len(ohlcv)
    assert result.dropna().iloc[-1] > 0


def test_historical_volatility(prices: pd.Series) -> None:
    result = historical_volatility(prices, periods=20)
    assert len(result) == len(prices)
    valid = result.dropna()
    assert (valid >= 0).all()


def test_realized_volatility(prices: pd.Series) -> None:
    returns = prices.pct_change().dropna()
    result = realized_volatility(returns)
    assert result >= 0


def test_iv_rank() -> None:
    assert iv_rank(50, 30, 70) == 50.0
    assert iv_rank(30, 30, 70) == 0.0
    assert iv_rank(70, 30, 70) == 100.0
    assert iv_rank(50, 50, 50) == 50.0


def test_iv_percentile() -> None:
    history = [30, 40, 50, 60, 70]
    assert iv_percentile(50, history) == 60.0
    assert iv_percentile(30, history) == 20.0
    assert iv_percentile(100, history) == 100.0


def test_normalize_score() -> None:
    assert normalize_score(50, 0, 100) == 50.0
    assert normalize_score(0, 0, 100) == 0.0
    assert normalize_score(100, 0, 100) == 100.0
    assert normalize_score(50, 50, 50) == 50.0
