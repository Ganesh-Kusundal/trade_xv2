"""Shadow vs production contract-lake parity checks (ADR-0023 cutover)."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from datalake.core.paths import contract_option_partition_path
from domain.ports.data_catalog import DEFAULT_DATA_PATHS

logger = logging.getLogger(__name__)
SHADOW_ROOT = "contracts_shadow"


def compare_contract_shadow_parity(
    *,
    lake_root: str | None = None,
    exchange: str = "NFO",
    underlying: str = "NIFTY",
    expiry: str,
    timeframe: str = "5m",
    asset_class: str = "option",
    rtol: float = 1e-5,
) -> dict:
    """Compare shadow-write parquet against production contract path when both exist."""
    root = Path(lake_root or DEFAULT_DATA_PATHS.lake_root)
    if asset_class != "option":
        return {"status": "skipped", "reason": "only option parity implemented"}

    prod = contract_option_partition_path(
        str(root), exchange, underlying, expiry, timeframe
    )
    shadow = contract_option_partition_path(
        str(root / SHADOW_ROOT), exchange, underlying, expiry, timeframe
    )
    if not prod.exists() or not shadow.exists():
        return {
            "status": "skipped",
            "reason": "missing prod or shadow file",
            "prod": str(prod),
            "shadow": str(shadow),
        }

    prod_df = pd.read_parquet(prod)
    shadow_df = pd.read_parquet(shadow)
    prod_rows = len(prod_df)
    shadow_rows = len(shadow_df)
    overlap = 0
    ohlc_mismatch = 0
    if prod_rows and shadow_rows and "timestamp" in prod_df.columns:
        merged = prod_df.merge(
            shadow_df,
            on=["timestamp", "instrument_id"],
            suffixes=("_prod", "_shadow"),
            how="inner",
        )
        overlap = len(merged)
        for col in ("open", "high", "low", "close"):
            pc, sc = f"{col}_prod", f"{col}_shadow"
            if pc in merged.columns and sc in merged.columns:
                diff = (merged[pc] - merged[sc]).abs()
                ohlc_mismatch += int((diff > rtol).sum())

    ok = overlap > 0 and ohlc_mismatch == 0 and abs(prod_rows - shadow_rows) <= max(
        1, int(0.01 * max(prod_rows, shadow_rows))
    )
    return {
        "status": "pass" if ok else "fail",
        "prod_rows": prod_rows,
        "shadow_rows": shadow_rows,
        "overlap_rows": overlap,
        "ohlc_mismatch": ohlc_mismatch,
        "prod": str(prod),
        "shadow": str(shadow),
    }
