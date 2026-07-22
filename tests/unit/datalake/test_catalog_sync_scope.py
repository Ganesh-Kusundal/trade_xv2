"""Tests for catalog-gated datalake sync scope."""

from __future__ import annotations

from pathlib import Path

import duckdb

from datalake.ingestion.catalog_sync_scope import (
    CatalogOptionGroup,
    contract_entries_from_catalog,
    gate_contract_sync_entries,
    gate_equity_sync_entries,
    gate_options_sync_entries,
    list_catalog_option_groups,
)
from datalake.ingestion.contract_sync_manifest import ContractSyncManifestEntry
from datalake.ingestion.options_sync_manifest import OptionsSyncManifestEntry
from datalake.ingestion.sync_manifest import SyncManifestEntry


def test_gate_equity_skips_symbols_not_in_catalog() -> None:
    entries = [
        SyncManifestEntry("NIFTY", "indices"),
        SyncManifestEntry("UNKNOWN", "equities"),
    ]
    eligible, skipped = gate_equity_sync_entries(entries, frozenset({"NIFTY"}))
    assert len(eligible) == 1
    assert eligible[0].symbol == "NIFTY"
    assert skipped == ["UNKNOWN"]


def test_gate_options_empty_catalog_skips_all() -> None:
    manifest = [OptionsSyncManifestEntry("NIFTY", "WEEK", 1)]
    eligible, skipped = gate_options_sync_entries(manifest, [])
    assert eligible == []
    assert skipped == ["NIFTY/WEEK/1"]


def test_gate_options_matches_catalog_groups() -> None:
    manifest = [
        OptionsSyncManifestEntry("NIFTY", "WEEK", 1),
        OptionsSyncManifestEntry("NIFTY", "WEEK", 99),
    ]
    catalog = [CatalogOptionGroup("NIFTY", "WEEK", 1)]
    eligible, skipped = gate_options_sync_entries(manifest, catalog)
    assert len(eligible) == 1
    assert skipped == ["NIFTY/WEEK/99"]


def test_gate_contract_rolling_requires_catalog_group() -> None:
    entries = [
        ContractSyncManifestEntry(
            instrument_id="NFO:NIFTY:20250102:24000:CE",
            timeframe="5m",
            asset_class="option",
            rolling_expiry_kind="WEEK",
            rolling_expiry_code=1,
        ),
        ContractSyncManifestEntry(
            instrument_id="NFO:NIFTY:20250102:24000:CE",
            timeframe="5m",
            asset_class="option",
            rolling_expiry_kind="WEEK",
            rolling_expiry_code=99,
        ),
    ]
    catalog = [CatalogOptionGroup("NIFTY", "WEEK", 1)]
    eligible, skipped = gate_contract_sync_entries(entries, catalog)
    assert len(eligible) == 1
    assert len(skipped) == 1


def test_contract_entries_from_catalog_does_not_synthesize_rolling_groups(
    tmp_path: Path,
) -> None:
    root = tmp_path / "lake"
    root.mkdir()
    db = root / "catalog.duckdb"
    con = duckdb.connect(str(db))
    con.execute(
        """
        CREATE TABLE m_pcr AS SELECT * FROM (VALUES
            (TIMESTAMP '2026-01-01 09:15:00', 'NIFTY', 'WEEK', 1,
             DATE '2026-01-02', 24000.0, 0, 0, 0, 0)
        ) AS t(timestamp, underlying, expiry_kind, expiry_code, expiry_date,
               spot, total_ce_volume, total_pe_volume, total_ce_oi, total_pe_oi)
        """
    )
    con.close()
    entries = contract_entries_from_catalog(str(root))
    assert entries == []
    groups = list_catalog_option_groups(str(root))
    assert len(groups) == 1
