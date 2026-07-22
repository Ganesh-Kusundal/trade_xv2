"""Datalake self-update: sync every **manifest-approved** symbol up to today.

This is the datalake layer's own "keep myself current" capability — it owns
the loop that decides which symbols are stale and repairs them, using
:meth:`HistoricalDataLoader.repair_missing` (per-symbol diff-and-catch-up).

Symbol scope comes from ``{lake_root}/sync_manifest.csv`` (see
:mod:`datalake.ingestion.sync_manifest`) — **not** from filesystem discovery.
New symbols require an explicit manifest entry (``download_universe`` adds them
automatically).

It takes ``fetch_fn``/``gateway`` as an injected dependency rather than
importing brokers or ``application`` directly (datalake must not depend on
those layers). Federation wiring lives in ``runtime.datalake_sync`` or
``application.data.sync_fetch_strategy``.

Callers: ``DataLake.sync()``, ``runtime.datalake_sync.run_federated_sync()``,
``scripts/sync_datalake.py``, ``tradex datalake sync``, ``POST /api/v1/datalake/sync``.
"""

from __future__ import annotations

import csv
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from domain.ports.data_catalog import DEFAULT_DATA_PATHS
from domain.ports.historical_fetch import HistoricalFetchPort
from infrastructure.batch_executor import batch_execute

logger = logging.getLogger(__name__)

RepairScope = Literal["tail", "internal", "all"]


@dataclass
class SyncReport:
    """Result of a :func:`sync_all` run."""

    symbols_total: int
    results: dict[str, int] = field(default_factory=dict)  # symbol -> new rows
    errors: dict[str, str] = field(default_factory=dict)  # symbol -> error message
    elapsed_s: float = 0.0
    health_ok: bool = True
    health_results: dict[str, Any] = field(default_factory=dict)

    @property
    def up_to_date(self) -> int:
        return sum(1 for r in self.results.values() if r == 0)

    @property
    def synced_with_new_data(self) -> int:
        return sum(1 for r in self.results.values() if r > 0)

    @property
    def total_new_rows(self) -> int:
        return sum(self.results.values())

    @property
    def ok(self) -> bool:
        return not self.errors and self.health_ok

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbols_total": self.symbols_total,
            "processed": len(self.results),
            "up_to_date": self.up_to_date,
            "synced_with_new_data": self.synced_with_new_data,
            "total_new_rows": self.total_new_rows,
            "errors": self.errors,
            "elapsed_s": round(self.elapsed_s, 1),
            "health_ok": self.health_ok,
            "health_results": self.health_results,
            "ok": self.ok,
        }


def existing_symbols(root: str, asset: str, timeframe: str) -> list[str]:
    base = Path(root) / asset / "candles" / f"timeframe={timeframe}"
    if not base.exists():
        return []
    return sorted(
        p.name.removeprefix("symbol=")
        for p in base.iterdir()
        if p.is_dir() and p.name.startswith("symbol=")
    )


def load_delisted(root: str) -> set[str]:
    """Symbols every broker has confirmed can't be fetched. Skips them at the
    source instead of re-discovering the same broker rejection every run.
    Applies to **both** equities and indices.
    Edit ``<root>/delisted_symbols.csv`` to add/remove entries."""
    path = Path(root) / "delisted_symbols.csv"
    if not path.exists():
        return set()
    with open(path) as f:
        return {row["symbol"] for row in csv.DictReader(f)}


def _health_check_has_issues(results: dict) -> bool:
    for name, result in results.items():
        if name == "thin_coverage":
            if result.get("sample"):
                return True
        elif result.get("count", 0):
            return True
    return False


def run_post_sync_health_check(
    root: str, timeframe: str, symbols: list[str], *, min_rows: int = 10000
) -> tuple[bool, dict]:
    """Run corruption checks on symbols that received new rows this run."""
    if not symbols:
        return True, {}
    from datalake.mcp.tools import DatalakeTools

    tools = DatalakeTools(root=root)
    results = tools.health_check(timeframe=timeframe, min_rows=min_rows, symbols=symbols)
    return not _health_check_has_issues(results), results


def sync_all(
    *,
    fetch_fn: HistoricalFetchPort | None = None,
    gateway: Any = None,
    root: str | None = None,
    assets: tuple[str, ...] = ("equities", "indices"),
    timeframe: str = "1m",
    workers: int = 10,
    limit: int | None = None,
    run_health_check: bool = True,
    repair_scope: RepairScope = "tail",
) -> SyncReport:
    """Sync every registered symbol up to today. The datalake's self-update entrypoint.

    ``repair_scope``:
    - ``"tail"`` (default): catch up last bar → today only — fast daily sync (~15 min).
    - ``"internal"``: fill mid-history trading-day holes only — slow, run off-hours.
    - ``"all"``: both phases.

    One of ``fetch_fn`` (:class:`domain.ports.historical_fetch.HistoricalFetchPort` —
    federated, quota-aware production path) or ``gateway`` (single-broker dev/ad-hoc)
    must be supplied; the caller builds whichever fetch strategy it wants and injects
    it here, since this module cannot import brokers/application.
    """
    from datalake.ingestion.loader import HistoricalDataLoader
    from datalake.storage.catalog import DataCatalog

    root = root or DEFAULT_DATA_PATHS.lake_root
    catalog = DataCatalog(root)
    loader = HistoricalDataLoader(root=root, catalog=catalog)

    from datalake.ingestion.sync_manifest import resolve_sync_work
    from datalake.ingestion.catalog_sync_scope import (
        gate_equity_sync_entries,
        list_catalog_symbols,
    )

    delisted = load_delisted(root)
    manifest_work = resolve_sync_work(root, assets=assets, delisted=delisted)
    catalog_symbols = list_catalog_symbols(root, timeframe=timeframe)
    work_entries, _skipped = gate_equity_sync_entries(manifest_work, catalog_symbols)
    work_keys = [f"{entry.symbol}|{entry.asset}" for entry in work_entries]
    if limit:
        work_keys = work_keys[:limit]

    start = time.time()
    results: dict[str, int] = {}
    errors: dict[str, str] = {}

    def _parse_entry(entry: str) -> tuple[str, str | None]:
        symbol, asset = entry.split("|", 1)
        exchange = "INDEX" if asset == "indices" else None
        return symbol, exchange

    def _sync_one(entry: str) -> int:
        symbol, exchange = _parse_entry(entry)
        return loader.repair_missing(
            symbol,
            gateway,
            timeframe=timeframe,
            exchange=exchange,
            fetch_fn=fetch_fn,
            repair_scope=repair_scope,
        )

    def _on_error(entry: str, exc: Exception) -> None:
        symbol, _ = _parse_entry(entry)
        errors[symbol] = str(exc)

    raw_results = batch_execute(work_keys, _sync_one, max_workers=workers, on_error=_on_error)
    for entry, rows in raw_results.items():
        symbol, _ = _parse_entry(entry)
        results[symbol] = results.get(symbol, 0) + rows

    report = SyncReport(
        symbols_total=len(work_keys),
        results=results,
        errors=errors,
        elapsed_s=time.time() - start,
    )

    if run_health_check:
        synced_symbols = [sym for sym, rows in results.items() if rows > 0]
        report.health_ok, report.health_results = run_post_sync_health_check(
            root, timeframe, synced_symbols
        )

    logger.info(
        "datalake.sync_all.complete",
        extra={
            "symbols_total": report.symbols_total,
            "processed": len(report.results),
            "new_rows": report.total_new_rows,
            "errors": len(report.errors),
            "health_ok": report.health_ok,
            "elapsed_s": round(report.elapsed_s, 1),
        },
    )
    return report
