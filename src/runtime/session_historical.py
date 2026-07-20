"""Historical fetch wiring for BrokerSession — composition root only.

BrokerSession must not import ``application.*`` directly. This module owns
coordinator construction and is registered at startup.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

from domain.candles.historical import HistoricalSeries, InstrumentRef

_fetch_sync: Callable[..., tuple[HistoricalSeries, Any]] | None = None
_build_coordinator: Callable[[Any], Any] | None = None


def register_historical_fetch(
    *,
    fetch_sync: Callable[..., tuple[HistoricalSeries, Any]],
    build_coordinator: Callable[[Any], Any],
) -> None:
    """Register historical coordinator helpers (called from runtime composition)."""
    global _fetch_sync, _build_coordinator
    _fetch_sync = fetch_sync
    _build_coordinator = build_coordinator


def build_historical_coordinator(session: Any) -> Any:
    if _build_coordinator is None:
        raise RuntimeError(
            "Historical coordinator builder not wired. "
            "Call runtime.session_historical.register_historical_fetch() at startup."
        )
    return _build_coordinator(session)


def fetch_historical_sync(
    session: Any,
    *,
    symbol: str,
    exchange: str,
    timeframe: str,
    days: int,
) -> HistoricalSeries:
    if _fetch_sync is None:
        raise RuntimeError(
            "Historical fetch not wired. "
            "Call runtime.session_historical.register_historical_fetch() at startup."
        )
    today = date.today()
    query = _HistoricalQuery(
        instrument=InstrumentRef(symbol=symbol, exchange=exchange),
        timeframe=timeframe,
        from_date=today - timedelta(days=days),
        to_date=today,
    )
    series, _ = _fetch_sync(session, query)
    return series


class _HistoricalQuery:
    """Minimal query bag passed to the wired fetch_sync callable."""

    __slots__ = ("instrument", "timeframe", "from_date", "to_date")

    def __init__(
        self,
        *,
        instrument: InstrumentRef,
        timeframe: str,
        from_date: date,
        to_date: date,
    ) -> None:
        self.instrument = instrument
        self.timeframe = timeframe
        self.from_date = from_date
        self.to_date = to_date


def wire_session_historical() -> None:
    """Register application-backed historical fetch (idempotent)."""
    from application.composer.registry import BrokerRegistry
    from application.composer.router import BrokerRouter
    from application.data.historical_coordinator import (
        HistoricalDataCoordinator,
        HistoricalQuery,
    )
    from application.scheduling.quota_scheduler import PriorityClass, QuotaScheduler
    from domain.policies.source_selection import auto_dual_broker_policy
    from infrastructure.adapters.market_data_gateway_adapter import (
        MarketDataGatewayAdapter,
    )

    def build_coordinator(session: Any) -> HistoricalDataCoordinator:
        provider = session.provider
        gw = getattr(provider, "_gw", None)
        if gw is None:
            broker_id = getattr(session, "broker_id", None) or "unknown"
            raise RuntimeError(
                f"broker {broker_id!r} has no wire adapter (provider._gw is None)"
            )

        caps_fn = getattr(gw, "capabilities", None)
        if not callable(caps_fn):
            broker_id = getattr(session, "broker_id", None) or "unknown"
            raise RuntimeError(
                f"broker {broker_id!r} wire adapter has no capabilities()"
            )
        caps = caps_fn()
        if caps is None or not getattr(caps, "supports_historical_data", False):
            broker_id = getattr(session, "broker_id", None) or "unknown"
            raise RuntimeError(
                f"broker {broker_id!r} does not support historical data"
            )

        broker_id = getattr(session, "broker_id", None) or getattr(gw, "broker_id", "unknown")
        adapter = MarketDataGatewayAdapter(gw, broker_id=str(broker_id), capabilities=caps)
        registry = BrokerRegistry()
        registry.register(adapter)
        scheduler = QuotaScheduler()
        for profile in caps.rate_limit_profiles:
            scheduler.register_profile(str(broker_id), profile)
        router = BrokerRouter(
            registry,
            auto_dual_broker_policy(),
            quota_headroom_fn=scheduler.headroom_for,
        )
        return HistoricalDataCoordinator(
            registry=registry,
            router=router,
            quota_fn=lambda bid, ep, pri: scheduler.acquire(
                bid, ep, PriorityClass[pri]
            ),
        )

    def fetch_sync(session: Any, query: _HistoricalQuery) -> tuple[HistoricalSeries, Any]:
        coordinator = build_coordinator(session)
        app_query = HistoricalQuery(
            instrument=query.instrument,
            timeframe=query.timeframe,
            from_date=query.from_date,
            to_date=query.to_date,
        )
        return coordinator.fetch_sync(app_query)

    register_historical_fetch(fetch_sync=fetch_sync, build_coordinator=build_coordinator)
