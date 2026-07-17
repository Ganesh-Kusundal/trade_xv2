"""Dependency injection for API routers.

Provides FastAPI dependencies for:
- TradingContext (OMS container)
- DataLakeGateway (historical data)
- ViewManager (DuckDB analytics views)
- DataCatalog (symbol metadata)
- EventBus (real-time events)
- BrokerService (live broker connections)

All services are stored in the infrastructure DI container (infrastructure.di.container)
as the single source of truth. This module provides typed FastAPI Depends() wrappers
that resolve from that container.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any

from fastapi import HTTPException, status

from domain.ports.event_publisher import EventBusPort
from domain.ports.market_data import MarketDataPort
from domain.ports.order_service import OrderServicePort
from domain.ports.risk_manager import RiskManagerPort
from infrastructure.di import container as di_container

logger = logging.getLogger(__name__)

# Module-level typed wrapper — set once during startup, provides attribute access
_container: SimpleNamespace | None = None


def get_container() -> SimpleNamespace:
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


def set_container(services: SimpleNamespace | dict[str, Any]) -> None:
    """Set services and register them in the DI container. Idempotent."""
    global _container  # intentional module singleton — DI container
    if _container is not None:
        logger.warning("Service container already initialized — ignoring duplicate")
        return

    ns = SimpleNamespace(**services) if isinstance(services, dict) else services

    _container = ns

    # Register all services in the DI container (single source of truth)
    # Even None services are registered so resolve() doesn't raise;
    # get_* functions handle None values with 503 responses.
    for name in vars(ns):
        if name.startswith("_"):
            continue
        value = getattr(ns, name)
        if isinstance(value, dict):
            for k, v in value.items():
                di_container.register_instance(k, v)
        else:
            di_container.register_instance(name, value)

    initialized = [k for k in vars(ns) if not k.startswith("_") and getattr(ns, k) is not None]
    logger.info("Service container initialized with: %s", initialized)


def reset_container() -> None:
    """Reset the service container. FOR TESTING ONLY.

    This bypasses the idempotent guard in set_container to allow
    tests to isolate their service state. Never call in production.
    """
    global _container, _trade_journal_instance  # intentional module singleton — test reset only
    _container = None
    _trade_journal_instance = None
    di_container.reset()


# ── FastAPI Dependencies ─────────────────────────────────────────────────────


def get_datalake_gateway() -> Any:
    """Get DataLakeGateway instance for historical data queries."""
    return di_container.resolve("datalake_gateway")


def get_view_manager() -> Any:
    """Get ViewManager instance for DuckDB analytics queries."""
    return di_container.resolve("view_manager")


def get_data_catalog() -> Any:
    """Get DataCatalog instance for symbol metadata."""
    return di_container.resolve("data_catalog")


def get_event_bus() -> EventBusPort:
    """Get EventBus instance for real-time events."""
    return di_container.resolve("event_bus")  # type: ignore[no-any-return]


def get_trading_context() -> Any:
    """Get the TradingContext. Raises 503 if not initialized."""
    ctx = di_container.resolve("trading_context")
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
    om = di_container.resolve("order_manager")
    if om is not None:
        return om  # type: ignore[no-any-return]

    # Fall back to TradingContext
    ctx = di_container.resolve("trading_context")
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
    pm = di_container.resolve("position_manager")
    if pm is not None:
        return pm

    # Fall back to TradingContext
    ctx = di_container.resolve("trading_context")
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
    rm = di_container.resolve("risk_manager")
    if rm is not None:
        return rm  # type: ignore[no-any-return]

    # Fall back to TradingContext
    ctx = di_container.resolve("trading_context")
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
    return di_container.resolve("broker_service")


def get_market_data_composer() -> MarketDataPort:
    """Get MarketDataComposer for unified multi-broker historical/streaming data.

    Raises 503 if not initialized.
    """
    composer = di_container.resolve("market_data_composer")
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
    composer = di_container.resolve("execution_composer")
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
    svc = get_broker_service()
    if svc is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Live broker not configured",
            headers={"Retry-After": "30"},
        )
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

    from infrastructure.providers.null.stubs import (
        NullBrokerService,
        NullDataCatalog,
        NullDataLakeGateway,
        NullEventBus,
        NullExecutionComposer,
        NullMarketDataComposer,
        NullOrderManager,
        NullPositionManager,
        NullRiskManager,
        NullViewManager,
    )

    services = SimpleNamespace(
        datalake_gateway=datalake_gateway or NullDataLakeGateway(),
        view_manager=view_manager or NullViewManager(),
        data_catalog=data_catalog or NullDataCatalog(),
        event_bus=event_bus or NullEventBus(),
        broker_service=broker_service or NullBrokerService(),
        trading_context=trading_context,
        order_manager=order_manager or NullOrderManager(),
        position_manager=position_manager or NullPositionManager(),
        risk_manager=risk_manager or NullRiskManager(),
        market_data_composer=market_data_composer or NullMarketDataComposer(),
        execution_composer=execution_composer or NullExecutionComposer(),
        extra=additional_services,
    )

    set_container(services)

    # Log initialization status
    all_named = [
        "datalake_gateway", "view_manager", "data_catalog",
        "event_bus", "broker_service", "trading_context",
        "order_manager", "position_manager", "risk_manager",
        "market_data_composer", "execution_composer",
    ]
    missing = [n for n in all_named if getattr(services, n) is None]
    if missing:
        logger.warning(
            "Services initialized with missing components: %s. Related endpoints will return 503.",
            missing,
        )
    else:
        logger.info("All services initialized (with NullProviders for missing components)")
