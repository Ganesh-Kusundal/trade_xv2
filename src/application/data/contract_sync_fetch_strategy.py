"""Federated contract historical fetch for datalake sync."""

from __future__ import annotations

from typing import Callable

from application.composer.factory import create_composers
from application.data.contract_historical_coordinator import (
    ContractHistoricalCoordinator,
    require_complete_contract_fetch,
)
from domain.ports.contract_historical_fetch import ContractHistoricalFetchPort
from infrastructure.adapters.market_data_gateway_adapter import wrap_market_gateway
from infrastructure.gateway.factory import require_gateway
from runtime.kernel import ProcessKernel
from runtime.event_loop import ensure_runtime_loop_running


def _detect_upstox_plus() -> frozenset[str]:
    import os

    entitlements: set[str] = set()
    if os.environ.get("UPSTOX_PLUS", "").strip().lower() in {"1", "true", "yes"}:
        entitlements.add("upstox_plus")
    return frozenset(entitlements)


def build_federated_contract_fetch_fn(
    *, print_fn: Callable[[str], None] = print
) -> ContractHistoricalFetchPort:
    """Bootstrap Dhan+Upstox and return contract fetch port."""
    ProcessKernel.wire()
    ensure_runtime_loop_running()
    gateways = []
    for bid in ("dhan", "upstox"):
        try:
            print_fn(f"Bootstrapping {bid} gateway for contract historical...")
            gw = require_gateway(bid, load_instruments=True)
            gateways.append(wrap_market_gateway(gw, bid))
        except Exception as exc:
            print_fn(f"  skip {bid}: {exc}")
    if not gateways:
        raise RuntimeError("No broker gateways available for contract historical sync")
    _composer, execution = create_composers(gateways)
    quota = execution._quota_scheduler
    coordinator = ContractHistoricalCoordinator(
        execution._registry,
        execution._router,
        lambda bid, ep, pri: quota.acquire(bid, ep, pri),
        entitlements=_detect_upstox_plus(),
    )

    def _fetch(query):
        df, ledger = coordinator.fetch(query)
        require_complete_contract_fetch(query, ledger)
        return df, ledger

    return _fetch
