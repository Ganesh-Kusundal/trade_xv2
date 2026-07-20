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

import logging
from collections.abc import Callable
from datetime import date, datetime
from datetime import timedelta as _TIMEDELTA
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from application.scheduling.quota_scheduler import QuotaScheduler
    from domain.policies.source_selection import SourceSelectionPolicy
    from domain.ports.broker_adapter import BrokerAdapter
    from domain.ports.broker_infrastructure import BrokerInfrastructurePort

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
    """Run a coroutine to completion via the runtime event-loop boundary.

    The backfill callback is invoked from a broker WebSocket thread (sync
    context), but ``HistoricalDataCoordinator.fetch`` is async.
    """
    try:
        from application.ports import run_coro_sync

        return run_coro_sync(coro)
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
    from application.data.historical_coordinator import HistoricalQuery
    from domain.candles.historical import InstrumentRef

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
    gap_reconciler: Any | None = None,
) -> Callable[[Any, datetime, datetime], list[dict]] | None:
    """Build a default reconnect-gap backfill callback from the historical coordinator.

    Returns ``None`` when no historical source is wired, so callers can
    no-op gracefully (log + skip rather than crash). The returned callback is
    broker-agnostic: it accepts either a single symbol string (Dhan) or a
    list of instrument keys (Upstox) as its first argument.

    When ``gap_reconciler`` (a :class:`GapReconciler`) is supplied, the
    callback also triggers a session-gap reconcile *after* the reconnect
    backfill completes, passing the just-backfilled range as
    ``already_covered_to`` so the reconciler does not re-fetch what the
    reconnect backfill already covered (requirement b).
    """
    if historical_coordinator is None:
        logger.debug("default_backfill.skipped_no_coordinator")
        return None

    def _backfill(symbols: Any, from_dt: datetime, to_dt: datetime) -> list[dict]:
        if isinstance(symbols, list | tuple | set):
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

    if gap_reconciler is None:
        return _backfill

    def _backfill_with_reconcile(symbols: Any, from_dt: datetime, to_dt: datetime) -> list[dict]:
        out = _backfill(symbols, from_dt, to_dt)
        try:
            keys = (
                [str(k) for k in symbols]
                if isinstance(symbols, list | tuple | set)
                else [str(symbols)]
            )
            # Subtract the range the reconnect backfill just filled.
            covered = {k: to_dt for k in keys}
            gap_reconciler.reconcile(keys, already_covered_to=covered)
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug(
                "default_backfill.reconcile_failed",
                extra={"error": str(exc)},
            )
        return out

    return _backfill_with_reconcile


def _default_gap_fill_callback(
    stream_orchestrator: Any | None,
) -> Callable[[str, list[dict]], None]:
    """Best-effort publish sink for reconciled gap bars.

    Tries to push bars through the orchestrator's normal delivery path if it
    exposes an injection hook (forward-compatible); otherwise records a debug
    log. Never raises — reconciliation is strictly best-effort.
    """

    def _fill(key: str, bars: list[dict]) -> None:
        target = stream_orchestrator
        if target is not None and hasattr(target, "inject_reconciled_bars"):
            try:
                target.inject_reconciled_bars(key, bars)  # type: ignore[attr-defined]
                return
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug(
                    "gap_reconcile.fill_inject_failed",
                    extra={"key": key, "error": str(exc)},
                )
        logger.debug(
            "gap_reconcile.filled",
            extra={"key": key, "bar_count": len(bars)},
        )

    return _fill


def _build_gap_reconciler(
    historical_coordinator: Any | None,
    *,
    stream_orchestrator: Any | None = None,
    fill_callback: Callable[[str, list[dict]], None] | None = None,
) -> Any | None:
    """Build a session-gap reconciler (or ``None`` when unavailable / unconfigured).

    Lazy-imports :class:`GapReconciler` so a missing module degrades to a
    no-op rather than a hard import error. Returns ``None`` when no historical
    coordinator is configured, preserving the existing M5 no-op behavior.
    """
    if historical_coordinator is None:
        return None
    try:
        from application.composer.gap_reconciler import GapReconciler
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("gap_reconcile.unavailable", extra={"error": str(exc)})
        return None
    if fill_callback is None:
        fill_callback = _default_gap_fill_callback(stream_orchestrator)
    return GapReconciler(historical_coordinator, fill_callback=fill_callback)


def _attach_initial_gap_reconcile(market_data: Any | None, gap_reconciler: Any | None) -> None:
    """Wire the reconciler to run once shortly after initial connect/subscribe.

    Wraps ``MarketDataComposer.subscribe_market_stream`` so the first real
    subscribe triggers a single session-gap reconcile for the subscribed
    instruments (requirement a). The flag is cleared after the first run so it
    never re-fires. No-op when the reconciler is ``None``.
    """
    if gap_reconciler is None or market_data is None:
        return
    market_data._session_gap_reconciler = gap_reconciler  # type: ignore[attr-defined]
    market_data._gap_reconcile_pending = True  # type: ignore[attr-defined]

    original = market_data.subscribe_market_stream  # type: ignore[attr-defined]

    async def _subscribe_and_reconcile(request: Any) -> str:
        sub_id = await original(request)
        md = market_data
        if getattr(md, "_gap_reconcile_pending", False):
            md._gap_reconcile_pending = False  # type: ignore[attr-defined]
            try:
                instruments = getattr(request, "instruments", None) or set()
                gap_reconciler.reconcile([str(i) for i in instruments])
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug(
                    "gap_reconcile.initial_failed",
                    extra={"error": str(exc)},
                )
        return sub_id

    market_data.subscribe_market_stream = _subscribe_and_reconcile  # type: ignore[attr-defined]


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


def _build_composers(
    *,
    registry: Any,
    router: Any,
    quota_scheduler: Any,
    historical_coordinator: Any,
    batch_quote_coordinator: Any,
    stream_orchestrator: Any,
    risk_manager: Any | None,
    order_manager: Any,
    gateways_for_backfill: list[Any] | None,
) -> tuple[MarketDataComposer, ExecutionComposer]:
    """Shared wiring: build composers + backfill + gap reconcile."""
    market_data = MarketDataComposer(
        historical_coordinator=historical_coordinator,
        batch_quote_coordinator=batch_quote_coordinator,
        stream_orchestrator=stream_orchestrator,
    )
    execution = ExecutionComposer(
        registry=registry,
        router=router,
        quota_scheduler=quota_scheduler,
        risk_manager=risk_manager,
        order_manager=order_manager,
    )
    gap_reconciler = _build_gap_reconciler(
        historical_coordinator,
        stream_orchestrator=stream_orchestrator,
    )
    _apply_default_backfill(
        gateways_for_backfill,
        _build_default_backfill_callback(historical_coordinator, gap_reconciler=gap_reconciler),
    )
    _attach_initial_gap_reconcile(market_data, gap_reconciler)
    return market_data, execution


def _ensure_risk_and_order(
    risk_manager: Any | None,
    order_manager: Any | None,
    *,
    registry: Any,
    router: Any,
    quota_scheduler: Any,
) -> tuple[Any, Any]:
    """Create default risk_manager / order_manager when not provided."""
    if risk_manager is None:
        from application.oms._internal.risk_manager import RiskConfig, RiskManager
        from application.oms.position_manager import PositionManager

        risk_manager = RiskManager(PositionManager(), config=RiskConfig())
    if order_manager is None:
        from application.oms.order_manager import OrderManager

        order_manager = OrderManager(risk_manager=risk_manager)
    return risk_manager, order_manager


def create_composers_from_infra(
    infra: BrokerInfrastructurePort,
    risk_manager: Any | None = None,
    order_manager: Any | None = None,
) -> tuple[MarketDataComposer, ExecutionComposer]:
    """Create composers from an existing BrokerInfrastructure.

    Preferred when infrastructure is already bootstrapped (e.g. via
    ``bootstrap_from_gateways``).
    """
    risk_manager, order_manager = _ensure_risk_and_order(
        risk_manager,
        order_manager,
        registry=infra.registry,
        router=infra.router,
        quota_scheduler=infra.quota,
    )
    return _build_composers(
        registry=infra.registry,
        router=infra.router,
        quota_scheduler=infra.quota,
        historical_coordinator=infra.historical,
        batch_quote_coordinator=infra.batch_quotes,
        stream_orchestrator=infra.streams,
        risk_manager=risk_manager,
        order_manager=order_manager,
        gateways_for_backfill=[
            infra.registry.get_gateway(bid) for bid in infra.registry.list_brokers()
        ],
    )


def create_composers(
    gateways: list[BrokerAdapter],
    policy: SourceSelectionPolicy | None = None,
    quota_scheduler: QuotaScheduler | None = None,
    risk_manager: Any | None = None,
) -> tuple[MarketDataComposer, ExecutionComposer]:
    """Create fully-wired MarketDataComposer and ExecutionComposer.

    Builds infrastructure internally. Prefer ``create_composers_from_infra``
    when infrastructure is already bootstrapped.
    """
    from application.composer.registry import BrokerRegistry
    from application.composer.router import BrokerRouter
    from application.data.batch_quote_coordinator import BatchQuoteCoordinator
    from application.data.historical_coordinator import HistoricalDataCoordinator
    from application.scheduling.quota_scheduler import QuotaScheduler as QuotaSchedulerCls
    from application.streaming.orchestrator import StreamOrchestrator
    from domain.policies.defaults import default_source_selection_policy

    registry = BrokerRegistry()
    for gw in gateways:
        registry.register(gw)

    if policy is None:
        policy = default_source_selection_policy()

    if quota_scheduler is None:
        quota_scheduler = QuotaSchedulerCls()
        for broker_id in registry.list_brokers():
            caps = registry.get_capabilities(broker_id).capabilities
            for profile in caps.rate_limit_profiles:
                quota_scheduler.register_profile(broker_id, profile)

    router = BrokerRouter(
        registry=registry,
        policy=policy,
        quota_headroom_fn=quota_scheduler.headroom_for,
    )

    historical_coordinator = HistoricalDataCoordinator(
        registry=registry,
        router=router,
        quota_fn=quota_scheduler.acquire,
    )
    batch_quote_coordinator = BatchQuoteCoordinator(
        registry=registry,
        router=router,
        quota_fn=quota_scheduler.acquire,
    )
    stream_orchestrator = StreamOrchestrator(registry=registry, router=router)

    risk_manager, order_manager = _ensure_risk_and_order(
        risk_manager,
        None,
        registry=registry,
        router=router,
        quota_scheduler=quota_scheduler,
    )
    return _build_composers(
        registry=registry,
        router=router,
        quota_scheduler=quota_scheduler,
        historical_coordinator=historical_coordinator,
        batch_quote_coordinator=batch_quote_coordinator,
        stream_orchestrator=stream_orchestrator,
        risk_manager=risk_manager,
        order_manager=order_manager,
        gateways_for_backfill=gateways,
    )
