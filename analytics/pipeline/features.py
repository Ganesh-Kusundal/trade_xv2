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
    """Average True Range."""

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
        df = df.copy()
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
        df = df.copy()
        df[self.name] = cum_tp_vol / cum_vol
        return df


@dataclass(frozen=True)
class RSI:
    """Relative Strength Index."""

    name: str = "rsi"
    period: int = 14

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        _ensure_columns(df, ["close"])
        delta = df["close"].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.rolling(window=self.period, min_periods=self.period).mean()
        avg_loss = loss.rolling(window=self.period, min_periods=self.period).mean()
        rs = avg_gain / avg_loss.replace(0, math.inf)
        df = df.copy()
        df[self.name] = 100 - (100 / (1 + rs))
        return df


@dataclass(frozen=True)
class SMA:
    """Simple Moving Average."""

    name: str = "sma"
    source: str = "close"
    period: int = 20

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        _ensure_columns(df, [self.source])
        df = df.copy()
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
        df = df.copy()
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
        df = df.copy()
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
        df = df.copy()
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
        df = df.copy()
        df[self.name] = df["volume"] / avg_vol.replace(0, math.inf)
        return df


@dataclass(frozen=True)
class VolumeSMA:
    """Volume simple moving average."""

    name: str = "volume_sma"
    period: int = 20

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        _ensure_columns(df, ["volume"])
        df = df.copy()
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
        df = df.copy()
        df[self.name] = df["close"].pct_change(periods=self.period).fillna(0) * 100
        return df


@dataclass(frozen=True)
class Momentum:
    """Price momentum (diff)."""

    name: str = "momentum"
    period: int = 1

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        _ensure_columns(df, ["close"])
        df = df.copy()
        df[self.name] = df["close"].diff(periods=self.period).fillna(0)
        return df


# ---------------------------------------------------------------------------
# Market structure features
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SwingHighLow:
    """Swing high/low detection."""

    swing_high: str = "swing_high"
    swing_low: str = "swing_low"
    lookback: int = 5

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        _ensure_columns(df, ["high", "low"])
        df = df.copy()
        rolled_high = df["high"].rolling(window=self.lookback, center=True).max()
        rolled_low = df["low"].rolling(window=self.lookback, center=True).min()
        df[self.swing_high] = df["high"] == rolled_high
        df[self.swing_low] = df["low"] == rolled_low
        return df


@dataclass(frozen=True)
class PriceDistance:
    """Distance from key levels."""

    name: str = "price_distance"
    source: str = "sma"
    period: int = 20

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        _ensure_columns(df, ["close", self.source])
        ref = df[self.source]
        df = df.copy()
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
        df = df.copy()
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
        df = df.copy()
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
        df = df.copy()
        df[self.name] = returns.rolling(window=self.period, min_periods=self.period).std() * math.sqrt(self.annualization) * 100
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
        df = df.copy()
        df[self.name] = (atr_series / df["close"].replace(0, math.inf)) * 100
        return df
