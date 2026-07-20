"""Daily sync: Trade_J DuckDB → TradeXV2 Parquet (incremental, watermark-based).

Strategy:
  1. For each (underlying, expiry_kind, expiry_code) group, find the max
     bar_time_ms in the existing TradeXV2 Parquet file (the "watermark").
  2. Read only rows from Trade_J DuckDB where bar_time_ms > watermark.
  3. Merge with existing data, dedup on (timestamp, symbol), sort, atomic write.
  4. If no Parquet file exists, do a full group read (first-time sync).

Idempotent: running multiple times produces the same result.
Safe: atomic Parquet writes — never corrupts an existing file.

Cron setup (run daily at 6 PM IST, after market close at 3:30 PM):
    # Add to crontab via `crontab -e`:
    TZ=Asia/Kolkata
    0 18 * * 1-5 cd /Users/apple/Downloads/Trade_XV2 && /Users/apple/Downloads/Trade_XV2/venv/bin/python -m interface.ui.main options-sync >> /Users/apple/Downloads/Trade_XV2/logs/options-sync.log 2>&1

    # Setup:
    mkdir -p /Users/apple/Downloads/Trade_XV2/logs
    crontab -e   # add the line above

    # Monday-Friday only (excludes weekends when markets are closed).
    # If Trade_J DuckDB is read-only, the sync is still safe — it will
    # detect no new data and exit cleanly.

After sync, also refresh the option analytics views:
    # The m_pcr / m_max_pain / m_iv_surface tables are NOT auto-refreshed by
    # sync. Run ViewManager.materialize_options() (analytics.views.manager)
    # against DataCatalog to refresh them, or re-run ViewManager.create_all().
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import duckdb
import pandas as pd
import pyarrow as pa

from datalake.core.io import atomic_parquet_write
from datalake.core.option_format import (
    CANONICAL_COLUMNS,
    convert_format,
    map_expiry_code_to_date,
)
from datalake.core.schema import enforce_canonical_schema
from datalake.core.symbols import normalize_symbol_for_storage
from datalake.quality.validation import validate_candles
from infrastructure.paths import project_root_from

# Initialize logging if not already configured
if not logging.getLogger().handlers:
    from infrastructure.logging_config import configure_logging

    configure_logging()
logger = logging.getLogger(__name__)

from domain.ports.data_catalog import DEFAULT_DATA_PATHS

TARGET_ROOT = Path(DEFAULT_DATA_PATHS.lake_root) / "options" / "candles"


def _resolve_trade_j_duckdb(explicit: str | Path | None) -> Path:
    if explicit is not None:
        return Path(explicit)
    if env := os.environ.get("TRADE_J_DUCKDB"):
        return Path(env)
    # ponytail: default under gitignored data/; override via TRADE_J_DUCKDB env
    return project_root_from(__file__) / "data" / "external" / "trade_j" / "historical.duckdb"


def _get_watermark(target_file: Path, conn: duckdb.DuckDBPyConnection) -> int:
    """Return the max bar_time_ms from an existing Parquet file, or 0 if absent.

    Uses the provided DuckDB connection (caller-owned) to avoid per-call connect overhead.

    The Parquet `timestamp` column is naive IST (canonical schema). To get the
    original UTC epoch ms (bar_time_ms in Trade_J), we subtract the IST offset
    before computing EPOCH — otherwise EPOCH() treats the naive timestamp as
    UTC and returns a value 5:30 hours ahead of the source bar_time_ms.
    """
    if not target_file.exists():
        return 0
    try:
        result = conn.execute(
            "SELECT COALESCE(MAX(CAST(EPOCH(timestamp - INTERVAL '5 hours 30 minutes') * 1000 AS BIGINT)), 0) "
            "FROM read_parquet(?)",
            [str(target_file)],
        ).fetchone()
        return int(result[0])
    except Exception:
        return 0


def sync_options(
    trade_j_duckdb: str | Path | None = None, target_root: str | Path | None = None
) -> dict:
    """Run incremental sync. Returns summary dict.

    Parameters
    ----------
    trade_j_duckdb : str | Path | None
        Path to Trade_J DuckDB. Defaults to ``TRADE_J_DUCKDB`` env or
        ``data/external/trade_j/historical.duckdb`` under the repo root.
        Parameterized for testability (tests pass a tmp_path DuckDB).
    target_root : str | Path | None
        Where to write Parquet files. Defaults to TARGET_ROOT.
    """
    src_path = _resolve_trade_j_duckdb(trade_j_duckdb)
    tgt_root = Path(target_root) if target_root else TARGET_ROOT
    summary = {
        "files_merged": 0,
        "files_created": 0,
        "new_rows": 0,
        "total_rows_after": 0,
        "groups": [],
    }

    from datalake.core.duckdb_utils import connect_with_retry

    src = connect_with_retry(str(src_path), read_only=True)
    try:
        # Discover all (underlying, expiry_kind, expiry_code) groups in source
        groups = src.execute("""
            SELECT DISTINCT underlying, expiry_kind, expiry_code
            FROM rolling_option_bars
            ORDER BY underlying, expiry_kind, expiry_code
        """).fetchall()

        for underlying, ek, ec in groups:
            target_dir = (
                tgt_root
                / f"underlying={normalize_symbol_for_storage(underlying)}"
                / f"expiry_kind={ek}"
                / f"expiry_code={ec}"
            )
            target_dir.mkdir(parents=True, exist_ok=True)
            target_file = target_dir / "data.parquet"

            watermark = _get_watermark(target_file, src)
            logger.info("%s %s code=%s: watermark=%s", underlying, ek, ec, watermark)

            # Read only new data from Trade_J (incremental)
            new_rows = src.execute(
                """
                SELECT
                    underlying, expiry_kind, expiry_code, strike_offset, option_type,
                    interval_min, bar_time_ms, open_paisa, high_paisa, low_paisa,
                    close_paisa, volume, iv, oi, spot_paisa, strike_paisa, ingested_at_ms
                FROM rolling_option_bars
                WHERE underlying = ? AND expiry_kind = ? AND expiry_code = ?
                  AND bar_time_ms > ?
                ORDER BY bar_time_ms, strike_offset, option_type
            """,
                [underlying, ek, ec, watermark],
            ).fetchdf()

            if new_rows.empty and target_file.exists():
                logger.info("  No new data, skipping")
                continue

            new_count = len(new_rows)
            logger.info("  Read %d new rows from Trade_J", new_count)

            # Convert new data
            if new_count > 0:
                new_rows = convert_format(new_rows)
                first_ts = int(new_rows["bar_time_ms"].min())
                expiry_date = map_expiry_code_to_date(underlying, ek, int(ec), first_ts)
                new_rows["expiry_date"] = expiry_date
                new_rows = validate_candles(new_rows, symbol=underlying, drop_invalid=True)

            # Merge with existing data
            if target_file.exists():
                existing = pd.read_parquet(target_file)
                before_count = len(existing)
                combined = (
                    pd.concat([existing, new_rows], ignore_index=True)
                    if new_count > 0
                    else existing
                )
                # Dedup on (timestamp, symbol)
                combined = combined.drop_duplicates(subset=["timestamp", "symbol"], keep="last")
                combined = combined.sort_values(["timestamp", "symbol"]).reset_index(drop=True)
                after_count = len(combined)
                deduped = before_count + new_count - after_count
                if deduped > 0:
                    logger.info("  Deduped %d duplicate rows", deduped)
                summary["files_merged"] += 1
            else:
                combined = new_rows.sort_values(["timestamp", "symbol"]).reset_index(drop=True)
                after_count = len(combined)
                summary["files_created"] += 1

            # Select canonical columns
            combined = combined[[c for c in CANONICAL_COLUMNS if c in combined.columns]]

            # Atomic write
            table = pa.Table.from_pandas(combined, preserve_index=False)
            table = enforce_canonical_schema(table)
            atomic_parquet_write(target_file, table, compression="snappy")

            summary["new_rows"] += new_count
            summary["total_rows_after"] += after_count
            summary["groups"].append(
                {
                    "underlying": underlying,
                    "expiry_kind": ek,
                    "expiry_code": int(ec),
                    "new_rows": new_count,
                    "total_rows": after_count,
                }
            )
            logger.info("  Wrote %d rows to %s", after_count, target_file)
    finally:
        src.close()
    return summary


def main() -> int:
    logger.info("=" * 60)
    logger.info("OPTIONS DAILY SYNC: Trade_J DuckDB → TradeXV2 Parquet")
    logger.info("=" * 60)
    summary = sync_options()
    logger.info("=" * 60)
    logger.info(
        "DONE: %s created, %s merged, %s new rows, %s total",
        summary["files_created"],
        summary["files_merged"],
        "{:,}".format(summary["new_rows"]),
        "{:,}".format(summary["total_rows_after"]),
    )
    logger.info("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
