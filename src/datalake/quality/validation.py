"""Data validation for candle ingestion.

Validates:
- OHLCV consistency (high >= low, open/close within [low, high])
- Price range (positive values)
- Volume (non-negative)
- Timestamp (not null, not in future)
- No duplicate timestamps (caller handles dedup)
- Temporal causality (published_at >= event_time)

Can either drop invalid rows or raise on first error.

Audit trail:
    Dropped rows are returned via the ``ValidationAudit`` dataclass
    when ``return_audit=True``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from datalake.core.constants import MAX_PRICE

logger = logging.getLogger(__name__)


@dataclass
class ValidationAudit:
    """Audit trail for dropped/flagged rows during validation."""
    total_rows: int = 0
    valid_rows: int = 0
    dropped_rows: int = 0
    issues: list[str] = field(default_factory=list)
    dropped_indices: list[int] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return self.dropped_rows == 0


_INTRADAY_TIMEFRAMES = ("1m", "5m", "15m", "30m")


def validate_candles(
    df: pd.DataFrame,
    symbol: str = "",
    drop_invalid: bool = True,
    return_audit: bool = False,
    timeframe: str = "",
) -> pd.DataFrame | tuple[pd.DataFrame, ValidationAudit]:
    """Validate candle data and optionally drop invalid rows.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with canonical columns.
    symbol : str
        Symbol name for logging.
    drop_invalid : bool
        If True, drop invalid rows. If False, raise on first invalid row.
    return_audit : bool
        If True, return (df, ValidationAudit) tuple instead of just df.
    timeframe : str
        When one of ``_INTRADAY_TIMEFRAMES``, rows whose time-of-day falls
        outside the NSE session (09:15-15:30 IST) are flagged/dropped. This
        is the backstop for timestamp-timezone bugs upstream (broker/
        composer normalization) landing candles at the wrong wall-clock
        hour -- e.g. UTC-vs-IST mislabeling shows up as an entire day's
        bars sitting 5.5h outside the session window.

    Returns
    -------
    pd.DataFrame with invalid rows removed (if drop_invalid=True).
    If return_audit=True, returns (df, ValidationAudit).
    """
    audit = ValidationAudit(total_rows=len(df))

    if df.empty:
        if return_audit:
            return df, audit
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
        from datalake.exchange_registry import get_active_adapter

        tz_name = get_active_adapter().timezone
        now = pd.Timestamp.now(tz=tz_name).tz_localize(None)
        future = df["timestamp"] > now
        if future.any():
            n = future.sum()
            issues.append(f"{n} future timestamps")
            if drop_invalid:
                df = df[~future].copy()

    # Check session hours (intraday timeframes only)
    if timeframe in _INTRADAY_TIMEFRAMES and pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
        from datalake.exchange_registry import _get_calendar

        session_open, session_close = _get_calendar().session_bounds(None)
        t = df["timestamp"].dt.time
        outside_session = (t < session_open) | (t > session_close)
        if outside_session.any():
            n = outside_session.sum()
            issues.append(
                f"{n} candles outside NSE session {session_open}-{session_close} "
                "(likely a timezone mislabel upstream)"
            )
            if drop_invalid:
                df = df[~outside_session].copy()

    # Check ingested_at not null (if column exists)
    if "ingested_at" in df.columns:
        null_ingested = df["ingested_at"].isna()
        if null_ingested.any():
            n = null_ingested.sum()
            issues.append(f"{n} null ingested_at")
            if drop_invalid:
                df = df[~null_ingested].copy()

    # Check published_at not null (if column exists)
    if "published_at" in df.columns:
        null_published = df["published_at"].isna()
        if null_published.any():
            n = null_published.sum()
            issues.append(f"{n} null published_at")
            if drop_invalid:
                df = df[~null_published].copy()

    # Check event_time equals timestamp (if both columns exist)
    if "event_time" in df.columns and "timestamp" in df.columns:
        mismatched = df["event_time"] != df["timestamp"]
        if mismatched.any():
            n = mismatched.sum()
            issues.append(f"{n} event_time != timestamp")
            if drop_invalid:
                df = df[~mismatched].copy()

    # Check is_correction is boolean (if column exists)
    if "is_correction" in df.columns:
        is_bool = df["is_correction"].isin([True, False, None])
        if not is_bool.all():
            n = (~is_bool).sum()
            issues.append(f"{n} is_correction not boolean")
            if drop_invalid:
                df = df[is_bool].copy()

    # Check temporal causality: published_at >= event_time
    if "published_at" in df.columns and "event_time" in df.columns and pd.api.types.is_datetime64_any_dtype(df.get("published_at")) and pd.api.types.is_datetime64_any_dtype(df.get("event_time")):
            causality_violation = df["published_at"] < df["event_time"]
            if causality_violation.any():
                n = int(causality_violation.sum())
                issues.append(f"{n} published_at < event_time (causality violation)")
                if drop_invalid:
                    df = df[~causality_violation].copy()

    audit.issues = issues
    audit.valid_rows = len(df)
    audit.dropped_rows = before - len(df)

    if issues and symbol:
        logger.warning(
            "%s: dropped %d/%d invalid rows (%s)",
            symbol,
            before - len(df),
            before,
            "; ".join(issues),
        )

    if return_audit:
        return df, audit
    return df


def validate_parquet_file(path: str | Path, symbol: str = "") -> dict:
    """Validate a Parquet file and return a report."""
    from datalake.quality.contract import validate_parquet_file as _validate

    return _validate(path, symbol=symbol)
