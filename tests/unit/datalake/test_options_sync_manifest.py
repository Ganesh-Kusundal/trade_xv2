"""Tests for options_sync_manifest."""

from __future__ import annotations

from pathlib import Path

from datalake.ingestion.options_sync_manifest import (
    bootstrap_options_sync_manifest,
    load_options_sync_manifest,
)


def test_bootstrap_writes_six_groups(tmp_path: Path) -> None:
    root = str(tmp_path / "lake")
    n = bootstrap_options_sync_manifest(root, overwrite=True)
    assert n == 6
    entries = load_options_sync_manifest(root)
    assert len(entries) == 6
    underlyings = {e.underlying for e in entries}
    assert underlyings == {"NIFTY", "BANKNIFTY"}
