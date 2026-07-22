"""Runtime wiring for contract-centric historical datalake sync."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from datalake.ingestion.sync_contracts import sync_contracts


def refresh_contract_analytics_views() -> None:
    """Create contract-centric DuckDB views over contracts/ parquet."""
    from analytics.views.manager import ViewManager

    vm = ViewManager()
    try:
        vm.contracts.create_views(vm.conn)
    finally:
        vm.close()


def run_federated_contract_sync(
    *,
    print_fn: Callable[[str], None] | None = None,
    bootstrap_manifest: bool = True,
    refresh_views: bool = True,
    **kwargs: Any,
) -> dict:
    from application.data.contract_sync_fetch_strategy import build_federated_contract_fetch_fn

    fetch_fn = build_federated_contract_fetch_fn(print_fn=print_fn or print)
    summary = sync_contracts(fetch_fn, bootstrap_manifest=bootstrap_manifest, **kwargs)
    if refresh_views and summary.get("files_written", 0) > 0:
        if print_fn:
            print_fn("Refreshing contract analytics views...")
        refresh_contract_analytics_views()
    return summary
