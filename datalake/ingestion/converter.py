"""Convert Trade_J Parquet files → canonical schema (IST timestamps).

Trade_J source format:
- open_paisa (price in paise, /100 for rupees)
- bar_time_ms (epoch milliseconds — may be UTC OR IST depending on source)
- interval (always "1m", dropped due to dict type issues)
- ingested_at_ms (ignored)

Canonical format (IST):
- open, high, low, close (rupees)
- timestamp (naive datetime in IST)
- symbol, exchange, volume, oi

Timezone handling:
- If bar_time_ms is in UTC (most common): convert to IST, strip timezone
- If bar_time_ms is in IST: treat as IST, just strip timezone
- Detection: check if the hour falls in NSE market hours (9:15-15:30 IST)
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import pyarrow as pa

from datalake.core.io import atomic_parquet_write
from datalake.core.schema import CANONICAL_COLUMNS
from datalake.core.constants import (
    MARKET_CLOSE_HOUR,
    MARKET_CLOSE_MINUTE,
    MARKET_OPEN_HOUR,
    MARKET_OPEN_MINUTE,
)
from datalake.core.symbols import normalize_symbol
from datalake.quality.validation import validate_candles

logger = logging.getLogger(__name__)


def _detect_source_timezone(bar_time_ms: pd.Series) -> str:
    """Detect whether bar_time_ms values are in UTC or IST.

    Heuristic: if the majority of timestamps (interpreted as UTC) fall in
    NSE market hours (9:15-15:30), the source is UTC. If they fall in
    3:45-10:00 UTC (= IST market hours), the source is already IST.
    """
    sample = bar_time_ms.dropna().head(1000)
    if sample.empty:
        return "UTC"  # default assumption

    as_utc = pd.to_datetime(sample, unit="ms", utc=True)
    hours = as_utc.dt.hour
    minutes = as_utc.dt.minute

    ist_market_count = (
        ((hours == MARKET_OPEN_HOUR) & (minutes >= MARKET_OPEN_MINUTE)).sum()
        + ((hours > MARKET_OPEN_HOUR) & (hours < MARKET_CLOSE_HOUR)).sum()
        + ((hours == MARKET_CLOSE_HOUR) & (minutes <= MARKET_CLOSE_MINUTE)).sum()
    )

    return "UTC" if ist_market_count > len(sample) * 0.5 else "IST"


def convert_tradej_parquet(
    src_path: Path,
    symbol: str,
    exchange: str = "NSE",
) -> pd.DataFrame:
    """Convert a single Trade_J Parquet file to canonical DataFrame (IST).

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
    pd.DataFrame with canonical columns (timestamp in IST).
    """
    df = pd.read_parquet(src_path)

    # Drop 'interval' column early (has dict vs string type issues across files)
    if "interval" in df.columns:
        df = df.drop(columns=["interval"])

    # Rename columns
    df = df.rename(
        columns={
            "bar_time_ms": "timestamp",
            "open_paisa": "open",
            "high_paisa": "high",
            "low_paisa": "low",
            "close_paisa": "close",
        }
    )

    # Convert timestamp with timezone detection
    if "timestamp" in df.columns and not df["timestamp"].empty:
        source_tz = _detect_source_timezone(df["timestamp"])
        if source_tz == "UTC":
            df["timestamp"] = (
                pd.to_datetime(df["timestamp"], unit="ms", utc=True)
                .dt.tz_convert("Asia/Kolkata")
                .dt.tz_localize(None)
            )
        else:
            df["timestamp"] = (
                pd.to_datetime(df["timestamp"], unit="ms", utc=True)
                .dt.tz_localize("Asia/Kolkata")
                .dt.tz_localize(None)
            )
        logger.debug("%s: source timezone detected as %s", symbol, source_tz)

    # Convert paise to rupees (divide by 100)
    for col in ["open", "high", "low", "close"]:
        if col in df.columns:
            df[col] = df[col] / 100.0

    # Add missing columns
    df["symbol"] = normalize_symbol(symbol)
    df["exchange"] = exchange
    if "oi" not in df.columns:
        df["oi"] = 0

    # Drop Trade_J-specific columns
    drop_cols = [c for c in df.columns if c not in [*CANONICAL_COLUMNS, "vwap", "trade_count"]]
    df = df.drop(columns=drop_cols, errors="ignore")

    # Ensure canonical column order
    for col in CANONICAL_COLUMNS:
        if col not in df.columns:
            df[col] = 0 if col in ("volume", "oi") else ""
    df["event_time"] = df["timestamp"]
    df = df[CANONICAL_COLUMNS].dropna(subset=["timestamp"])

    now_ist = pd.Timestamp.now(tz="Asia/Kolkata").tz_localize(None)
    df["published_at"] = now_ist
    df["ingested_at"] = now_ist
    df["is_correction"] = False

    # Validate OHLCV consistency
    df = validate_candles(df, symbol=symbol, drop_invalid=True)

    return df


def convert_tradej_directory(
    tradej_bars_dir: Path,
    target_dir: Path,
    symbols: list[str] | None = None,
    timeframe: str = "1m",
) -> dict[str, dict[str, int]]:
    """Convert all Trade_J Parquet files to canonical hive-partitioned layout.

    Parameters
    ----------
    tradej_bars_dir : Path
        Path to Trade_J bars directory.
    target_dir : Path
        Target directory (hive-partitioned).
    symbols : list of str or None
        Specific symbols to convert. None = all.
    timeframe : str
        Target timeframe.

    Returns
    -------
    Dict mapping symbol → {rows, duplicates_dropped, invalid_dropped}.
    """
    results: dict[str, dict[str, int]] = {}

    symbol_dirs = sorted(tradej_bars_dir.iterdir())
    if symbols:
        symbol_set = {normalize_symbol(s) for s in symbols}
        symbol_dirs = [
            d for d in symbol_dirs if normalize_symbol(d.name.replace("symbol=", "")) in symbol_set
        ]

    for sym_dir in symbol_dirs:
        if not sym_dir.is_dir():
            continue

        symbol = normalize_symbol(sym_dir.name.replace("symbol=", ""))
        logger.info("Converting %s...", symbol)

        parquet_files = sorted(sym_dir.glob("*.parquet"))
        if not parquet_files:
            continue

        dfs = []
        invalid_total = 0
        for pf in parquet_files:
            try:
                df = convert_tradej_parquet(pf, symbol)
                dfs.append(df)
            except Exception as exc:
                logger.warning("Failed to convert %s: %s", pf, exc)

        if not dfs:
            continue

        combined = pd.concat(dfs, ignore_index=True)
        combined = combined.sort_values("timestamp")

        # Log duplicates before dropping
        dup_count = combined.duplicated(subset=["timestamp"]).sum()
        if dup_count > 0:
            logger.warning("%s: dropping %d duplicate timestamps", symbol, dup_count)

        combined = combined.drop_duplicates(subset=["timestamp"], keep="last")

        # Write to hive partition atomically
        sym_target = target_dir / f"symbol={symbol}"
        sym_target.mkdir(parents=True, exist_ok=True)

        table = pa.Table.from_pandas(combined, preserve_index=False)
        atomic_parquet_write(sym_target / "data.parquet", table, compression="snappy")

        results[symbol] = {
            "rows": len(combined),
            "duplicates_dropped": dup_count,
            "invalid_dropped": invalid_total,
        }
        logger.info("  %s: %d rows (%d duplicates dropped)", symbol, len(combined), dup_count)

    return results
