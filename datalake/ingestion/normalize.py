"""Shared normalization utilities for converting broker data to canonical schema."""

from __future__ import annotations

import logging

import pandas as pd

from datalake.core.schema import CANONICAL_COLUMNS
from datalake.core.symbols import normalize_symbol

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
    """Ensure timestamp column is datetime64."""
    if "timestamp" in df.columns and not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    return df


def convert_paise_to_rupees(df: pd.DataFrame) -> pd.DataFrame:
    """Convert price columns from paise to rupees if values are too large."""
    for col in ["open", "high", "low", "close"]:
        if col in df.columns and df[col].max() > PAISE_THRESHOLD:
            df[col] = df[col] / 100.0
    return df


def ensure_canonical_columns(df: pd.DataFrame, symbol: str, exchange: str) -> pd.DataFrame:
    """Ensure all canonical columns exist with correct types."""
    df["symbol"] = normalize_symbol(symbol)
    df["exchange"] = exchange

    if "oi" not in df.columns:
        df["oi"] = 0

    for col in CANONICAL_COLUMNS:
        if col not in df.columns:
            df[col] = 0 if col in ("volume", "oi") else ""

    return df


def add_temporal_metadata(df: pd.DataFrame) -> pd.DataFrame:
    """Add published_at, ingested_at, is_correction columns."""
    now_ist = pd.Timestamp.now(tz="Asia/Kolkata").tz_localize(None)
    df["event_time"] = df["timestamp"]
    df["published_at"] = now_ist
    df["ingested_at"] = now_ist
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

    df = df[*CANONICAL_COLUMNS, "event_time", "published_at", "ingested_at", "is_correction"]
    df = df.dropna(subset=["timestamp"])

    return df
