"""Federated fetch strategy for datalake options sync."""

from __future__ import annotations

from datetime import date
from typing import Callable

from application.composer.factory import create_composers
from application.data.dhan_rolling_options_fetcher import DhanRollingOptionsFetcher
from application.data.options_historical_coordinator import (
    OptionsHistoricalCoordinator,
    require_complete_options_fetch,
)
from domain.candles.options_historical import OptionsHistoricalQuery
from domain.ports.options_historical_fetch import OptionsHistoricalFetchPort
from infrastructure.adapters.market_data_gateway_adapter import wrap_market_gateway
from infrastructure.gateway.factory import require_gateway
from runtime.kernel import ProcessKernel
from runtime.event_loop import ensure_runtime_loop_running


def build_federated_options_fetch_fn(
    *, print_fn: Callable[[str], None] = print
) -> OptionsHistoricalFetchPort:
    """Bootstrap Dhan gateway and return an options fetch port for sync."""
    ProcessKernel.wire()
    ensure_runtime_loop_running()

    print_fn("Bootstrapping Dhan gateway for options historical...")
    dhan_gw = require_gateway("dhan", load_instruments=True)
    gateways = [wrap_market_gateway(dhan_gw, "dhan")]
    _composer, _execution = create_composers(gateways)
    quota = _execution._quota_scheduler  # ponytail: reuse wired scheduler

    def _sync_acquire(broker_id: str, endpoint_class: str, priority_class: str):
        return quota.acquire(broker_id, endpoint_class, priority_class)

    fetcher = DhanRollingOptionsFetcher(
        dhan_gw,
        quota_acquire=lambda bid, ep, _pri: _sync_acquire(bid, ep, "HISTORICAL_BACKFILL"),
        quota_release=quota.release,
    )
    coordinator = OptionsHistoricalCoordinator(fetcher)

    def _fetch(
        underlying: str,
        expiry_kind: str,
        expiry_code: int,
        from_date: date,
        to_date: date,
    ):
        query = OptionsHistoricalQuery(
            underlying=underlying,
            expiry_kind=expiry_kind,  # type: ignore[arg-type]
            expiry_code=int(expiry_code),
            from_date=from_date,
            to_date=to_date,
        )
        df, ledger = coordinator.fetch(query)
        require_complete_options_fetch(underlying, expiry_kind, expiry_code, ledger)
        return df

    return _fetch
