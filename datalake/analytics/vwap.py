"""VWAP computation — Volume Weighted Average Price at ingestion and query time.

Computes VWAP during data ingestion (loader/converter) and provides
standalone VWAP calculation for any OHLCV DataFrame.

VWAP = Σ(typical_price × volume) / Σ(volume)
where typical_price = (high + low + close) / 3
"""

from __future__ import annotations

import logging

import pandas as pd

logger = logging.getLogger(__name__)


def compute_vwap(
    df: pd.DataFrame,
    group_col: str | None = None,
    timestamp_col: str = "timestamp",
) -> pd.DataFrame:
    """Compute VWAP for an OHLCV DataFrame.

    Args:
        df: DataFrame with open, high, low, close, volume columns.
        group_col: Optional column to group by (e.g., "symbol").
            If None, computes VWAP for the entire DataFrame as a single group.
        timestamp_col: Name of the timestamp column.

    Returns:
        DataFrame with 'vwap' column added (in-place cumulative VWAP per group).
    """
    if df.empty or not all(c in df.columns for c in ["high", "low", "close", "volume"]):
        return df

    df = df.copy()
    typical_price = (df["high"] + df["low"] + df["close"]) / 3.0
    tp_vol = typical_price * df["volume"]

    if group_col and group_col in df.columns:
        df["_tp_vol"] = tp_vol
        df["_vol_cum"] = df.groupby(group_col)["volume"].cumsum()
        df["_tp_vol_cum"] = df.groupby(group_col)["_tp_vol"].cumsum()
    else:
        df["_tp_vol"] = tp_vol
        df["_vol_cum"] = df["volume"].cumsum()
        df["_tp_vol_cum"] = tp_vol.cumsum()

    df["vwap"] = df["_tp_vol_cum"] / df["_vol_cum"].replace(0, float("nan"))
    df.drop(columns=["_tp_vol", "_vol_cum", "_tp_vol_cum"], inplace=True)

    return df


def compute_daily_vwap(
    df: pd.DataFrame,
    timestamp_col: str = "timestamp",
    group_col: str | None = None,
) -> pd.DataFrame:
    """Compute daily (intraday-resetting) VWAP from intraday data.

    Resets VWAP at each new trading day. Useful for intraday VWAP
    bands and mean-reversion strategies.

    Args:
        df: DataFrame with intraday OHLCV data (1m, 5m, etc.).
        timestamp_col: Name of the timestamp column.
        group_col: Optional group column.

    Returns:
        DataFrame with 'vwap_daily' column.
    """
    if df.empty or not all(c in df.columns for c in ["high", "low", "close", "volume"]):
        return df

    df = df.copy()
    ts = pd.to_datetime(df[timestamp_col])
    df["_date"] = ts.dt.date

    typical_price = (df["high"] + df["low"] + df["close"]) / 3.0
    df["_tp_vol"] = typical_price * df["volume"]

    if group_col and group_col in df.columns:
        df["_day_key"] = df[group_col].astype(str) + "_" + df["_date"].astype(str)
    else:
        df["_day_key"] = df["_date"].astype(str)

    df["vwap_daily"] = (
        df.groupby("_day_key")["_tp_vol"].cumsum()
        / df.groupby("_day_key")["volume"].cumsum().replace(0, float("nan"))
    )

    df.drop(columns=["_date", "_tp_vol", "_day_key"], inplace=True)
    return df


def vwap_from_candles(
    candles: list[dict] | pd.DataFrame,
) -> float:
    """Compute a single VWAP value from a set of candles.

    Args:
        candles: List of dicts or DataFrame with high, low, close, volume.

    Returns:
        VWAP value, or 0.0 if no volume.
    """
    if isinstance(candles, pd.DataFrame):
        if candles.empty or not all(c in candles.columns for c in ["high", "low", "close", "volume"]):
            return 0.0
        typical = (candles["high"] + candles["low"] + candles["close"]) / 3.0
        total_vol = candles["volume"].sum()
        if total_vol == 0:
            return 0.0
        return float((typical * candles["volume"]).sum() / total_vol)

    if not candles:
        return 0.0

    total_tp_vol = 0.0
    total_vol = 0
    for c in candles:
        tp = (c.get("high", 0) + c.get("low", 0) + c.get("close", 0)) / 3.0
        vol = c.get("volume", 0)
        total_tp_vol += tp * vol
        total_vol += vol

    return total_tp_vol / total_vol if total_vol > 0 else 0.0
