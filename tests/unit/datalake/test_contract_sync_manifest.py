"""Tests for contract_sync_manifest."""

from __future__ import annotations

from pathlib import Path

from datalake.ingestion.contract_sync_manifest import (
    bootstrap_contract_sync_manifest,
    bootstrap_contract_sync_manifest_from_options,
    load_contract_sync_manifest,
    parse_manifest_instrument,
    ContractSyncManifestEntry,
)
from datalake.ingestion.options_sync_manifest import bootstrap_options_sync_manifest
from domain.instruments.instrument_id import InstrumentId


def test_bootstrap_stays_empty_without_exact_contract_rows(tmp_path: Path) -> None:
    root = str(tmp_path / "lake")
    bootstrap_options_sync_manifest(root, overwrite=True)
    bootstrap_contract_sync_manifest(root)
    entries = load_contract_sync_manifest(root)
    assert entries == []


def test_bootstrap_from_options_is_noop(tmp_path: Path) -> None:
    root = str(tmp_path / "lake")
    bootstrap_options_sync_manifest(root, overwrite=True)
    n = bootstrap_contract_sync_manifest_from_options(root)
    assert n == 0
    assert load_contract_sync_manifest(root) == []


def test_parse_full_instrument_id() -> None:
    entry = ContractSyncManifestEntry(
        instrument_id="NFO:NIFTY:20260626:24500:CE",
        timeframe="5m",
        asset_class="option",
    )
    iid = parse_manifest_instrument(entry)
    assert iid.exchange == "NFO"
    assert iid.underlying == "NIFTY"
    assert iid.strike == 24500
    assert iid.right == "CE"


def test_parse_equity_two_part_id() -> None:
    entry = ContractSyncManifestEntry(
        instrument_id="NSE:RELIANCE",
        timeframe="1d",
        asset_class="equity",
    )
    iid = parse_manifest_instrument(entry)
    assert iid == InstrumentId.equity("NSE", "RELIANCE")
