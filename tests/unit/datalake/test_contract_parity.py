"""Contract shadow parity helper tests."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from datalake.core.paths import contract_option_partition_path
from datalake.ingestion.contract_parity import compare_contract_shadow_parity


def test_parity_skips_when_files_missing(tmp_path: Path) -> None:
    result = compare_contract_shadow_parity(
        lake_root=str(tmp_path),
        expiry="2026-06-26",
    )
    assert result["status"] == "skipped"


def test_parity_passes_on_identical_files(tmp_path: Path) -> None:
    root = tmp_path / "lake"
    expiry = "2026-06-26"
    prod = contract_option_partition_path(str(root), "NFO", "NIFTY", expiry, "5m")
    shadow = contract_option_partition_path(
        str(root / "contracts_shadow"), "NFO", "NIFTY", expiry, "5m"
    )
    prod.parent.mkdir(parents=True)
    shadow.parent.mkdir(parents=True)
    df = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2026-06-01 09:15:00"]),
            "instrument_id": ["NFO:NIFTY:2026-06-26:24500:CE"],
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
            "volume": [1000],
        }
    )
    df.to_parquet(prod, index=False)
    df.to_parquet(shadow, index=False)
    result = compare_contract_shadow_parity(
        lake_root=str(root),
        expiry=expiry,
    )
    assert result["status"] == "pass"
    assert result["overlap_rows"] == 1
