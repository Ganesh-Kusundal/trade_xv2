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
    ATRPercent,
    Beta,
    BollingerBands,
    Correlation,
    Gap,
    HistoricalVolatility,
    Momentum,
    PercentRank,
    PriceDistance,
    RelativeVolume,
    SwingHighLow,
    Trend,
    VolumeSMA,
    ZScore,
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
    return pd.DataFrame(
        {
            "open": [c - 0.5 for c in closes],
            "high": [c + 2 for c in closes],
            "low": [c - 2 for c in closes],
            "close": closes,
            "volume": [1000 + (i % 5) * 100 for i in range(n)],
        }
    )


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
    assert (
        result["bb_upper"].iloc[-1] >= result["bb_middle"].iloc[-1] >= result["bb_lower"].iloc[-1]
    )


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


# ── Volume features ──────────────────────────────────────────────────────────


def test_relative_volume(ohlcv: pd.DataFrame) -> None:
    result = RelativeVolume(period=20).compute(ohlcv)
    assert "relative_volume" in result.columns
    valid = result["relative_volume"].dropna()
    assert (valid >= 0).all()


def test_volume_sma(ohlcv: pd.DataFrame) -> None:
    result = VolumeSMA(period=20).compute(ohlcv)
    assert "volume_sma" in result.columns
    valid = result["volume_sma"].dropna()
    assert (valid >= 0).all()


# ── Market structure features ────────────────────────────────────────────────


def test_swing_high_low(ohlcv: pd.DataFrame) -> None:
    result = SwingHighLow(lookback=5).compute(ohlcv)
    assert "swing_high" in result.columns
    assert "swing_low" in result.columns
    assert result["swing_high"].dtype == bool
    assert result["swing_low"].dtype == bool


def test_price_distance(ohlcv: pd.DataFrame) -> None:
    df = SMA(source="close", period=20, name="sma").compute(ohlcv.copy())
    result = PriceDistance(source="sma", period=20).compute(df)
    assert "price_distance" in result.columns


# ── Gap features ─────────────────────────────────────────────────────────────


def test_gap(ohlcv: pd.DataFrame) -> None:
    result = Gap().compute(ohlcv)
    assert "gap_pct" in result.columns
    first_valid = result["gap_pct"].dropna()
    assert len(first_valid) > 0


# ── Trend features ───────────────────────────────────────────────────────────


def test_trend(ohlcv: pd.DataFrame) -> None:
    result = Trend(fast_period=10, slow_period=50).compute(ohlcv)
    assert "trend" in result.columns
    assert set(result["trend"].unique()).issubset({"up", "down", "neutral"})


# ── Volatility features ──────────────────────────────────────────────────────


def test_atr_percent(ohlcv: pd.DataFrame) -> None:
    df = ATR(period=14).compute(ohlcv.copy())
    result = ATRPercent(atr_name="atr", period=14).compute(df)
    assert "atr_pct" in result.columns
    valid = result["atr_pct"].dropna()
    assert (valid >= 0).all()


# ── Statistical features ─────────────────────────────────────────────────────


def test_z_score(ohlcv: pd.DataFrame) -> None:
    result = ZScore(source="close", period=20).compute(ohlcv)
    assert "z_score" in result.columns


def test_correlation(ohlcv: pd.DataFrame) -> None:
    result = Correlation(source1="close", source2="volume", period=20).compute(ohlcv)
    assert "correlation" in result.columns
    valid = result["correlation"].dropna()
    assert (valid >= -1).all() and (valid <= 1).all()


# ── Multi-asset features ─────────────────────────────────────────────────────


def test_beta(ohlcv: pd.DataFrame) -> None:
    df = ohlcv.copy()
    df["benchmark"] = df["close"] * 1.05
    result = Beta(asset_col="close", bench_col="benchmark", period=20).compute(df)
    assert "beta" in result.columns


# ── Cross-sectional features ─────────────────────────────────────────────────


def test_percent_rank(prices: pd.Series) -> None:
    df = pd.DataFrame({"close": prices})
    result = PercentRank(source="close", period=20).compute(df)
    assert "pct_rank" in result.columns
    valid = result["pct_rank"].dropna()
    assert (valid >= 0).all() and (valid <= 100).all()


# ── Coverage gate ────────────────────────────────────────────────────────────


def test_all_feature_classes_have_tests() -> None:
    """Gate: every Feature class in analytics.pipeline.features must have a test."""
    import inspect

    import analytics.pipeline.features as feat_mod

    feature_classes = {
        name
        for name, obj in inspect.getmembers(feat_mod, inspect.isclass)
        if obj.__module__ == feat_mod.__name__
        and hasattr(obj, "compute")
        and name != "Feature"
    }

    import sys

    test_mod = sys.modules[__name__]
    tested_names: set[str] = set()
    for func_name, _ in inspect.getmembers(test_mod, inspect.isfunction):
        if not func_name.startswith("test_"):
            continue
        norm_func = func_name.lower().replace("_", "")
        for cls_name in feature_classes:
            if cls_name.lower() in norm_func:
                tested_names.add(cls_name)

    untested = feature_classes - tested_names
    assert not untested, f"Feature classes without tests: {untested}"


# ── Edge case tests ─────────────────────────────────────────────────────────


def test_sma_missing_source_column() -> None:
    df = pd.DataFrame({"volume": [1, 2, 3]})
    with pytest.raises(ValueError, match="Missing"):
        SMA(period=2, source="close").compute(df)


def test_rsi_period_exceeds_data() -> None:
    df = pd.DataFrame({"close": [100.0, 101.0, 102.0]})
    result = RSI(period=10).compute(df)
    assert result["rsi"].isna().all()


def test_bollinger_constant_prices() -> None:
    df = pd.DataFrame({"close": [100.0] * 20, "high": [100.0] * 20, "low": [100.0] * 20})
    result = BollingerBands(period=10).compute(df)
    assert len(result) == 20
    assert result["bb_middle"].iloc[-1] == pytest.approx(100.0)


def test_atr_empty_after_warmup() -> None:
    df = pd.DataFrame({
        "open": [100.0],
        "high": [102.0],
        "low": [98.0],
        "close": [101.0],
    })
    result = ATR(period=10).compute(df)
    assert len(result) == 1
    assert result["atr"].isna().iloc[0]


def test_zscore_constant_series() -> None:
    df = pd.DataFrame({"close": [50.0] * 20})
    result = ZScore(period=10, source="close").compute(df)
    assert len(result) == 20
