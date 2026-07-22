"""auto_sync.sync_all orchestration — SyncReport shape and multi-symbol loop."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from datalake.ingestion.auto_sync import SyncReport, sync_all
from datalake.ingestion.sync_manifest import SyncManifestEntry, write_sync_manifest
from tests.unit.datalake.test_loader_merge import _candles


def _ensure_symbol_dir(root: Path, asset: str, symbol: str, timeframe: str = "1m") -> None:
    sym_dir = root / asset / "candles" / f"timeframe={timeframe}" / f"symbol={symbol}"
    sym_dir.mkdir(parents=True, exist_ok=True)
    df = _candles([f"{date.today().isoformat()} 09:15:00"], base_price=50.0, symbol=symbol)
    df.to_parquet(sym_dir / "data.parquet", index=False)


def _write_manifest(root: Path, entries: list[tuple[str, str]]) -> None:
    write_sync_manifest(
        str(root),
        [SyncManifestEntry(sym, asset) for sym, asset in entries],  # type: ignore[arg-type]
    )


def test_sync_all_returns_sync_report_with_new_rows(tmp_path: Path) -> None:
    for sym in ("AAA", "BBB"):
        _ensure_symbol_dir(tmp_path, "equities", sym)
    _write_manifest(tmp_path, [("AAA", "equities"), ("BBB", "equities")])

    def fetch_fn(symbol: str, exchange: str, timeframe: str, lookback_days: int) -> pd.DataFrame:
        return _candles([f"{date.today().isoformat()} 10:00:00"], base_price=50.0, symbol=symbol)

    report = sync_all(
        fetch_fn=fetch_fn,
        root=str(tmp_path),
        assets=("equities",),
        workers=2,
        run_health_check=False,
    )
    assert isinstance(report, SyncReport)
    assert report.symbols_total == 2
    assert len(report.results) == 2
    assert report.total_new_rows > 0
    assert report.ok
