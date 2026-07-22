"""Contract-centric incremental sync with provenance sidecar."""

from __future__ import annotations

import json
import logging
import os
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pyarrow as pa

from datalake.core.io import atomic_parquet_write
from datalake.core.paths import (
    contract_future_partition_path,
    contract_option_partition_path,
)
from datalake.core.schema import enforce_canonical_schema
from datalake.ingestion.contract_sync_manifest import (
    bootstrap_contract_sync_manifest,
    load_contract_sync_manifest,
    parse_manifest_instrument,
)
from datalake.quality.validation import validate_candles
from domain.candles.contract_historical import CONTRACT_CANONICAL_COLUMNS, ContractHistoricalQuery
from domain.historical.contract_state import ContractState
from domain.ports.contract_historical_fetch import ContractHistoricalFetchPort
from domain.ports.data_catalog import DEFAULT_DATA_PATHS

logger = logging.getLogger(__name__)
DEFAULT_LOOKBACK_DAYS = 30
SHADOW_PREFIX = "contracts_shadow"


def _shadow_mode() -> bool:
    return os.environ.get("TRADEX_CONTRACT_LAKE_SHADOW", "").strip() in {"1", "true", "yes"}


def _target_path(entry, lake_root: str, instrument) -> Path:
    expiry = instrument.expiry.isoformat() if instrument.expiry else "NONE"
    root = Path(lake_root)
    if _shadow_mode():
        root = root / SHADOW_PREFIX
    if entry.asset_class == "option":
        return contract_option_partition_path(
            str(root), instrument.exchange, instrument.underlying, expiry, entry.timeframe
        )
    return contract_future_partition_path(
        str(root), instrument.exchange, instrument.underlying, expiry, entry.timeframe
    )


def _provenance_path(data_path: Path) -> Path:
    return data_path.with_name("provenance.json")


def _watermark(data_path: Path) -> date | None:
    if not data_path.exists():
        return None
    try:
        df = pd.read_parquet(data_path, columns=["timestamp"])
        if df.empty:
            return None
        return pd.Timestamp(df["timestamp"].max()).date()
    except Exception:
        return None


def sync_contracts(
    fetch_fn: ContractHistoricalFetchPort,
    *,
    lake_root: str | None = None,
    bootstrap_manifest: bool = True,
) -> dict:
    """Incremental contract sync for manifest entries."""
    root = lake_root or DEFAULT_DATA_PATHS.lake_root
    if bootstrap_manifest:
        bootstrap_contract_sync_manifest(root)
    from datalake.ingestion.catalog_sync_scope import (
        gate_contract_sync_entries,
        list_catalog_option_groups,
    )

    manifest_entries = load_contract_sync_manifest(root)
    catalog_groups = list_catalog_option_groups(root)
    entries, skipped = gate_contract_sync_entries(manifest_entries, catalog_groups)
    summary = {
        "files_written": 0,
        "new_rows": 0,
        "entries": [],
        "skipped_not_in_catalog": skipped,
        "shadow": _shadow_mode(),
    }
    today = date.today()

    for entry in entries:
        instrument = parse_manifest_instrument(entry)
        target = _target_path(entry, root, instrument)
        target.parent.mkdir(parents=True, exist_ok=True)
        wm = _watermark(target)
        from_date = (wm + timedelta(days=1)) if wm else today - timedelta(days=DEFAULT_LOOKBACK_DAYS)
        if from_date > today:
            continue
        state = ContractState.EXPIRED if entry.rolling_expiry_kind else ContractState.AUTO
        query = ContractHistoricalQuery(
            instrument=instrument,
            from_date=from_date,
            to_date=today,
            timeframe=entry.timeframe,
            contract_state=state,
            rolling_expiry_kind=entry.rolling_expiry_kind,
            rolling_expiry_code=entry.rolling_expiry_code,
            rolling_strike_offset=entry.rolling_strike_offset,
        )
        df, ledger = fetch_fn(query)
        if df is None or df.empty:
            continue
        if "symbol" not in df.columns:
            df = df.copy()
            df["symbol"] = instrument.underlying
        df = validate_candles(df, symbol=instrument.underlying, drop_invalid=True)
        if target.exists():
            existing = pd.read_parquet(target)
            df = pd.concat([existing, df], ignore_index=True)
            df = df.drop_duplicates(subset=["timestamp", "instrument_id"], keep="last")
        df = df.sort_values(["timestamp"]).reset_index(drop=True)
        cols = [c for c in CONTRACT_CANONICAL_COLUMNS if c in df.columns]
        table = enforce_canonical_schema(pa.Table.from_pandas(df[cols], preserve_index=False))
        atomic_parquet_write(target, table, compression="snappy")
        _provenance_path(target).write_text(
            json.dumps(ledger.to_summary_dict(), indent=2, default=str),
            encoding="utf-8",
        )
        summary["files_written"] += 1
        summary["new_rows"] += len(df)
        summary["entries"].append(
            {"instrument_id": entry.instrument_id, "rows": len(df), "path": str(target)}
        )
        logger.info("contract_sync wrote %s rows → %s", len(df), target)
    return summary
