"""Factory functions to bootstrap composers from injected dependencies.

Provides convenience functions to create fully-wired composer instances
with all required coordinators, routers, and schedulers.

Two creation paths:

1. ``create_composers_from_infra(infra)`` — preferred. Takes an existing
   ``BrokerInfrastructure`` and extracts components from it.
2. ``create_composers(gateways, ...)`` — builds infrastructure internally.
   Kept for backward compatibility.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import date, datetime, timedelta as _TIMEDELTA
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tradex.runtime.broker_port import CommonBrokerGateway
    from tradex.runtime.historical_coordinator import HistoricalDataCoordinator
    from tradex.runtime.infrastructure import BrokerInfrastructure
    from tradex.runtime.policy import SourceSelectionPolicy
    from tradex.runtime.quota_scheduler import QuotaScheduler

from application.composer.execution import ExecutionComposer
from application.composer.market_data import MarketDataComposer

logger = logging.getLogger(__name__)

# Default reconnect-gap backfill uses 1-minute candles. Reconnect gaps are
# intraday by nature, so a fine-grained timeframe maximizes fidelity of the
# reconciled bars.
_DEFAULT_BACKFILL_TIMEFRAME = "1m"

_ONE_DAY = _TIMEDELTA(days=1)


def _split_instrument_key(key: str) -> tuple[str, str]:
    """Best-effort parse of a feed instrument key into (symbol, exchange).

    Feed gap-tracking keys differ per broker:
      - Dhan uses the resolved ticker, e.g. ``"RELIANCE"`` (no exchange).
      - Upstox uses an instrument key, e.g. ``"NSE_EQ|RELIANCE"``.

    When the exchange cannot be recovered we fall back to ``"NSE"``, the
    common case; a wrong guess simply degrades to an empty fetch (no crash).
    """
    key = (key or "").strip()
    if "|" in key:
        parts = key.split("|")
        return parts[-1], parts[0]
    if ":" in key:
        parts = key.split(":")
        return parts[0], parts[-1]
    return key, "NSE"


def _run_async(coro: Any) -> Any:
    """Run a coroutine to completion in an isolated event loop.

    The backfill callback is invoked from a broker WebSocket thread (sync
    context), but ``HistoricalDataCoordinator.fetch`` is async. A fresh loop
    keeps this self-contained and immune to "loop already running" errors in
    the calling thread.
    """
    try:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("default_backfill.async_failed", extra={"error": str(exc)})
        return None


def _bar_to_dict(bar: Any) -> dict:
    """Convert a normalized ``HistoricalBar`` into a feed tick dict.

    ``_publish_tick`` (strict mode) requires a non-zero ``ltp`` and a
    ``symbol``; missing OHLC fields are tolerated but supplied anyway.
    """
    ts = bar.event_time
    ts_iso = ts.isoformat() if isinstance(ts, datetime) else str(ts)
    close = float(bar.close)
    return {
        "symbol": bar.instrument.symbol,
        "exchange": bar.instrument.exchange,
        "ltp": close,
        "open": float(bar.open),
        "high": float(bar.high),
        "low": float(bar.low),
        "close": close,
        "volume": int(bar.volume),
        "timestamp": ts_iso,
    }


def _fetch_gap_bars(
    historical_coordinator: Any,
    symbol: str,
    exchange: str,
    from_dt: datetime,
    to_dt: datetime,
) -> list[dict]:
    """Fetch historical bars covering a reconnect gap for one instrument."""
    from domain.candles.historical import InstrumentRef
    from tradex.runtime.historical_coordinator import HistoricalQuery

    fdate = from_dt.date() if isinstance(from_dt, datetime) else date.fromisoformat(str(from_dt))
    tdate = to_dt.date() if isinstance(to_dt, datetime) else date.fromisoformat(str(to_dt))
    # Reconnect gaps are typically intraday, so from_date often equals
    # to_date (same calendar day). HistoricalQuery is date-granular and the
    # coordinator fetches inclusive date ranges, so extend to_date by a day
    # to ensure the gap day is covered rather than dropped.
    if fdate >= tdate:
        tdate = fdate + _ONE_DAY
    if fdate >= tdate:
        return []

    query = HistoricalQuery(
        instrument=InstrumentRef(symbol=symbol, exchange=exchange),
        timeframe=_DEFAULT_BACKFILL_TIMEFRAME,
        from_date=fdate,
        to_date=tdate,
    )
    result = _run_async(historical_coordinator.fetch(query))
    if result is None:
        return []
    series, _ledger = result
    bars = getattr(series, "bars", None) or []
    return [_bar_to_dict(b) for b in bars]


def _build_default_backfill_callback(
    historical_coordinator: Any,
) -> Callable[[Any, datetime, datetime], list[dict]] | None:
    """Build a default reconnect-gap backfill callback from the historical coordinator.

    Returns ``None`` when no historical source is wired, so callers can
    no-op gracefully (log + skip rather than crash). The returned callback is
    broker-agnostic: it accepts either a single symbol string (Dhan) or a
    list of instrument keys (Upstox) as its first argument.
    """
    if historical_coordinator is None:
        logger.debug("default_backfill.skipped_no_coordinator")
        return None

    def _backfill(symbols: Any, from_dt: datetime, to_dt: datetime) -> list[dict]:
        if isinstance(symbols, (list, tuple, set)):
            keys = [str(k) for k in symbols]
        else:
            keys = [str(symbols)]
        out: list[dict] = []
        for key in keys:
            try:
                symbol, exchange = _split_instrument_key(key)
                if not symbol:
                    continue
                out.extend(
                    _fetch_gap_bars(historical_coordinator, symbol, exchange, from_dt, to_dt)
                )
            except Exception as exc:
                logger.warning(
                    "default_backfill.failed",
                    extra={"symbol": key, "error": str(exc)},
                )
        return out

    return _backfill


def _apply_default_backfill(
    gateways: list[Any] | None,
    callback: Callable[[Any, datetime, datetime], list[dict]] | None,
) -> None:
    """Defensively install a backfill callback on each gateway's feed source.

    Broker feeds read ``_backfill_callback`` at feed-construction time from
    their owning connection/lifecycle object. We set it on every plausible
    target in the gateway object graph so the next ``stream()`` picks it up.
    Never raises — reconnect backfill is strictly best-effort.
    """
    if callback is None:
        return
    for gw in gateways or []:
        candidates: list[Any] = []
        if hasattr(gw, "_backfill_callback") or hasattr(gw, "backfill_callback"):
            candidates.append(gw)
        conn = getattr(gw, "_conn", None)
        if conn is not None:
            candidates.append(conn)
            lc = getattr(conn, "_lifecycle_helper", None)
            if lc is not None:
                candidates.append(lc)
        sub = getattr(gw, "_gateway", None)
        if sub is not None:
            candidates.append(sub)
            sub_conn = getattr(sub, "_conn", None)
            if sub_conn is not None:
                candidates.append(sub_conn)
                sub_lc = getattr(sub_conn, "_lifecycle_helper", None)
                if sub_lc is not None:
                    candidates.append(sub_lc)
        for target in candidates:
            try:
                target._backfill_callback = callback
            except Exception:
                logger.debug(
                    "default_backfill.set_failed",
                    extra={"target": type(target).__name__},
                )


def create_composers_from_infra(
    infra: BrokerInfrastructure,
    risk_manager: Any | None = None,
    order_manager: Any | None = None,
) -> tuple[MarketDataComposer, ExecutionComposer]:
    """Create composers from an existing BrokerInfrastructure.

    This is the preferred creation path when infrastructure is already
    bootstrapped (e.g. via ``bootstrap_from_gateways``).

    Parameters
    ----------
    infra
        Fully-wired BrokerInfrastructure with registry, router, quota,
        historical coordinator, stream orchestrator, and extensions.
    risk_manager
        Optional risk manager for kill-switch enforcement in ExecutionComposer.

    Returns
    -------
    tuple[MarketDataComposer, ExecutionComposer]
        Wired composer instances ready for use.
    """
    if risk_manager is None:
        from application.oms._internal.risk_manager import RiskConfig, RiskManager

        risk_manager = RiskManager(config=RiskConfig())
    if order_manager is None:
        from application.oms.order_manager import OrderManager

        order_manager = OrderManager(risk_manager=risk_manager)

    market_data = MarketDataComposer(
        historical_coordinator=infra.historical,
        stream_orchestrator=infra.streams,
    )
    execution = ExecutionComposer(
        registry=infra.registry,
        router=infra.router,
        quota_scheduler=infra.quota,
        risk_manager=risk_manager,
        order_manager=order_manager,
    )

    # Wire a default reconnect-gap backfill so silent data loss on
    # reconnect is reconciled by default (best-effort; no crash if the
    # historical source is unconfigured).
    _apply_default_backfill(
        [infra.registry.get_gateway(bid) for bid in infra.registry.list_brokers()],
        _build_default_backfill_callback(infra.historical),
    )

    return market_data, execution


def create_composers(
    gateways: list[CommonBrokerGateway],
    policy: SourceSelectionPolicy | None = None,
    quota_scheduler: QuotaScheduler | None = None,
    risk_manager: Any | None = None,
) -> tuple[MarketDataComposer, ExecutionComposer]:
    """Create fully-wired MarketDataComposer and ExecutionComposer.

    Builds infrastructure internally. Prefer ``create_composers_from_infra``
    when infrastructure is already bootstrapped.

    Parameters
    ----------
    gateways
        List of broker gateway instances to register.
    policy
        Source selection policy. Uses default if None.
    quota_scheduler
        Quota scheduler instance. Creates new instance with defaults if None.

    Returns
    -------
    tuple[MarketDataComposer, ExecutionComposer]
        Wired composer instances ready for use.
    """
    from tradex.runtime.historical_coordinator import HistoricalDataCoordinator
    from tradex.runtime.policy_defaults import default_source_selection_policy
    from tradex.runtime.quota_scheduler import QuotaScheduler as QuotaSchedulerCls
    from tradex.runtime.registry import BrokerRegistry
    from tradex.runtime.router import BrokerRouter
    from tradex.runtime.stream_orchestrator import StreamOrchestrator

    # 1. Create registry and register gateways
    registry = BrokerRegistry()
    for gw in gateways:
        registry.register(gw)

    # 2. Create policy
    if policy is None:
        policy = default_source_selection_policy()

    # 3. Create quota scheduler
    if quota_scheduler is None:
        quota_scheduler = QuotaSchedulerCls()
        for broker_id in registry.list_brokers():
            caps = registry.get_capabilities(broker_id).capabilities
            for profile in caps.rate_limit_profiles:
                quota_scheduler.register_profile(broker_id, profile)

    # 4. Create router
    router = BrokerRouter(
        registry=registry,
        policy=policy,
        quota_headroom_fn=quota_scheduler.headroom_for,
    )

    # 5. Create historical coordinator
    historical_coordinator = HistoricalDataCoordinator(
        registry=registry,
        router=router,
        quota_fn=quota_scheduler.acquire,
    )

    # 6. Create stream orchestrator
    stream_orchestrator = StreamOrchestrator(
        registry=registry,
        router=router,
    )

    if risk_manager is None:
        from application.oms._internal.risk_manager import RiskConfig, RiskManager

        risk_manager = RiskManager(config=RiskConfig())

    from application.oms.order_manager import OrderManager

    order_manager = OrderManager(risk_manager=risk_manager)

    # 7. Create composers
    market_data_composer = MarketDataComposer(
        historical_coordinator=historical_coordinator,
        stream_orchestrator=stream_orchestrator,
    )

    execution_composer = ExecutionComposer(
        registry=registry,
        router=router,
        quota_scheduler=quota_scheduler,
        risk_manager=risk_manager,
        order_manager=order_manager,
    )

    # Wire a default reconnect-gap backfill so silent data loss on
    # reconnect is reconciled by default (best-effort; no crash if the
    # historical source is unconfigured).
    _apply_default_backfill(
        gateways,
        _build_default_backfill_callback(historical_coordinator),
    )

    return market_data_composer, execution_composer


def create_market_data_composer(
    gateways: list[CommonBrokerGateway],
    policy: SourceSelectionPolicy | None = None,
) -> MarketDataComposer:
    """Create only MarketDataComposer (for read-only market data use cases)."""
    market_data, _ = create_composers(gateways, policy=policy)
    return market_data


def create_execution_composer(
    gateways: list[CommonBrokerGateway],
    policy: SourceSelectionPolicy | None = None,
    quota_scheduler: QuotaScheduler | None = None,
) -> ExecutionComposer:
    """Create only ExecutionComposer (for execution-only use cases)."""
    _, execution = create_composers(gateways, policy=policy, quota_scheduler=quota_scheduler)
    return execution
