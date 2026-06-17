"""One-time migration: Trade_J DuckDB rolling_option_bars → TradeXV2 Parquet.

Source: /Users/apple/Downloads/Trade_J/runtime-dev/historical.duckdb
  Table: rolling_option_bars (1,023,301 rows, 5-min bars)
  Underlyings: NIFTY (543K), BANKNIFTY (480K)
  Expiries: WEEK code=1+2, MONTH code=1
  Date range: 2026-03-02 → 2026-06-10

Target: market_data/options/candles/underlying=X/expiry_kind=Y/expiry_code=Z/data.parquet
  Schema: timestamp, symbol, underlying, expiry_kind, expiry_code, strike_offset,
          option_type, exchange, open, high, low, close, volume, oi, iv,
          spot, strike, interval_min
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import duckdb
import pyarrow as pa

from datalake.io import atomic_parquet_write
from datalake.option_format import (
    CANONICAL_COLUMNS,
    convert_format,
    map_expiry_code_to_date,
)
from datalake.symbols import normalize_symbol
from datalake.validation import validate_candles

# Initialize logging if not already configured
if not logging.getLogger().handlers:
    from brokers.common.logging_config import setup_logging
    setup_logging()
logger = logging.getLogger(__name__)

TRADE_J_DUCKDB = "/Users/apple/Downloads/Trade_J/runtime-dev/historical.duckdb"
TARGET_ROOT = Path("market_data/options/candles")


def migrate_options() -> dict:
    """Run the one-time migration. Returns summary dict."""
    src = duckdb.connect(TRADE_J_DUCKDB, read_only=True)
    TARGET_ROOT.mkdir(parents=True, exist_ok=True)

    # Read all option data from Trade_J
    logger.info("Reading option data from Trade_J DuckDB...")
    raw = src.execute("""
        SELECT
            underlying,
            expiry_kind,
            expiry_code,
            strike_offset,
            option_type,
            interval_min,
            bar_time_ms,
            open_paisa,
            high_paisa,
            low_paisa,
            close_paisa,
            volume,
            iv,
            oi,
            spot_paisa,
            strike_paisa,
            ingested_at_ms
        FROM rolling_option_bars
        ORDER BY underlying, expiry_kind, expiry_code, bar_time_ms, strike_offset, option_type
    """).fetchdf()
    src.close()

    logger.info(f"  Read {len(raw):,} rows from Trade_J")

    # Convert format
    logger.info("Converting format (paise→rupees, ms→IST datetime)...")
    out = convert_format(raw)

    # Group by (underlying, expiry_kind, expiry_code) and write one file per group
    groups = out.groupby(["underlying", "expiry_kind", "expiry_code"], sort=True)
    summary = {"files_written": 0, "total_rows": 0, "groups": []}

    for (underlying, ek, ec), group_df in groups:
        first_ts = int(group_df["bar_time_ms"].min())
        expiry_date = map_expiry_code_to_date(underlying, ek, int(ec), first_ts)

        # Select canonical columns
        out_df = group_df[[c for c in CANONICAL_COLUMNS if c in group_df.columns]].copy()
        out_df["expiry_date"] = expiry_date

        # Validate
        out_df = validate_candles(out_df, symbol=underlying, drop_invalid=True)

        # Write to hive path
        target_dir = TARGET_ROOT / f"underlying={normalize_symbol(underlying)}" / f"expiry_kind={ek}" / f"expiry_code={ec}"
        target_dir.mkdir(parents=True, exist_ok=True)
        target_file = target_dir / "data.parquet"

        table = pa.Table.from_pandas(out_df, preserve_index=False)
        atomic_parquet_write(target_file, table, compression="snappy")

        summary["files_written"] += 1
        summary["total_rows"] += len(out_df)
        summary["groups"].append({
            "underlying": underlying,
            "expiry_kind": ek,
            "expiry_code": int(ec),
            "expiry_date": expiry_date,
            "rows": len(out_df),
            "path": str(target_file),
        })
        logger.info(
            f"  {underlying} {ek} code={ec} → expiry={expiry_date}  {len(out_df):>6,} rows → {target_file}"
        )

    return summary


def main() -> int:
    logger.info("=" * 60)
    logger.info("OPTIONS MIGRATION: Trade_J DuckDB → TradeXV2 Parquet")
    logger.info("=" * 60)
    summary = migrate_options()
    logger.info("=" * 60)
    logger.info(f"DONE: {summary['files_written']} files, {summary['total_rows']:,} rows")
    logger.info("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
