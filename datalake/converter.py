"""Convert Trade_J Parquet files → canonical schema.

Trade_J uses:
- open_paisa (price in paise, /100 for rupees)
- bar_time_ms (epoch milliseconds)
- interval (always "1m")
- ingested_at_ms (ignored)

Canonical uses:
- open, high, low, close (rupees)
- timestamp (datetime)
- symbol, exchange, volume, oi
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import pyarrow as pa

from datalake.io import atomic_parquet_write

logger = logging.getLogger(__name__)


def convert_tradej_parquet(
    src_path: Path,
    symbol: str,
    exchange: str = "NSE",
) -> pd.DataFrame:
    """Convert a single Trade_J Parquet file to canonical DataFrame.

    Parameters
    ----------
    src_path : Path
        Path to Trade_J Parquet file.
    symbol : str
        Symbol name (Trade_J files don't always have it in data).
    exchange : str
        Exchange code.

    Returns
    -------
    pd.DataFrame with canonical columns.
    """
    df = pd.read_parquet(src_path)

    # Drop 'interval' column early (has dict vs string type issues across files)
    if "interval" in df.columns:
        df = df.drop(columns=["interval"])

    # Rename columns
    df = df.rename(columns={
        "bar_time_ms": "timestamp",
        "open_paisa": "open",
        "high_paisa": "high",
        "low_paisa": "low",
        "close_paisa": "close",
    })

    # Convert timestamp from epoch ms to datetime
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True).dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)

    # Convert paise to rupees (divide by 100)
    for col in ["open", "high", "low", "close"]:
        if col in df.columns:
            df[col] = df[col] / 100.0

    # Add missing columns
    df["symbol"] = symbol
    df["exchange"] = exchange
    if "oi" not in df.columns:
        df["oi"] = 0

    # Drop Trade_J-specific columns (including 'interval' which has dict type issues)
    drop_cols = [c for c in df.columns if c not in [
        "timestamp", "symbol", "exchange", "open", "high", "low", "close", "volume", "oi",
        "vwap", "trade_count",
    ]]
    df = df.drop(columns=drop_cols, errors="ignore")

    # Ensure column order
    canonical = ["timestamp", "symbol", "exchange", "open", "high", "low", "close", "volume", "oi"]
    for col in canonical:
        if col not in df.columns:
            df[col] = 0 if col in ("volume", "oi") else ""
    df = df[canonical]

    return df


def convert_tradej_directory(
    tradej_bars_dir: Path,
    target_dir: Path,
    symbols: list[str] | None = None,
    timeframe: str = "1m",
) -> dict[str, int]:
    """Convert all Trade_J Parquet files to canonical hive-partitioned layout.

    Parameters
    ----------
    tradej_bars_dir : Path
        Path to Trade_J bars directory (e.g., data/historical-equity/bars/interval=1m/).
    target_dir : Path
        Target directory (e.g., market_data/equities/candles/timeframe=1m/).
    symbols : list of str or None
        Specific symbols to convert. None = all.
    timeframe : str
        Target timeframe.

    Returns
    -------
    dict mapping symbol → number of rows written.
    """
    results: dict[str, int] = {}

    symbol_dirs = sorted(tradej_bars_dir.iterdir())
    if symbols:
        symbol_set = {s.upper() for s in symbols}
        symbol_dirs = [d for d in symbol_dirs if d.name.replace("symbol=", "").upper() in symbol_set]

    for sym_dir in symbol_dirs:
        if not sym_dir.is_dir():
            continue

        symbol = sym_dir.name.replace("symbol=", "")
        logger.info("Converting %s...", symbol)

        # Read all monthly partitions for this symbol
        parquet_files = sorted(sym_dir.glob("*.parquet"))
        if not parquet_files:
            continue

        dfs = []
        for pf in parquet_files:
            try:
                df = convert_tradej_parquet(pf, symbol)
                dfs.append(df)
            except Exception as exc:
                logger.warning("Failed to convert %s: %s", pf, exc)

        if not dfs:
            continue

        combined = pd.concat(dfs, ignore_index=True)
        combined = combined.sort_values("timestamp").drop_duplicates(subset=["timestamp"])

        # Write to hive partition atomically
        sym_target = target_dir / f"symbol={symbol}"
        sym_target.mkdir(parents=True, exist_ok=True)

        table = pa.Table.from_pandas(combined, preserve_index=False)
        atomic_parquet_write(sym_target / "data.parquet", table, compression="snappy")

        results[symbol] = len(combined)
        logger.info("  %s: %d rows", symbol, len(combined))

    return results
