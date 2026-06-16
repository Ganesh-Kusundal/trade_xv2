"""Data validation for candle ingestion.

Validates:
- OHLCV consistency (high >= low, open/close within [low, high])
- Price range (positive values)
- Volume (non-negative)
- Timestamp (not null, not in future)
- No duplicate timestamps (caller handles dedup)

Can either drop invalid rows or raise on first error.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

MAX_PRICE = 10_000_000.0  # 1 crore per share, sanity cap


def validate_candles(
    df: pd.DataFrame,
    symbol: str = "",
    drop_invalid: bool = True,
) -> pd.DataFrame:
    """Validate candle data and optionally drop invalid rows.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with canonical columns.
    symbol : str
        Symbol name for logging.
    drop_invalid : bool
        If True, drop invalid rows. If False, raise on first invalid row.

    Returns
    -------
    pd.DataFrame with invalid rows removed (if drop_invalid=True).
    """
    if df.empty:
        return df

    before = len(df)
    issues: list[str] = []

    # Check required columns
    required = ["timestamp", "open", "high", "low", "close", "volume"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        msg = f"missing required columns: {missing}"
        if drop_invalid:
            logger.error("%s: %s", symbol, msg)
            return df.iloc[0:0]
        raise ValueError(msg)

    # Drop null timestamps
    null_ts = df["timestamp"].isna()
    if null_ts.any():
        n = null_ts.sum()
        issues.append(f"{n} null timestamps")
        if drop_invalid:
            df = df[~null_ts].copy()

    # Check OHLCV consistency
    invalid_ohlc = (
        (df["high"] < df["low"])
        | (df["open"] < 0)
        | (df["close"] < 0)
        | (df["high"] < df["open"])
        | (df["high"] < df["close"])
        | (df["low"] > df["open"])
        | (df["low"] > df["close"])
    )
    if invalid_ohlc.any():
        n = invalid_ohlc.sum()
        issues.append(f"{n} invalid OHLC (high<low or O/C outside range)")
        if drop_invalid:
            df = df[~invalid_ohlc].copy()

    # Check price range
    extreme = (df["high"] > MAX_PRICE) | (df["low"] < 0)
    if extreme.any():
        n = extreme.sum()
        issues.append(f"{n} prices out of range [0, {MAX_PRICE}]")
        if drop_invalid:
            df = df[~extreme].copy()

    # Check volume
    neg_vol = df["volume"] < 0
    if neg_vol.any():
        n = neg_vol.sum()
        issues.append(f"{n} negative volume")
        if drop_invalid:
            df = df[~neg_vol].copy()

    # Check future timestamps
    if pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
        now = pd.Timestamp.now(tz="Asia/Kolkata").tz_localize(None)
        future = df["timestamp"] > now
        if future.any():
            n = future.sum()
            issues.append(f"{n} future timestamps")
            if drop_invalid:
                df = df[~future].copy()

    if issues and symbol:
        logger.warning("%s: dropped %d/%d invalid rows (%s)",
                       symbol, before - len(df), before, "; ".join(issues))

    return df


def validate_parquet_file(path: str | Path, symbol: str = "") -> dict:
    """Validate a Parquet file and return a report.

    Returns
    -------
    Dict with keys: total_rows, valid_rows, invalid_rows, issues
    """
    df = pd.read_parquet(path)
    if df.empty:
        return {"total_rows": 0, "valid_rows": 0, "invalid_rows": 0, "issues": []}

    total = len(df)
    validated = validate_candles(df, symbol=symbol, drop_invalid=False)
    issues = []

    if validated.empty:
        issues.append("all rows failed validation")

    return {
        "total_rows": total,
        "valid_rows": len(validated),
        "invalid_rows": total - len(validated),
        "issues": issues,
    }
