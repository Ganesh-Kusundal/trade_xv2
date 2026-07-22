"""Daily sync: broker federation → options/candles parquet (incremental, watermark-based).

Uses an injected :class:`domain.ports.options_historical_fetch.OptionsHistoricalFetchPort`
(Dhan rolling API via ``build_federated_options_fetch_fn``). Manifest-gated via
``options_sync_manifest.csv``.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pyarrow as pa

from datalake.core.io import atomic_parquet_write
from datalake.core.option_format import CANONICAL_COLUMNS
from datalake.core.schema import enforce_canonical_schema
from datalake.core.symbols import normalize_symbol_for_storage
from datalake.ingestion.options_sync_manifest import (
    bootstrap_options_sync_manifest,
    load_options_sync_manifest,
)
from datalake.quality.validation import validate_candles
from domain.ports.data_catalog import DEFAULT_DATA_PATHS
from domain.ports.options_historical_fetch import OptionsHistoricalFetchPort

if not logging.getLogger().handlers:
    from infrastructure.logging_config import configure_logging

    configure_logging()
logger = logging.getLogger(__name__)

TARGET_ROOT = Path(DEFAULT_DATA_PATHS.lake_root) / "options" / "candles"
DEFAULT_LOOKBACK_DAYS = 365


def _get_watermark_date(target_file: Path) -> date | None:
    """Return the latest bar date in an existing parquet file, or None."""
    if not target_file.exists():
        return None
    try:
        df = pd.read_parquet(target_file, columns=["timestamp"])
        if df.empty:
            return None
        return pd.Timestamp(df["timestamp"].max()).date()
    except Exception:
        return None


def sync_options(
    fetch_fn: OptionsHistoricalFetchPort,
    *,
    target_root: str | Path | None = None,
    lake_root: str | None = None,
    bootstrap_manifest: bool = False,
) -> dict:
    """Run incremental options sync for all manifest groups."""
    root = lake_root or DEFAULT_DATA_PATHS.lake_root
    if bootstrap_manifest:
        bootstrap_options_sync_manifest(root)
    tgt_root = Path(target_root) if target_root else TARGET_ROOT
    from datalake.ingestion.catalog_sync_scope import (
        gate_options_sync_entries,
        list_catalog_option_groups,
    )

    manifest_groups = load_options_sync_manifest(root)
    catalog_groups = list_catalog_option_groups(root)
    groups, _skipped = gate_options_sync_entries(manifest_groups, catalog_groups)

    summary = {
        "files_merged": 0,
        "files_created": 0,
        "new_rows": 0,
        "total_rows_after": 0,
        "groups": [],
    }
    today = date.today()

    for entry in groups:
        underlying = entry.underlying
        ek = entry.expiry_kind
        ec = entry.expiry_code
        target_dir = (
            tgt_root
            / f"underlying={normalize_symbol_for_storage(underlying)}"
            / f"expiry_kind={ek}"
            / f"expiry_code={ec}"
        )
        target_dir.mkdir(parents=True, exist_ok=True)
        target_file = target_dir / "data.parquet"

        watermark = _get_watermark_date(target_file)
        if watermark is None:
            from_date = today - timedelta(days=DEFAULT_LOOKBACK_DAYS)
        else:
            from_date = watermark + timedelta(days=1)

        if from_date > today:
            logger.info("%s %s code=%s: up to date (watermark=%s)", underlying, ek, ec, watermark)
            continue

        logger.info(
            "%s %s code=%s: fetching %s → %s (watermark=%s)",
            underlying,
            ek,
            ec,
            from_date,
            today,
            watermark,
        )
        new_rows = fetch_fn(underlying, ek, ec, from_date, today)
        new_count = len(new_rows) if new_rows is not None and not new_rows.empty else 0
        logger.info("  Fetched %d rows from broker federation", new_count)

        if new_count > 0:
            new_rows = validate_candles(new_rows, symbol=underlying, drop_invalid=True)

        if new_count == 0 and target_file.exists():
            logger.info("  No new data, skipping write")
            continue

        if target_file.exists():
            existing = pd.read_parquet(target_file)
            before_count = len(existing)
            combined = (
                pd.concat([existing, new_rows], ignore_index=True)
                if new_count > 0
                else existing
            )
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

        combined = combined[[c for c in CANONICAL_COLUMNS if c in combined.columns]]
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

    return summary
