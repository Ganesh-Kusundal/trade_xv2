"""Dependency injection for API routers.

Provides FastAPI dependencies for:
- TradingContext (OMS container)
- DataLakeGateway (historical data)
- ViewManager (DuckDB analytics views)
- DataCatalog (symbol metadata)
- EventBus (real-time events)
- BrokerService (live broker connections)

All services are stored in a typed :class:`ServiceContainer` as the single
source of truth. This module provides FastAPI Depends() wrappers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Literal

from fastapi import HTTPException, status

from application.oms.live_order_authority import RiskRejectedError, authorize_live_order
from domain.exceptions import LiveBrokerBlockedError, ServiceNotFoundError
from domain.ports.event_publisher import EventBusPort
from domain.ports.order_service import OrderServicePort
from domain.ports.protocols import DataProvider
from domain.ports.risk_manager import RiskManagerPort

logger = logging.getLogger(__name__)


@dataclass
class ServiceContainer:
    """Typed API service container (G-P2-1)."""

    datalake_gateway: Any | None = None
    view_manager: Any | None = None
    data_catalog: Any | None = None
    event_bus: EventBusPort | None = None
    broker_service: Any | None = None
    trading_context: Any | None = None
    order_manager: OrderServicePort | None = None
    position_manager: Any | None = None
    risk_manager: RiskManagerPort | None = None
    market_data_composer: DataProvider | None = None
    execution_composer: Any | None = None
    extra: dict[str, Any] = field(default_factory=dict)


# Module-level typed wrapper — set once during startup
_container: ServiceContainer | SimpleNamespace | None = None


def _resolve(name: str) -> Any:
    """Resolve a service from the container by name.

    Raises HTTP 503 if the container is not initialized or the service is unset.
    """
    if _container is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"Service '{name}' is not available (container not initialized). "
                "Check server logs for initialization errors."
            ),
        )
    value = getattr(_container, name, None)
    if value is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"Service '{name}' is not configured. "
                "Related endpoints will return 503 until wired at startup."
            ),
        )
    return value


def get_container() -> ServiceContainer | SimpleNamespace:
    """Get the service container. Raises 503 if not initialized."""
    if _container is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Service container not initialized. "
                "The server is still starting up or failed to initialize. "
                "Check server logs for initialization errors."
            ),
        )
    return _container


def set_container(services: ServiceContainer | SimpleNamespace | dict[str, Any]) -> None:
    """Set services container. Idempotent."""
    global _container  # intentional module singleton — DI container
    if _container is not None:
        logger.warning("Service container already initialized — ignoring duplicate")
        return

    if isinstance(services, dict):
        ns = ServiceContainer(
            **{k: v for k, v in services.items() if k in ServiceContainer.__dataclass_fields__}
        )
        extra = {
            k: v for k, v in services.items() if k not in ServiceContainer.__dataclass_fields__
        }
        ns.extra = extra
        _container = ns
    elif isinstance(services, ServiceContainer):
        _container = services
    else:
        _container = services

    initialized = [
        k for k in ServiceContainer.__dataclass_fields__ if getattr(services, k, None) is not None
    ]
    logger.info("Service container initialized with: %s", initialized)


def reset_container() -> None:
    """Reset the service container. FOR TESTING ONLY.

    This bypasses the idempotent guard in set_container to allow
    tests to isolate their service state. Never call in production.
    """
    global _container, _trade_journal_instance  # intentional module singleton — test reset only
    _container = None
    _trade_journal_instance = None
    from interface.api.lifecycle import reset_api_process_session

    reset_api_process_session()


# ── FastAPI Dependencies ─────────────────────────────────────────────────────


def _container_get(attr: str) -> Any:
    """Resolve a registered service attribute from the container."""
    return _resolve(attr)


def _make_getter(attr: str, doc: str):
    def getter() -> Any:
        return _container_get(attr)

    getter.__doc__ = doc
    getter.__name__ = f"get_{attr}"
    return getter


get_datalake_gateway = _make_getter(
    "datalake_gateway", "Get DataLakeGateway instance for historical data queries."
)
get_view_manager = _make_getter(
    "view_manager", "Get ViewManager instance for DuckDB analytics queries."
)
get_data_catalog = _make_getter("data_catalog", "Get DataCatalog instance for symbol metadata.")
get_broker_service = _make_getter(
    "broker_service", "Get BrokerService instance for live broker connections."
)


def get_event_bus() -> EventBusPort:
    """Get EventBus instance for real-time events."""
    return _container_get("event_bus")  # type: ignore[no-any-return]


def get_trading_context() -> Any:
    """Get the TradingContext. Raises 503 if not initialized."""
    ctx = getattr(_container, "trading_context", None) if _container is not None else None
    if ctx is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "TradingContext not initialized. OMS is not available. "
                "To enable OMS, provide event_bus or trading_context "
                "when creating the FastAPI app."
            ),
        )
    return ctx


def get_order_manager() -> OrderServicePort:
    """Get OrderManager from TradingContext.

    Raises 503 if TradingContext or OrderManager is not available.
    """
    # Check direct registration first (higher priority)
    om = getattr(_container, "order_manager", None) if _container is not None else None
    if om is not None:
        return om  # type: ignore[no-any-return]

    # Fall back to TradingContext
    ctx = getattr(_container, "trading_context", None) if _container is not None else None
    if ctx is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "TradingContext not initialized. OrderManager is unavailable. "
                "To enable order management, provide event_bus or trading_context "
                "when creating the FastAPI app."
            ),
        )

    return ctx.order_manager  # type: ignore[no-any-return]


def get_position_manager() -> Any:
    """Get PositionManager from TradingContext.

    Raises 503 if TradingContext or PositionManager is not available.
    """
    # Check direct registration first (higher priority)
    pm = getattr(_container, "position_manager", None) if _container is not None else None
    if pm is not None:
        return pm

    # Fall back to TradingContext
    ctx = getattr(_container, "trading_context", None) if _container is not None else None
    if ctx is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "TradingContext not initialized. PositionManager is unavailable. "
                "To enable position management, provide event_bus or trading_context "
                "when creating the FastAPI app."
            ),
        )

    return ctx.position_manager


def get_risk_manager() -> RiskManagerPort:
    """Get RiskManager from TradingContext.

    Raises 503 if TradingContext or RiskManager is not available.
    """
    # Check direct registration first (higher priority)
    rm = getattr(_container, "risk_manager", None) if _container is not None else None
    if rm is not None:
        return rm  # type: ignore[no-any-return]

    # Fall back to TradingContext
    ctx = getattr(_container, "trading_context", None) if _container is not None else None
    if ctx is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "TradingContext not initialized. RiskManager is unavailable. "
                "To enable risk management, provide event_bus or trading_context "
                "when creating the FastAPI app."
            ),
        )

    return ctx.risk_manager  # type: ignore[no-any-return]


get_position_repository = get_position_manager


def get_market_data_composer() -> DataProvider:
    """Get MarketDataComposer for unified multi-broker historical/streaming data.

    Raises 503 if not initialized.
    """
    composer = getattr(_container, "market_data_composer", None) if _container is not None else None
    if composer is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "MarketDataComposer not initialized. Multi-broker market data unavailable. "
                "Initialize composers via application.composer.factory.create_composers()."
            ),
        )
    return composer  # type: ignore[no-any-return]


def get_execution_composer() -> Any:
    """Get ExecutionComposer for unified multi-broker order execution.

    Raises 503 if not initialized.
    """
    composer = getattr(_container, "execution_composer", None) if _container is not None else None
    if composer is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "ExecutionComposer not initialized. Multi-broker order execution unavailable. "
                "Initialize composers via application.composer.factory.create_composers()."
            ),
        )
    return composer


def enforce_live_order_authority(
    *,
    mutation_action: Literal["place", "modify", "cancel"] = "place",
    risk_payload: dict[str, Any] | None = None,
) -> None:
    """Authorize a live order mutation at the API boundary.

    Raises HTTP 403 when the live-actionable gate, allow_live_orders flag,
    kill switch, or pre-trade risk path blocks the mutation. In production,
    a missing risk manager is fail-closed.
    """
    svc = get_broker_service()
    broker = (getattr(svc, "active_broker_name", None) or "unknown") if svc else "unknown"
    try:
        risk_manager = get_risk_manager()
    except (HTTPException, ServiceNotFoundError):
        risk_manager = None
    try:
        authorize_live_order(
            broker=broker,
            allow_live_orders=getattr(svc, "allow_live_orders", False) if svc else False,
            risk_manager=risk_manager,
            live_actionable=(
                lambda: bool(getattr(svc, "live_actionable", False)) if svc else False
            ),
            risk_payload=risk_payload,
            mutation_action=mutation_action,
        )
    except LiveBrokerBlockedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
            headers={"Retry-After": "30"},
        ) from exc
    except RiskRejectedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
            headers={"Retry-After": "30"},
        ) from exc


def require_live_broker() -> Any:
    """Return the active broker gateway or raise 503/403 when unavailable.

    Enforces the single live-order authority (P1-T3 / drift D3): every live
    order path through the API must pass the live-actionable readiness gate and
    the ``allow_live_orders`` flag before the broker is returned to a router.
    """
    svc = get_broker_service()
    if svc is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Live broker not configured",
            headers={"Retry-After": "30"},
        )
    broker = svc.active_broker_name or "unknown"
    try:
        risk_manager = get_risk_manager()
    except (HTTPException, ServiceNotFoundError):
        risk_manager = None
    try:
        authorize_live_order(
            broker=broker,
            allow_live_orders=getattr(svc, "allow_live_orders", False),
            risk_manager=risk_manager,
            live_actionable=lambda: bool(getattr(svc, "live_actionable", False)),
            mutation_action="place",
        )
    except LiveBrokerBlockedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
            headers={"Retry-After": "30"},
        ) from exc
    except RiskRejectedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
            headers={"Retry-After": "30"},
        ) from exc
    try:
        return svc.active_broker
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
            headers={"Retry-After": "30"},
        ) from exc


def get_live_broker_name() -> str:
    """Active broker name for response provenance headers."""
    svc = get_broker_service()
    if svc is None:
        return "unknown"
    return str(getattr(svc, "active_broker_name", "unknown"))


def enforce_extended_order_spine_policy() -> None:
    """Block extended order mutations that bypass place_order_spine (audit R6).

    ponytail: until extended orders route through the unified OMS spine, block
    under ADR-0012 paper default and in production/staging always.
    """
    from config.schema import AppConfig
    from runtime.execution_config import is_live_execution_target

    if not is_live_execution_target():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Extended order mutations disabled under ADR-0012 paper-only "
                "execution boundary"
            ),
        )

    cfg = AppConfig.from_env()
    if cfg.is_production_or_staging():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Extended order mutations disabled in production until routed "
                "through unified OMS spine (IdempotencyGuard + place_order_spine)"
            ),
        )


def require_extended_order_spine_allowed() -> None:
    """FastAPI dependency wrapper for extended order mutation routes."""
    enforce_extended_order_spine_policy()


_trade_journal_instance: Any = None


def get_trade_journal() -> Any:
    """Get TradeJournal for historical P&L queries (singleton)."""
    global _trade_journal_instance  # intentional module singleton — lazy init
    if _trade_journal_instance is None:
        from datalake.research.journal import TradeJournal

        _trade_journal_instance = TradeJournal(read_only=True)
    return _trade_journal_instance


# ── Initialization Helper ────────────────────────────────────────────────────


def initialize_all_services(
    datalake_gateway: Any = None,
    view_manager: Any = None,
    data_catalog: Any = None,
    event_bus: Any = None,
    broker_service: Any = None,
    trading_context: Any = None,
    market_data_composer: Any = None,
    execution_composer: Any = None,
    **additional_services: Any,
) -> None:
    """Initialize all services and register them in the DI container.

    Called once during FastAPI app startup to wire up existing TradeXV2 services.
    Must be called before any request is processed.

    Parameters
    ----------
    datalake_gateway:
        DataLakeGateway instance for historical OHLCV data.
    view_manager:
        ViewManager instance for DuckDB analytics views.
    data_catalog:
        DataCatalog instance for symbol metadata.
    event_bus:
        EventBus instance for real-time event publishing.
    broker_service:
        BrokerService instance for live broker connections.
    trading_context:
        TradingContext instance for OMS (order/position/risk management).
    **additional_services:
        Additional services to register (key=name, value=instance).
    """
    # Extract OMS components from trading_context if provided
    order_manager = None
    position_manager = None
    risk_manager = None
    if trading_context is not None:
        order_manager = getattr(trading_context, "order_manager", None)
        position_manager = getattr(trading_context, "position_manager", None)
        # G7: use the public TradingContext.risk_manager property (no getattr reflection).
        risk_manager = trading_context.risk_manager

    services = ServiceContainer(
        datalake_gateway=datalake_gateway,
        view_manager=view_manager,
        data_catalog=data_catalog,
        event_bus=event_bus,
        broker_service=broker_service,
        trading_context=trading_context,
        order_manager=order_manager,
        position_manager=position_manager,
        risk_manager=risk_manager,
        market_data_composer=market_data_composer,
        execution_composer=execution_composer,
        extra=additional_services,
    )

    set_container(services)

    from interface.api.lifecycle import wire_api_process_session

    wire_api_process_session(
        trading_context=trading_context,
        execution_composer=execution_composer,
        runtime=additional_services.get("runtime"),
    )

    # Log initialization status
    all_named = [
        "datalake_gateway",
        "view_manager",
        "data_catalog",
        "event_bus",
        "broker_service",
        "trading_context",
        "order_manager",
        "position_manager",
        "risk_manager",
        "market_data_composer",
        "execution_composer",
    ]
    missing = [n for n in all_named if getattr(services, n) is None]
    if missing:
        logger.warning(
            "Services initialized with missing components: %s. Related endpoints will return 503.",
            missing,
        )
    else:
        logger.info("All services initialized")
