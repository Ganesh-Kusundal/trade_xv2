"""Runtime wiring for federated datalake sync — single composition entrypoint."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from datalake.ingestion.auto_sync import SyncReport, sync_all


def run_federated_sync(
    *,
    print_fn: Callable[[str], None] | None = None,
    **kwargs: Any,
) -> SyncReport:
    """Bootstrap Dhan + Upstox federation and run :func:`datalake.ingestion.auto_sync.sync_all`."""
    from application.data.sync_fetch_strategy import build_federated_fetch_fn

    fetch_fn = build_federated_fetch_fn(print_fn=print_fn or print)
    return sync_all(fetch_fn=fetch_fn, **kwargs)


def run_adhoc_sync(
    gateway: Any,
    **kwargs: Any,
) -> SyncReport:
    """Run sync_all with a single broker gateway (no quota management)."""
    return sync_all(gateway=gateway, **kwargs)
