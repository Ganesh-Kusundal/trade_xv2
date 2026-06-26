"""Quantitative feature engineering — momentum, mean-reversion, volatility regime.

Standalone feature computation module for backtesting and research.
All functions are pure (no side effects) and work on pandas DataFrames.

Feature categories:
- Momentum: RSI, MACD, ROC, ADX, CCI, Williams %R, Stochastic
- Mean-reversion: Bollinger Bands, Z-score, RSI extremes
- Volatility: ATR, historical vol, Garman-Klass, Parkinson, Yang-Zhang
- Volume: OBV, VWAP deviation, volume profile
"""

from __future__ import annotations

import numpy as np
import pandas as pd


# ── Momentum indicators ──────────────────────────────────────────────────


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index."""
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, float("nan"))
    return 100.0 - (100.0 / (1.0 + rs))


def macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    """MACD, signal line, and histogram."""
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return pd.DataFrame({
        "macd": macd_line,
        "macd_signal": signal_line,
        "macd_histogram": histogram,
    })


def roc(close: pd.Series, period: int = 10) -> pd.Series:
    """Rate of Change (%)."""
    return close.pct_change(periods=period) * 100.0


def adx(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> pd.DataFrame:
    """Average Directional Index (ADX, +DI, -DI)."""
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    up_move = high - high.shift(1)
    down_move = low.shift(1) - low

    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)

    atr = tr.ewm(alpha=1.0 / period, min_periods=period).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1.0 / period, min_periods=period).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1.0 / period, min_periods=period).mean() / atr

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, float("nan"))
    adx_val = dx.ewm(alpha=1.0 / period, min_periods=period).mean()

    return pd.DataFrame({
        "adx": adx_val,
        "plus_di": plus_di,
        "minus_di": minus_di,
    })


def cci(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 20,
) -> pd.Series:
    """Commodity Channel Index."""
    tp = (high + low + close) / 3.0
    sma_tp = tp.rolling(period).mean()
    mad = tp.rolling(period).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
    return (tp - sma_tp) / (0.015 * mad)


def williams_r(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> pd.Series:
    """Williams %R."""
    highest = high.rolling(period).max()
    lowest = low.rolling(period).min()
    return -100.0 * (highest - close) / (highest - lowest).replace(0, float("nan"))


def stochastic(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    k_period: int = 14,
    d_period: int = 3,
) -> pd.DataFrame:
    """Stochastic Oscillator (%K, %D)."""
    lowest = low.rolling(k_period).min()
    highest = high.rolling(k_period).max()
    k = 100.0 * (close - lowest) / (highest - lowest).replace(0, float("nan"))
    d = k.rolling(d_period).mean()
    return pd.DataFrame({"stoch_k": k, "stoch_d": d})


# ── Mean-reversion indicators ────────────────────────────────────────────


def bollinger_bands(
    close: pd.Series,
    period: int = 20,
    num_std: float = 2.0,
) -> pd.DataFrame:
    """Bollinger Bands (upper, mid, lower, bandwidth, %B)."""
    sma = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = sma + num_std * std
    lower = sma - num_std * std
    bandwidth = (upper - lower) / sma
    pct_b = (close - lower) / (upper - lower)
    return pd.DataFrame({
        "bb_upper": upper,
        "bb_mid": sma,
        "bb_lower": lower,
        "bb_bandwidth": bandwidth,
        "bb_pct_b": pct_b,
    })


def zscore(close: pd.Series, period: int = 20) -> pd.Series:
    """Z-score of close price over rolling window."""
    mean = close.rolling(period).mean()
    std = close.rolling(period).std()
    return (close - mean) / std.replace(0, float("nan"))


def rsi_extremes(close: pd.Series, period: int = 14) -> pd.DataFrame:
    """RSI with oversold/overbought signals."""
    rsi_val = rsi(close, period)
    return pd.DataFrame({
        "rsi": rsi_val,
        "rsi_oversold": (rsi_val < 30).astype(float),
        "rsi_overbought": (rsi_val > 70).astype(float),
    })


# ── Volatility indicators ────────────────────────────────────────────────


def atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> pd.Series:
    """Average True Range."""
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / period, min_periods=period).mean()


def historical_volatility(
    close: pd.Series,
    period: int = 20,
    annualize: bool = True,
) -> pd.Series:
    """Historical volatility (annualized by default)."""
    log_ret = np.log(close / close.shift(1))
    vol = log_ret.rolling(period).std()
    if annualize:
        vol = vol * np.sqrt(252)
    return vol


def garman_klass_vol(
    high: pd.Series,
    low: pd.Series,
    open_: pd.Series,
    close: pd.Series,
    period: int = 20,
) -> pd.Series:
    """Garman-Klass volatility estimator."""
    log_hl = np.log(high / low)
    log_co = np.log(close / open_)
    gk = 0.5 * log_hl**2 - (2 * np.log(2) - 1) * log_co**2
    return gk.rolling(period).mean().apply(lambda x: np.sqrt(max(x, 0)))


def parkinson_vol(
    high: pd.Series,
    low: pd.Series,
    period: int = 20,
) -> pd.Series:
    """Parkinson volatility estimator (high-low based)."""
    log_hl = np.log(high / low)
    return (log_hl**2 / (4 * np.log(2))).rolling(period).mean().apply(
        lambda x: np.sqrt(max(x, 0))
    )


def yang_zhang_vol(
    high: pd.Series,
    low: pd.Series,
    open_: pd.Series,
    close: pd.Series,
    period: int = 20,
) -> pd.Series:
    """Yang-Zhang volatility estimator (most efficient for OHLC)."""
    log_oc = np.log(open_ / close.shift(1))
    log_co = np.log(close / open_)
    log_ho = np.log(high / open_)
    log_lo = np.log(low / open_)

    open_var = log_oc.rolling(period).var()
    close_var = log_co.rolling(period).var()
    rs_var = log_ho * (log_ho - log_co) + log_lo * (log_lo - log_co)
    rs_var = rs_var.rolling(period).mean()

    k = 0.34 / (1.34 + (period + 1) / (period - 1))
    return np.sqrt(open_var + k * close_var + (1 - k) * rs_var)


# ── Volume indicators ────────────────────────────────────────────────────


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """On-Balance Volume."""
    direction = np.sign(close.diff())
    return (direction * volume).cumsum()


def vwap_deviation(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    volume: pd.Series,
    period: int = 20,
) -> pd.Series:
    """Deviation from rolling VWAP (as %)."""
    tp = (high + low + close) / 3.0
    vwap = (tp * volume).rolling(period).sum() / volume.rolling(period).sum()
    return ((close - vwap) / vwap) * 100.0


def volume_profile(
    close: pd.Series,
    volume: pd.Series,
    bins: int = 50,
) -> pd.DataFrame:
    """Volume profile — volume distribution by price level."""
    price_bins = pd.cut(close, bins=bins)
    profile = volume.groupby(price_bins, observed=True).sum()
    return pd.DataFrame({
        "price_range": profile.index.astype(str),
        "volume": profile.values,
    })


# ── Convenience: compute all features ────────────────────────────────────


def compute_all_features(
    df: pd.DataFrame,
    timestamp_col: str = "timestamp",
) -> pd.DataFrame:
    """Compute all quantitative features for an OHLCV DataFrame.

    Returns a copy with all feature columns added.
    """
    if df.empty or not all(c in df.columns for c in ["open", "high", "low", "close", "volume"]):
        return df

    df = df.copy()
    close = df["close"]
    high = df["high"]
    low = df["low"]
    open_ = df["open"]
    volume = df["volume"]

    df["rsi_14"] = rsi(close, 14)
    df["rsi_7"] = rsi(close, 7)

    macd_df = macd(close)
    df = pd.concat([df, macd_df], axis=1)

    df["roc_5"] = roc(close, 5)
    df["roc_10"] = roc(close, 10)
    df["roc_20"] = roc(close, 20)

    adx_df = adx(high, low, close)
    df = pd.concat([df, adx_df], axis=1)

    df["cci_20"] = cci(high, low, close, 20)
    df["williams_r_14"] = williams_r(high, low, close, 14)

    stoch_df = stochastic(high, low, close)
    df = pd.concat([df, stoch_df], axis=1)

    bb_df = bollinger_bands(close)
    df = pd.concat([df, bb_df], axis=1)

    df["zscore_20"] = zscore(close, 20)

    df["atr_14"] = atr(high, low, close, 14)
    df["hvol_20"] = historical_volatility(close, 20)
    df["gk_vol"] = garman_klass_vol(high, low, open_, close)
    df["parkinson_vol"] = parkinson_vol(high, low)
    df["yz_vol"] = yang_zhang_vol(high, low, open_, close)

    df["obv"] = obv(close, volume)
    df["vwap_dev_20"] = vwap_deviation(high, low, close, volume, 20)

    return df
