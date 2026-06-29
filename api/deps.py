"""Dependency injection for API routers.

Provides FastAPI dependencies for:
- TradingContext (OMS container)
- DataLakeGateway (historical data)
- ViewManager (DuckDB analytics views)
- DataCatalog (symbol metadata)
- EventBus (real-time events)
- BrokerService (live broker connections)

Uses a module-level ServiceContainer dataclass instead of a raw dict
so that services are discoverable and type-safe. The container is
populated once during FastAPI lifespan startup and is immutable
(no new services can be added mid-request).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException, status

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ServiceContainer:
    """Immutable container for all registered API services.

    Populated once at application startup during the lifespan event.
    After creation, the container is frozen — no services can be
    added or removed at runtime. This prevents the race conditions
    that were possible with the previous mutable global dict.
    """

    datalake_gateway: Any = None
    view_manager: Any = None
    data_catalog: Any = None
    event_bus: Any = None
    broker_service: Any = None
    trading_context: Any = None
    risk_manager: Any = None
    order_manager: Any = None
    position_manager: Any = None
    market_data_composer: Any = None
    execution_composer: Any = None
    extra: dict[str, Any] = field(default_factory=dict)

    def is_oms_ready(self) -> bool:
        """Check if all OMS components are available.

        Returns True only if TradingContext and all OMS managers
        (OrderManager, PositionManager, RiskManager) are initialized.
        """
        return (
            self.trading_context is not None
            and self.order_manager is not None
            and self.position_manager is not None
            and self.risk_manager is not None
        )

    def get_missing_services(self) -> list[str]:
        """Get list of services that are not initialized."""
        missing = []
        for attr_name in [
            "datalake_gateway",
            "view_manager",
            "data_catalog",
            "event_bus",
            "broker_service",
            "trading_context",
            "risk_manager",
            "order_manager",
            "position_manager",
            "market_data_composer",
            "execution_composer",
        ]:
            if getattr(self, attr_name) is None:
                missing.append(attr_name)
        return missing


# Single immutable container instance — set once during startup
_container: ServiceContainer | None = None


def get_container() -> ServiceContainer:
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


def set_container(container: ServiceContainer) -> None:
    """Set the service container during app startup. Idempotent."""
    global _container
    if _container is not None:
        logger.warning("Service container already initialized — ignoring duplicate")
        return
    _container = container
    initialized = [k for k, v in vars(container).items() if v is not None and k != "extra"] + list(
        container.extra.keys()
    )
    logger.info("Service container initialized with: %s", initialized)


def reset_container() -> None:
    """Reset the service container. FOR TESTING ONLY.

    This bypasses the idempotent guard in set_container to allow
    tests to isolate their service state. Never call in production.
    """
    global _container
    _container = None


# ── FastAPI Dependencies ─────────────────────────────────────────────────────


def get_datalake_gateway() -> Any:
    """Get DataLakeGateway instance for historical data queries."""
    return get_container().datalake_gateway


def get_view_manager() -> Any:
    """Get ViewManager instance for DuckDB analytics queries."""
    return get_container().view_manager


def get_data_catalog() -> Any:
    """Get DataCatalog instance for symbol metadata."""
    return get_container().data_catalog


def get_event_bus() -> Any:
    """Get EventBus instance for real-time events."""
    return get_container().event_bus


def get_trading_context() -> Any:
    """Get the TradingContext. Raises 503 if not initialized."""
    ctx = get_container().trading_context
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


def get_order_manager() -> Any:
    """Get OrderManager from TradingContext.

    Raises 503 if TradingContext or OrderManager is not available.
    """
    container = get_container()

    # Check direct registration first (higher priority)
    if container.order_manager is not None:
        return container.order_manager

    # Fall back to TradingContext
    ctx = container.trading_context
    if ctx is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "TradingContext not initialized. OrderManager is unavailable. "
                "To enable order management, provide event_bus or trading_context "
                "when creating the FastAPI app."
            ),
        )

    return ctx.order_manager


def get_position_manager() -> Any:
    """Get PositionManager from TradingContext.

    Raises 503 if TradingContext or PositionManager is not available.
    """
    container = get_container()

    # Check direct registration first (higher priority)
    if container.position_manager is not None:
        return container.position_manager

    # Fall back to TradingContext
    ctx = container.trading_context
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


def get_risk_manager() -> Any:
    """Get RiskManager from TradingContext.

    Raises 503 if TradingContext or RiskManager is not available.
    """
    container = get_container()

    # Check direct registration first (higher priority)
    if container.risk_manager is not None:
        return container.risk_manager

    # Fall back to TradingContext
    ctx = container.trading_context
    if ctx is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "TradingContext not initialized. RiskManager is unavailable. "
                "To enable risk management, provide event_bus or trading_context "
                "when creating the FastAPI app."
            ),
        )

    return ctx.risk_manager


def get_order_repository() -> Any:
    """Get OrderRepository adapter backed by OrderManager."""
    from application.oms.order_repository_adapter import OrderManagerRepository

    return OrderManagerRepository(get_order_manager())


def get_position_repository() -> Any:
    """Get PositionRepository adapter backed by PositionManager."""
    from application.oms.position_repository_adapter import PositionManagerRepository

    return PositionManagerRepository(get_position_manager())


def get_broker_service() -> Any:
    """Get BrokerService instance for live broker connections."""
    return get_container().broker_service


def get_market_data_composer() -> Any:
    """Get MarketDataComposer for unified multi-broker historical/streaming data.

    Raises 503 if not initialized.
    """
    composer = get_container().market_data_composer
    if composer is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "MarketDataComposer not initialized. Multi-broker market data unavailable. "
                "Initialize composers via application.composer.factory.create_composers()."
            ),
        )
    return composer


def get_execution_composer() -> Any:
    """Get ExecutionComposer for unified multi-broker order execution.

    Raises 503 if not initialized.
    """
    composer = get_container().execution_composer
    if composer is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "ExecutionComposer not initialized. Multi-broker order execution unavailable. "
                "Initialize composers via application.composer.factory.create_composers()."
            ),
        )
    return composer


def require_live_broker() -> Any:
    """Return the active broker gateway or raise 503 when unavailable."""
    from brokers.common.connection.errors import BrokerNotReadyError

    svc = get_broker_service()
    if svc is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Live broker not configured",
            headers={"Retry-After": "30"},
        )
    try:
        return svc.active_broker
    except BrokerNotReadyError as exc:
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


def get_trade_journal() -> Any:
    """Get TradeJournal for historical P&L queries."""
    from datalake.journal import TradeJournal

    return TradeJournal(read_only=True)


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
    """Initialize all services and create the immutable container.

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
        risk_manager = getattr(trading_context, "risk_manager", None)

    container = ServiceContainer(
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

    set_container(container)

    # Log initialization status
    missing = container.get_missing_services()
    if missing:
        logger.warning(
            "Services initialized with missing components: %s. Related endpoints will return 503.",
            missing,
        )
    else:
        logger.info("All services initialized successfully")
