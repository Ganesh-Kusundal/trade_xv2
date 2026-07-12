"""Composable feature classes for the FeaturePipeline.

Each feature follows the contract:
    compute(df: pd.DataFrame) -> pd.DataFrame

Features read from OHLCV columns and append new columns.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol

import pandas as pd


class Feature(Protocol):
    """Protocol for all pipeline features."""

    name: str

    def compute(self, df: pd.DataFrame) -> pd.DataFrame: ...


def _ensure_columns(df: pd.DataFrame, columns: list[str]) -> None:
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")


# ---------------------------------------------------------------------------
# Price-based features
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ATR:
    """Average True Range.

    NOTE: This implementation uses SMA (simple moving average) for
    smoothing, not Wilder's exponential moving average. This differs
    from the standard ATR used in TradingView, AmiBroker, and most
    technical analysis literature. The HalfTrend indicator in
    analytics/indicators/halftrend.py uses Wilder's smoothing.

    For Wilder's ATR, use the HalfTrend indicator's ATR calculation.
    """

    name: str = "atr"
    period: int = 14

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        _ensure_columns(df, ["high", "low", "close"])
        prev_close = df["close"].shift(1)
        tr = pd.concat(
            [
                df["high"] - df["low"],
                (df["high"] - prev_close).abs(),
                (df["low"] - prev_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        df[self.name] = tr.rolling(window=self.period, min_periods=self.period).mean()
        return df


@dataclass(frozen=True)
class VWAP:
    """Volume Weighted Average Price (cumulative intraday)."""

    name: str = "vwap"

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        _ensure_columns(df, ["high", "low", "close", "volume"])
        typical = (df["high"] + df["low"] + df["close"]) / 3
        cum_tp_vol = (typical * df["volume"]).cumsum()
        cum_vol = df["volume"].cumsum().replace(0, math.inf)
        df[self.name] = cum_tp_vol / cum_vol
        return df


@dataclass(frozen=True)
class RSI:
    """Relative Strength Index.

    NOTE: This implementation uses SMA (simple moving average) for
    smoothing gains/losses, not Wilder's exponential moving average.
    This differs from the standard RSI used in TradingView, AmiBroker,
    and most technical analysis literature.

    Wilder's RSI uses exponential smoothing: avg_gain = (prev_avg * (period-1) + current_gain) / period.
    This SMA version uses: avg_gain = mean(gains over period).

    The SMA version produces smoother, less responsive RSI values.
    Strategies migrating from other platforms should be aware of this
    deviation.
    """

    name: str = "rsi"
    period: int = 14

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        _ensure_columns(df, ["close"])
        from domain.indicators.rsi import RSI as WilderRSI  # noqa: N811

        df[self.name] = WilderRSI(period=self.period).calculate_frame(df)
        return df


@dataclass(frozen=True)
class SMA:
    """Simple Moving Average."""

    name: str = "sma"
    source: str = "close"
    period: int = 20

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        _ensure_columns(df, [self.source])
        df[self.name] = df[self.source].rolling(window=self.period, min_periods=1).mean()
        return df


@dataclass(frozen=True)
class EMA:
    """Exponential Moving Average."""

    name: str = "ema"
    source: str = "close"
    period: int = 20

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        _ensure_columns(df, [self.source])
        df[self.name] = df[self.source].ewm(span=self.period, adjust=False).mean()
        return df


@dataclass(frozen=True)
class BollingerBands:
    """Bollinger Bands (upper, middle, lower, pct_b, bandwidth)."""

    prefix: str = "bb"
    period: int = 20
    num_std: float = 2.0

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        _ensure_columns(df, ["close"])
        middle = df["close"].rolling(window=self.period, min_periods=1).mean()
        std = df["close"].rolling(window=self.period, min_periods=1).std()
        upper = middle + self.num_std * std
        lower = middle - self.num_std * std
        pct_b = (df["close"] - lower) / (upper - lower).replace(0, math.inf)
        bandwidth = (upper - lower) / middle.replace(0, math.inf)
        df[f"{self.prefix}_upper"] = upper
        df[f"{self.prefix}_middle"] = middle
        df[f"{self.prefix}_lower"] = lower
        df[f"{self.prefix}_pct_b"] = pct_b
        df[f"{self.prefix}_bandwidth"] = bandwidth
        return df


@dataclass(frozen=True)
class MACD:
    """MACD (line, signal, histogram)."""

    prefix: str = "macd"
    fast: int = 12
    slow: int = 26
    signal: int = 9

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        _ensure_columns(df, ["close"])
        ema_fast = df["close"].ewm(span=self.fast, adjust=False).mean()
        ema_slow = df["close"].ewm(span=self.slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=self.signal, adjust=False).mean()
        histogram = macd_line - signal_line
        df[f"{self.prefix}_line"] = macd_line
        df[f"{self.prefix}_signal"] = signal_line
        df[f"{self.prefix}_histogram"] = histogram
        return df


# ---------------------------------------------------------------------------
# Volume features
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RelativeVolume:
    """Relative volume (current / average)."""

    name: str = "relative_volume"
    period: int = 20

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        _ensure_columns(df, ["volume"])
        avg_vol = df["volume"].rolling(window=self.period, min_periods=1).mean()
        df[self.name] = df["volume"] / avg_vol.replace(0, math.inf)
        return df


@dataclass(frozen=True)
class VolumeSMA:
    """Volume simple moving average."""

    name: str = "volume_sma"
    period: int = 20

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        _ensure_columns(df, ["volume"])
        df[self.name] = df["volume"].rolling(window=self.period, min_periods=1).mean()
        return df


# ---------------------------------------------------------------------------
# Momentum features
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ROC:
    """Rate of Change."""

    name: str = "roc"
    period: int = 1

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        _ensure_columns(df, ["close"])
        df[self.name] = df["close"].pct_change(periods=self.period).fillna(0) * 100
        return df


@dataclass(frozen=True)
class Momentum:
    """Price momentum (diff)."""

    name: str = "momentum"
    period: int = 1

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        _ensure_columns(df, ["close"])
        df[self.name] = df["close"].diff(periods=self.period).fillna(0)
        return df


# ---------------------------------------------------------------------------
# Market structure features
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SwingHighLow:
    """Confirmed swing high/low without centered-window look-ahead.

    Boolean ``swing_high`` / ``swing_low`` mark confirmed pivots. Price
    levels ``last_swing_high`` / ``last_swing_low`` are forward-filled for
    breakout comparisons at bar close.
    """

    swing_high: str = "swing_high"
    swing_low: str = "swing_low"
    last_swing_high: str = "last_swing_high"
    last_swing_low: str = "last_swing_low"
    lookback: int = 5

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        _ensure_columns(df, ["high", "low", "close"])
        from domain.indicators.market_structure import MarketStructureAnalyzer

        left = max(1, self.lookback // 2)
        right = max(1, self.lookback - left)
        swings = MarketStructureAnalyzer(swing_left=left, swing_right=right).analyze(df)
        df[self.swing_high] = swings["swing_high"]
        df[self.swing_low] = swings["swing_low"]
        df[self.last_swing_high] = (
            df["high"].where(df[self.swing_high]).ffill().fillna(df["high"].expanding().max())
        )
        df[self.last_swing_low] = (
            df["low"].where(df[self.swing_low]).ffill().fillna(df["low"].expanding().min())
        )
        return df


@dataclass(frozen=True)
class CandlestickPattern:
    """Candlestick + swing pattern detection as pipeline columns.

    Appends boolean pattern columns (``cdl_doji``, ``cdl_hammer``,
    ``cdl_shooting_star``, ``cdl_engulfing_bull/bear``, ``cdl_harami_bull/bear``)
    plus ``swing_continuation`` / ``swing_breakdown`` and the enum summary
    ``cdl_direction`` (BULL / BEAR / NEUTRAL). Mirrors ``SwingHighLow``: pure
    domain detection wrapped behind a feature so patterns become columns in any
    ``FeaturePipeline``.
    """

    name: str = "candlestick_pattern"
    doji_body_ratio: float = 0.1
    hammer_lower_wick_mult: float = 2.0
    hammer_upper_wick_mult: float = 0.3
    hammer_max_body_ratio: float = 0.4
    swing_left: int = 2
    swing_right: int = 2

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        _ensure_columns(df, ["open", "high", "low", "close"])
        from domain.indicators.patterns import CandlestickPatterns

        detector = CandlestickPatterns(
            doji_body_ratio=self.doji_body_ratio,
            hammer_lower_wick_mult=self.hammer_lower_wick_mult,
            hammer_upper_wick_mult=self.hammer_upper_wick_mult,
            hammer_max_body_ratio=self.hammer_max_body_ratio,
            swing_left=self.swing_left,
            swing_right=self.swing_right,
        )
        return detector.compute(df)


@dataclass(frozen=True)
class PriceDistance:
    """Distance from key levels."""

    name: str = "price_distance"
    source: str = "sma"
    period: int = 20

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        _ensure_columns(df, ["close", self.source])
        ref = df[self.source]
        df[self.name] = ((df["close"] - ref) / ref.replace(0, math.inf)) * 100
        return df


# ---------------------------------------------------------------------------
# Gap features
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Gap:
    """Gap from previous close."""

    name: str = "gap_pct"

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        _ensure_columns(df, ["open", "close"])
        prev_close = df["close"].shift(1)
        df[self.name] = ((df["open"] - prev_close) / prev_close.replace(0, math.inf)) * 100
        return df


# ---------------------------------------------------------------------------
# Trend features
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Trend:
    """Trend classification based on SMA crossover."""

    name: str = "trend"
    fast_period: int = 10
    slow_period: int = 50

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        _ensure_columns(df, ["close"])
        fast = df["close"].rolling(window=self.fast_period, min_periods=1).mean()
        slow = df["close"].rolling(window=self.slow_period, min_periods=1).mean()
        df[self.name] = "neutral"
        df.loc[fast > slow, self.name] = "up"
        df.loc[fast < slow, self.name] = "down"
        return df


# ---------------------------------------------------------------------------
# Volatility features
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HistoricalVolatility:
    """Historical volatility."""

    name: str = "hist_volatility"
    period: int = 20
    annualization: int = 252

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        _ensure_columns(df, ["close"])
        returns = df["close"].apply(math.log).diff()
        df[self.name] = (
            returns.rolling(window=self.period, min_periods=self.period).std()
            * math.sqrt(self.annualization)
            * 100
        )
        return df


@dataclass(frozen=True)
class ATRPercent:
    """ATR as percentage of price."""

    name: str = "atr_pct"
    atr_name: str = "atr"
    period: int = 14

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        _ensure_columns(df, ["close"])
        if self.atr_name not in df.columns:
            atr_series = ATR(name=self.atr_name, period=self.period).compute(df)[self.atr_name]
        else:
            atr_series = df[self.atr_name]
        df[self.name] = (atr_series / df["close"].replace(0, math.inf)) * 100
        return df


# ---------------------------------------------------------------------------
# Statistical features (z-score, correlation)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ZScore:
    """Z-score normalization of price (how many std devs from mean)."""

    name: str = "z_score"
    source: str = "close"
    period: int = 20

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        _ensure_columns(df, [self.source])
        mean = df[self.source].rolling(window=self.period, min_periods=1).mean()
        std = df[self.source].rolling(window=self.period, min_periods=1).std()
        df[self.name] = ((df[self.source] - mean) / std.replace(0, math.inf)).fillna(0)
        return df


@dataclass(frozen=True)
class Correlation:
    """Rolling correlation between two series."""

    name: str = "correlation"
    source1: str = "close"
    source2: str = "volume"
    period: int = 20

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        _ensure_columns(df, [self.source1, self.source2])
        df[self.name] = (
            df[self.source1]
            .rolling(window=self.period, min_periods=self.period)
            .corr(df[self.source2])
        )
        return df


# ---------------------------------------------------------------------------
# Multi-asset features (cross-sectional)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Beta:
    """Beta coefficient vs benchmark (rolling regression slope)."""

    name: str = "beta"
    asset_col: str = "close"
    bench_col: str = "benchmark"
    period: int = 60

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        _ensure_columns(df, [self.asset_col, self.bench_col])

        # Vectorized calculation using rolling operations
        asset_ret = df[self.asset_col].pct_change()
        bench_ret = df[self.bench_col].pct_change()

        # Rolling covariance and variance
        cov = asset_ret.rolling(window=self.period, min_periods=self.period).cov(bench_ret)
        var = bench_ret.rolling(window=self.period, min_periods=self.period).var()

        df[self.name] = (cov / var.replace(0, float("nan"))).fillna(0)
        return df


# ---------------------------------------------------------------------------
# Cross-sectional features
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PercentRank:
    """Percent rank over rolling window (cross-sectional ranking)."""

    name: str = "pct_rank"
    source: str = "close"
    period: int = 252  # ~1 year of trading days

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        _ensure_columns(df, [self.source])
        df[self.name] = (
            df[self.source]
            .rolling(window=self.period, min_periods=1)
            .apply(
                lambda x: (pd.Series(x).rank(pct=True).iloc[-1] * 100) if len(x) > 1 else 50.0,
                raw=False,
            )
        )
        return df
