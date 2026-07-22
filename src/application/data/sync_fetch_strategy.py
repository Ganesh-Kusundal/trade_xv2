"""Federated fetch strategy adapter for datalake.ingestion.auto_sync.sync_all().

datalake/ must not import application/ (architecture rule — datalake owns
storage/catalog, application owns broker federation/routing). This module is
the one place that builds a concrete ``fetch_fn`` closure — using the real
application-layer smart router (BrokerRouter + QuotaScheduler +
HistoricalDataCoordinator) — and hands it to ``sync_all`` as a
:class:`domain.ports.historical_fetch.HistoricalFetchPort`, so datalake never
needs to know brokers exist.

Shared by ``runtime.datalake_sync.run_federated_sync``, ``DataLake.sync()``,
``scripts/sync_datalake.py``, ``tradex datalake sync``, and
``POST /api/v1/datalake/sync``.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Callable

from domain.ports.historical_fetch import HistoricalFetchPort


def require_complete_federated_fetch(symbol: str, series: Any, ledger: Any) -> None:
    """Sync must not write partial federation results to permanent storage.

    ``series.gaps`` comes from GapDetector after trading-day filtering —
    weekend/holiday-only gaps are excluded. Raises on degraded ledger or
    any remaining trading-day gap (``missing_from_end``, ``missing_chunk``,
    ``all_failed``, ``missing_from_start``).
    """
    if ledger.degraded or series.gaps:
        raise RuntimeError(
            f"[{symbol}] federated fetch degraded: {ledger.degraded_reason} "
            f"gaps={len(series.gaps)}"
        )


def build_federated_fetch_fn(
    *, print_fn: Callable[[str], None] = print
) -> HistoricalFetchPort:
    """Bootstrap Dhan + Upstox and return a :class:`HistoricalFetchPort` for sync."""
    from application.composer.factory import create_composers
    from application.data.historical_coordinator import HistoricalQuery
    from datalake.ingestion.broker_selection import _TIMEFRAME_ALIASES
    from domain.candles.historical import InstrumentRef
    from domain.ports.async_bridge import run_coro_sync
    from infrastructure.adapters.market_data_gateway_adapter import wrap_market_gateway
    from infrastructure.gateway.factory import require_gateway
    from runtime.kernel import ProcessKernel
    from runtime.event_loop import ensure_runtime_loop_running

    ProcessKernel.wire()

    # Without this, every worker thread's run_coro_sync() call below falls
    # back to spinning up and tearing down its own ephemeral event loop per
    # symbol (thousands of times for a full-lake sync) instead of scheduling
    # onto one shared, already-pumping loop via run_coroutine_threadsafe.
    ensure_runtime_loop_running()

    print_fn("Bootstrapping Dhan gateway...")
    dhan_gw = require_gateway("dhan", load_instruments=True)
    print_fn("Bootstrapping Upstox gateway...")
    try:
        upstox_gw = require_gateway("upstox", load_instruments=True)
    except Exception:
        upstox_gw = None

    gateways = [wrap_market_gateway(dhan_gw, "dhan")]
    if upstox_gw is not None:
        gateways.append(wrap_market_gateway(upstox_gw, "upstox"))
    else:
        print_fn("WARNING: Upstox unavailable, federating across Dhan only")

    composer, _execution = create_composers(gateways)

    def _fetch(symbol: str, exchange: str, timeframe: str, lookback_days: int):
        query = HistoricalQuery(
            instrument=InstrumentRef(symbol=symbol, exchange=exchange),
            timeframe=_TIMEFRAME_ALIASES.get(timeframe, timeframe),
            from_date=date.today() - timedelta(days=lookback_days),
            to_date=date.today(),
        )
        series, ledger = run_coro_sync(composer.fetch_historical(query))
        require_complete_federated_fetch(symbol, series, ledger)
        return series.to_dataframe()

    return _fetch
