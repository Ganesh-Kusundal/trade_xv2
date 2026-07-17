"""Shared normalization utilities for converting broker data to canonical schema."""

from __future__ import annotations

import logging

import pandas as pd

from datalake.core.schema import CANONICAL_COLUMNS
from datalake.core.symbols import normalize_symbol_for_storage
from datalake.exchange_registry import get_active_adapter
from domain.constants.market import IST_OFFSET

logger = logging.getLogger(__name__)

# Common column name mappings (broker → canonical)
COLUMN_MAP = {
    "bar_time_ms": "timestamp",
    "open_paisa": "open",
    "high_paisa": "high",
    "low_paisa": "low",
    "close_paisa": "close",
    "Open": "open",
    "High": "high",
    "Low": "low",
    "Close": "close",
    "Volume": "volume",
    "Date": "timestamp",
    "Datetime": "timestamp",
}

# Threshold for auto-detecting paise vs rupees
PAISE_THRESHOLD = 100_000


def rename_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename broker-specific columns to canonical names."""
    return df.rename(columns={k: v for k, v in COLUMN_MAP.items() if k in df.columns})


def ensure_timestamp_dtype(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure timestamp column is naive datetime in IST (Asia/Kolkata).

    All datalake timestamps are IST naive per schema.py. Broker data may
    arrive as UTC-aware, IST-aware, or naive — this normalizes everything.

    - UTC-aware → convert to IST, strip tz
    - IST-aware → strip tz (already correct)
    - Naive → assume already IST, keep as-is
    """
    if "timestamp" not in df.columns:
        return df
    try:
        adapter = get_active_adapter()
        tz = adapter.timezone
    except Exception:
        tz = IST_OFFSET  # Fallback to canonical IST if no adapter configured
    ts = pd.to_datetime(df["timestamp"], errors="coerce")

    if ts.dtype == object:
        # A column of Python datetimes with inconsistent tzinfo objects
        # (e.g. bars federated from brokers that tag UTC vs a fixed
        # +05:30 offset) parses to `object` dtype, not a real
        # datetime64[tz] column -- `.dt.tz` below would silently read as
        # unavailable rather than raising, letting unconverted timestamps
        # straight through. Force a single tz-aware dtype first so the
        # aware/naive branch below is reliable.
        ts = pd.to_datetime(ts, utc=True, errors="coerce")

    if ts.dt.tz is not None:
        # Timezone-aware: convert to exchange tz, then strip tz
        ts = ts.dt.tz_convert(tz).dt.tz_localize(None)
    # else: naive — assume already in exchange tz, keep as-is

    df["timestamp"] = ts
    return df


def convert_paise_to_rupees(
    df: pd.DataFrame, *, source_unit: str = "auto"
) -> pd.DataFrame:
    """Convert price columns from the exchange's native unit to base currency.

    Uses the active exchange adapter's ``price_scale`` (e.g. 100 for NSE paise→INR)
    instead of hardcoded ``/100``.

    Parameters
    ----------
    source_unit : str
        ``"native"`` — always divide by adapter.price_scale.
        ``"base"`` — no conversion; warn if values exceed threshold.
        ``"auto"`` (default) — legacy heuristic: divide if max > threshold.
    """
    price_cols = ["open", "high", "low", "close"]
    existing = [c for c in price_cols if c in df.columns]
    if not existing:
        return df

    adapter = get_active_adapter()
    scale = adapter.price_scale
    # Threshold scales with the adapter's price unit
    threshold = 100_000  # TODO: derive from adapter if needed

    if source_unit == "native":
        for col in existing:
            df[col] = df[col] / scale
    elif source_unit == "base":
        max_val = max(df[c].max() for c in existing)
        if max_val > threshold:
            logger.warning(
                "paise_threshold_warning",
                extra={
                    "max_value": max_val,
                    "threshold": threshold,
                    "detail": "Values exceed threshold but source_unit='base'. "
                    "Verify data is actually in base currency.",
                },
            )
    else:  # auto — legacy heuristic
        for col in existing:
            if df[col].max() > threshold:
                df[col] = df[col] / scale
    return df


def ensure_canonical_columns(df: pd.DataFrame, symbol: str, exchange: str) -> pd.DataFrame:
    """Ensure all canonical columns exist with correct types."""
    df["symbol"] = normalize_symbol_for_storage(symbol)
    df["exchange"] = exchange

    if "oi" not in df.columns:
        df["oi"] = 0

    for col in CANONICAL_COLUMNS:
        if col not in df.columns:
            df[col] = 0 if col in ("volume", "oi") else ""

    return df


def add_temporal_metadata(df: pd.DataFrame) -> pd.DataFrame:
    """Add published_at, ingested_at, is_correction columns."""
    tz = get_active_adapter().timezone
    now_local = pd.Timestamp.now(tz=tz).tz_localize(None)
    df["event_time"] = df["timestamp"]
    df["published_at"] = now_local
    df["ingested_at"] = now_local
    df["is_correction"] = False
    return df


def normalize_to_canonical(
    df: pd.DataFrame,
    symbol: str,
    exchange: str,
    timestamp_col: str = "timestamp",
) -> pd.DataFrame:
    """Full normalization pipeline: broker DataFrame → canonical schema.

    Applies: column rename, timestamp conversion, paise→rupees,
    canonical column enforcement, temporal metadata, validation.
    """
    df = rename_columns(df)
    df = ensure_timestamp_dtype(df)
    df = convert_paise_to_rupees(df)
    df = ensure_canonical_columns(df, symbol, exchange)
    df = add_temporal_metadata(df)

    # Filter to canonical columns and drop rows with null timestamps
    for col in CANONICAL_COLUMNS:
        if col not in df.columns:
            df[col] = 0 if col in ("volume", "oi") else ""

    # CANONICAL_COLUMNS already includes "event_time" -- don't duplicate it
    # here, or df[_cols] selects two "event_time" columns and every
    # downstream df["event_time"] access returns a 2-column DataFrame
    # instead of a Series (breaks any comparison against it).
    _cols = [*list(CANONICAL_COLUMNS), "published_at", "ingested_at", "is_correction"]
    df = df[_cols]
    df = df.dropna(subset=["timestamp"])

    return df
