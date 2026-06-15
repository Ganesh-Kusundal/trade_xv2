"""Reusable technical indicators used by analytics engines."""

from __future__ import annotations

import math

import pandas as pd


def rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    delta = prices.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, math.inf)
    return 100 - (100 / (1 + rs))


def roc(prices: pd.Series, periods: int = 1) -> pd.Series:
    return prices.pct_change(periods=periods).fillna(0) * 100


def momentum(prices: pd.Series, periods: int = 1) -> pd.Series:
    return prices.diff(periods=periods).fillna(0)


def acceleration(prices: pd.Series, periods: int = 1) -> pd.Series:
    return prices.pct_change(periods=periods).diff().fillna(0)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    previous_close = close.shift(1)
    true_range = pd.concat(
        [
            high - low,
            (high - previous_close).abs(),
            (low - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.rolling(window=period, min_periods=period).mean()


def historical_volatility(
    prices: pd.Series,
    periods: int = 20,
    annualization: int = 252,
) -> pd.Series:
    returns = prices.apply(math.log).diff()
    return returns.rolling(window=periods, min_periods=periods).std() * math.sqrt(annualization) * 100


def realized_volatility(returns: pd.Series, annualization: int = 252) -> float:
    clean = returns.dropna()
    if clean.empty:
        return 0.0
    return float(clean.std() * math.sqrt(annualization) * 100)


def iv_rank(current_iv: float, iv_low: float, iv_high: float) -> float:
    if iv_high <= iv_low:
        return 50.0
    return max(0.0, min(100.0, (current_iv - iv_low) / (iv_high - iv_low) * 100))


def iv_percentile(current_iv: float, history: list[float] | pd.Series) -> float:
    values = pd.Series(history, dtype="float64").dropna()
    if values.empty:
        return 50.0
    return float((values <= current_iv).mean() * 100)


def normalize_score(value: float, low: float, high: float) -> float:
    if high <= low:
        return 50.0
    return max(0.0, min(100.0, (value - low) / (high - low) * 100))


def sma(prices: pd.Series, period: int = 20) -> pd.Series:
    return prices.rolling(window=period, min_periods=1).mean()


def ema(prices: pd.Series, period: int = 20) -> pd.Series:
    return prices.ewm(span=period, adjust=False).mean()


def macd(
    prices: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    ema_fast = ema(prices, fast)
    ema_slow = ema(prices, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line
    return pd.DataFrame({
        "macd": macd_line,
        "signal": signal_line,
        "histogram": histogram,
    })


def bollinger_bands(
    prices: pd.Series,
    period: int = 20,
    num_std: float = 2.0,
) -> pd.DataFrame:
    middle = sma(prices, period)
    std = prices.rolling(window=period, min_periods=1).std()
    upper = middle + num_std * std
    lower = middle - num_std * std
    pct_b = (prices - lower) / (upper - lower).replace(0, math.inf)
    return pd.DataFrame({
        "upper": upper,
        "middle": middle,
        "lower": lower,
        "pct_b": pct_b,
        "bandwidth": (upper - lower) / middle.replace(0, math.inf),
    })


def vwap(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series) -> pd.Series:
    typical_price = (high + low + close) / 3
    cumulative_tp_vol = (typical_price * volume).cumsum()
    cumulative_vol = volume.cumsum().replace(0, math.inf)
    return cumulative_tp_vol / cumulative_vol
