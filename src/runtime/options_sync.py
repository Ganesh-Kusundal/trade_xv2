"""Runtime wiring for federated options datalake sync."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from datalake.ingestion.sync_options import sync_options


def refresh_option_analytics_views() -> None:
    """Rematerialize m_pcr / m_max_pain / m_iv_surface and recreate option views."""
    from analytics.views.manager import ViewManager

    vm = ViewManager()
    try:
        vm._cache.materialize_tables(vm.options.materialization_sql(), vm.conn)
        vm.options.create_views(vm.conn)
    finally:
        vm.close()


def _empty_options_sync_summary() -> dict:
    return {
        "files_merged": 0,
        "files_created": 0,
        "new_rows": 0,
        "total_rows_after": 0,
        "groups": [],
    }


def _groups_needing_sync(*, bootstrap_manifest: bool, **kwargs: Any) -> list:
    """Return manifest groups eligible after catalog gate (no broker I/O)."""
    from datalake.ingestion.catalog_sync_scope import (
        gate_options_sync_entries,
        list_catalog_option_groups,
    )
    from datalake.ingestion.options_sync_manifest import (
        bootstrap_options_sync_manifest,
        load_options_sync_manifest,
    )
    from domain.ports.data_catalog import DEFAULT_DATA_PATHS

    root = kwargs.get("lake_root") or DEFAULT_DATA_PATHS.lake_root
    if bootstrap_manifest:
        bootstrap_options_sync_manifest(root)
    manifest_groups = load_options_sync_manifest(root)
    catalog_groups = list_catalog_option_groups(root)
    groups, _skipped = gate_options_sync_entries(manifest_groups, catalog_groups)
    return groups


def run_federated_options_sync(
    *,
    print_fn: Callable[[str], None] | None = None,
    refresh_views: bool = True,
    bootstrap_manifest: bool = True,
    **kwargs: Any,
) -> dict:
    """Bootstrap Dhan options federation and run incremental options sync."""
    groups = _groups_needing_sync(bootstrap_manifest=bootstrap_manifest, **kwargs)
    if not groups:
        if print_fn:
            print_fn("[dim]No catalog-registered option groups to sync.[/dim]")
        return _empty_options_sync_summary()

    from application.data.options_sync_fetch_strategy import build_federated_options_fetch_fn

    fetch_fn = build_federated_options_fetch_fn(print_fn=print_fn or print)
    summary = sync_options(
        fetch_fn,
        bootstrap_manifest=False,
        **kwargs,
    )
    if refresh_views and summary.get("new_rows", 0) > 0:
        if print_fn:
            print_fn("Refreshing option analytics views...")
        refresh_option_analytics_views()
    return summary
