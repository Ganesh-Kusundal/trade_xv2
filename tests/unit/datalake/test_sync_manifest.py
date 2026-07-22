"""sync_manifest allowlist — sync must not discover symbols from filesystem."""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from datalake.ingestion.auto_sync import SyncReport, sync_all
from datalake.ingestion.sync_manifest import (
    SyncManifestEntry,
    add_symbol_to_manifest,
    bootstrap_sync_manifest_from_disk,
    load_sync_manifest,
    manifest_path,
    remove_symbol_from_manifest,
    resolve_sync_work,
    write_sync_manifest,
)
from tests.unit.datalake.test_loader_merge import _candles


def _write_manifest(root: Path, entries: list[tuple[str, str]]) -> None:
    write_sync_manifest(
        str(root),
        [SyncManifestEntry(sym, asset) for sym, asset in entries],  # type: ignore[arg-type]
    )


def _ensure_symbol_dir(root: Path, asset: str, symbol: str, timeframe: str = "1m") -> None:
    sym_dir = root / asset / "candles" / f"timeframe={timeframe}" / f"symbol={symbol}"
    sym_dir.mkdir(parents=True, exist_ok=True)
    # Minimal parquet so repair_missing has something to merge against.
    df = _candles([f"{date.today().isoformat()} 09:15:00"], base_price=100.0, symbol=symbol)
    df.to_parquet(sym_dir / "data.parquet", index=False)


def test_load_sync_manifest_requires_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="sync manifest not found"):
        load_sync_manifest(str(tmp_path))


def test_resolve_sync_work_respects_assets_and_delisted(tmp_path: Path) -> None:
    _write_manifest(
        tmp_path,
        [
            ("AAA", "equities"),
            ("BBB", "equities"),
            ("NIFTY", "indices"),
            ("ORPHAN", "indices"),
        ],
    )
    delisted_path = tmp_path / "delisted_symbols.csv"
    with open(delisted_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["symbol"])
        writer.writerow(["BBB"])

    work = resolve_sync_work(
        str(tmp_path),
        assets=("equities",),
        delisted={"BBB"},
    )
    assert [e.symbol for e in work] == ["AAA"]


def test_sync_all_skips_on_disk_symbol_not_in_manifest(tmp_path: Path) -> None:
    _ensure_symbol_dir(tmp_path, "equities", "IN_MANIFEST")
    _ensure_symbol_dir(tmp_path, "equities", "ORPHAN_ON_DISK")
    _write_manifest(tmp_path, [("IN_MANIFEST", "equities")])

    fetched: list[str] = []

    def fetch_fn(symbol: str, exchange: str, timeframe: str, lookback_days: int) -> pd.DataFrame:
        fetched.append(symbol)
        return _candles([f"{date.today().isoformat()} 10:00:00"], base_price=50.0, symbol=symbol)

    report = sync_all(
        fetch_fn=fetch_fn,
        root=str(tmp_path),
        assets=("equities",),
        run_health_check=False,
    )
    assert report.symbols_total == 1
    assert fetched == ["IN_MANIFEST"]


def test_sync_all_fails_without_manifest(tmp_path: Path) -> None:
    _ensure_symbol_dir(tmp_path, "equities", "AAA")

    def fetch_fn(symbol: str, exchange: str, timeframe: str, lookback_days: int) -> pd.DataFrame:
        return _candles([f"{date.today().isoformat()} 09:15:00"], base_price=50.0, symbol=symbol)

    with pytest.raises(FileNotFoundError, match="sync manifest not found"):
        sync_all(fetch_fn=fetch_fn, root=str(tmp_path), run_health_check=False)


def test_bootstrap_excludes_default_orphans(tmp_path: Path) -> None:
    _ensure_symbol_dir(tmp_path, "indices", "NIFTY")
    _ensure_symbol_dir(tmp_path, "indices", "BSE100")
    _ensure_symbol_dir(tmp_path, "equities", "RELIANCE")

    count = bootstrap_sync_manifest_from_disk(str(tmp_path))
    assert count == 2
    symbols = {e.symbol for e in load_sync_manifest(str(tmp_path))}
    assert symbols == {"NIFTY", "RELIANCE"}
    assert "BSE100" not in symbols


def test_add_and_remove_symbol_from_manifest(tmp_path: Path) -> None:
    _write_manifest(tmp_path, [("AAA", "equities")])
    assert add_symbol_to_manifest(str(tmp_path), "BBB", "equities") is True
    assert add_symbol_to_manifest(str(tmp_path), "AAA", "equities") is False
    assert remove_symbol_from_manifest(str(tmp_path), "AAA", "equities") is True
    assert {e.symbol for e in load_sync_manifest(str(tmp_path))} == {"BBB"}


def test_sync_all_includes_indices_from_manifest(tmp_path: Path) -> None:
    _ensure_symbol_dir(tmp_path, "indices", "NIFTY")
    _write_manifest(tmp_path, [("NIFTY", "indices")])
    fetch_calls: list[tuple[str, str]] = []

    def fetch_fn(symbol: str, exchange: str, timeframe: str, lookback_days: int) -> pd.DataFrame:
        fetch_calls.append((symbol, exchange))
        return _candles([f"{date.today().isoformat()} 09:15:00"], base_price=50.0, symbol=symbol)

    report = sync_all(
        fetch_fn=fetch_fn,
        root=str(tmp_path),
        assets=("indices",),
        run_health_check=False,
    )
    assert isinstance(report, SyncReport)
    assert report.symbols_total == 1
    assert fetch_calls == [("NIFTY", "INDEX")]
