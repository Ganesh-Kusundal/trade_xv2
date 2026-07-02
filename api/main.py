"""TradeXV2 FastAPI Application Factory.

Creates and configures the FastAPI application with:
- CORS middleware
- All API routers
- WebSocket handlers
- OpenAPI documentation
- Service dependency injection
- Health/readiness endpoints

Usage:
    from api.main import create_app

    app = create_app()
    # Or with services:
    app = create_app(
        datalake_gateway=gateway,
        view_manager=vm,
        data_catalog=catalog,
    )
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import APIConfig
from api.deps import get_container, initialize_all_services

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup/shutdown events."""
    # Startup
    logger.info("TradeXV2 API server starting...")
    logger.info("OpenAPI docs available at %s%s", app.docs_url or "/docs", "")

    # Start TradingContext lifecycle (reconciliation, DLQ monitor, daily PnL reset)
    from api.ws.bridge import MarketBridge
    from api.ws.market import market_manager
    from infrastructure.lifecycle import LifecycleManager
    from infrastructure.resource_manager import ResourceManager

    resource_manager = ResourceManager()
    lifecycle: LifecycleManager | None = None
    market_bridge: MarketBridge | None = None
    lifecycle_started = False

    try:
        container = get_container()
    except Exception as exc:
        logger.error(
            "Service container not available during startup: %s. "
            "OMS endpoints will return 503 until server fully initializes.",
            exc,
        )
        yield
        await _shutdown_cleanup(market_bridge, lifecycle, lifecycle_started, resource_manager)
        return

    ctx = container.trading_context
    if ctx is None:
        logger.warning(
            "No TradingContext in container — OMS endpoints disabled. "
            "To enable OMS, provide event_bus or trading_context to create_app()."
        )
        yield
        await _shutdown_cleanup(market_bridge, lifecycle, lifecycle_started, resource_manager)
        return

    # Build and start lifecycle
    lifecycle = LifecycleManager()
    try:
        ctx.attach_lifecycle(lifecycle)
        lifecycle.start_all()
        lifecycle_started = True
        logger.info("TradingContext lifecycle started")

        # Register lifecycle manager with resource manager
        resource_manager.register(
            "lifecycle",
            lifecycle,
            lambda: lifecycle.stop_all(),
        )

        # Start MarketBridge for WebSocket market data
        market_bridge = MarketBridge(
            event_bus=ctx.event_bus,
            connection_manager=market_manager,
        )
        await market_bridge.start()
        logger.info("MarketBridge started")

        # Register market bridge with resource manager
        resource_manager.register(
            "market_bridge",
            market_bridge,
            market_bridge.stop,
        )

        # Register trading context for cleanup
        resource_manager.register(
            "trading_context",
            ctx,
            None,  # No explicit cleanup needed; lifecycle handles it
        )
    except Exception as exc:
        logger.exception(
            "TradingContext lifecycle setup failed: %s: %s. "
            "OMS may be partially functional. Check logs for details.",
            type(exc).__name__,
            exc,
        )
        # Don't yield yet — let the server start with degraded OMS

    yield

    # Shutdown via resource manager
    await _shutdown_cleanup(market_bridge, lifecycle, lifecycle_started, resource_manager)

    from datalake.core.duckdb_utils import close_all_connections

    close_all_connections()
    logger.info("TradeXV2 API server shutting down...")


async def _shutdown_cleanup(
    market_bridge: Any | None,
    lifecycle: Any | None,
    lifecycle_started: bool,
    resource_manager: Any | None = None,
) -> None:
    """Clean shutdown of MarketBridge and LifecycleManager.

    Parameters
    ----------
    market_bridge:
        MarketBridge instance to stop (async).
    lifecycle:
        LifecycleManager instance to stop (sync).
    lifecycle_started:
        True if lifecycle.start_all() was called successfully.
    resource_manager:
        ResourceManager to perform reverse-order cleanup. If provided,
        it handles the shutdown of all registered resources.
    """
    # Use resource manager for coordinated shutdown if available
    if resource_manager is not None:
        try:
            await resource_manager.shutdown_all()
            logger.info("Resource manager shutdown completed")
        except Exception as exc:
            logger.warning("Resource manager shutdown failed: %s", exc)
        return

    # Fallback: manual cleanup (backward compat)
    # Stop async MarketBridge
    if market_bridge:
        try:
            await market_bridge.stop()
            logger.info("MarketBridge stopped")
        except Exception as exc:
            logger.warning("MarketBridge shutdown failed: %s", exc)

    # Stop sync lifecycle services
    if lifecycle_started and lifecycle:
        try:
            lifecycle.stop_all()
            logger.info("TradingContext lifecycle stopped")
        except Exception as exc:
            logger.warning("Lifecycle shutdown failed: %s", exc)
    elif lifecycle and not lifecycle_started:
        logger.debug("Lifecycle was not started, skipping stop")


def create_app(
    config: APIConfig | None = None,
    datalake_gateway: Any = None,
    view_manager: Any = None,
    data_catalog: Any = None,
    event_bus: Any = None,
    broker_service: Any = None,
    trading_context: Any = None,
    market_data_composer: Any = None,
    execution_composer: Any = None,
    **additional_services: Any,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Parameters
    ----------
    config:
        API configuration. Uses defaults if not provided.
    datalake_gateway:
        DataLakeGateway instance for historical data.
    view_manager:
        ViewManager instance for DuckDB analytics.
    data_catalog:
        DataCatalog instance for symbol metadata.
    event_bus:
        EventBus instance for real-time events.
    broker_service:
        BrokerService instance for live broker connections.
    trading_context:
        TradingContext instance for OMS orchestration.
    market_data_composer:
        MarketDataComposer instance for unified multi-broker historical/streaming data.
    execution_composer:
        ExecutionComposer instance for multi-broker order routing and execution.
    **additional_services:
        Additional services to register in DI container.

    Returns
    -------
    Configured FastAPI application instance.
    """
    from runtime.production_config import validate_production_config

    validate_production_config(surface="api")

    cfg = config or APIConfig()

    from api.auth import configure as _configure_auth

    _configure_auth(auth_mode=cfg.auth_mode, api_key=cfg.api_key)

    # Initialise OpenTelemetry distributed tracing
    from infrastructure.observability.opentelemetry_setup import setup_telemetry

    setup_telemetry(
        service_name="tradex-api",
        otlp_endpoint=None,  # set via env/config when deploying
    )

    # Auto-build TradingContext if not provided but event_bus is available
    if trading_context is None and event_bus is not None:
        from api.lifecycle import build_trading_context

        try:
            trading_context = build_trading_context(event_bus=event_bus)
        except Exception as exc:
            logger.warning(
                "TradingContext creation failed: %s. OMS will be unavailable.",
                exc,
            )
            trading_context = None

    # Register domain runtime hooks for analytics engines
    from application.execution.factory import create_oms_backtest_adapter
    from application.oms.factory import create_trading_context
    from domain.runtime_hooks import (
        register_domain_event_factory,
        register_oms_backtest_factory,
        register_trading_context_factory,
    )
    from infrastructure.event_bus.factory import create_domain_event

    register_oms_backtest_factory(create_oms_backtest_adapter)
    register_domain_event_factory(create_domain_event)
    register_trading_context_factory(create_trading_context)

    # Initialize services (now includes TradingContext and Composers)
    initialize_all_services(
        datalake_gateway=datalake_gateway,
        view_manager=view_manager,
        data_catalog=data_catalog,
        event_bus=event_bus,
        broker_service=broker_service,
        trading_context=trading_context,
        market_data_composer=market_data_composer,
        execution_composer=execution_composer,
        **additional_services,
    )

    # Create FastAPI app
    app = FastAPI(
        title="TradeXV2 API",
        description="Quantitative Trading Platform API - Market Data, Analytics, Scanner, Strategy, Replay, Backtesting",
        version="1.0.0",
        docs_url=cfg.docs_url,
        redoc_url=cfg.redoc_url,
        openapi_url=cfg.openapi_url,
        lifespan=lifespan,
        # OpenAPI configuration
        openapi_tags=[
            {"name": "Health", "description": "Health and readiness probes"},
            {"name": "Symbols", "description": "Symbol search and metadata"},
            {"name": "Market Data", "description": "Historical and live market data"},
            {"name": "Analytics", "description": "Technical indicators and analytics"},
            {"name": "Scanner", "description": "Scanner results and candidates"},
            {"name": "Strategy", "description": "Strategy signals and candidates"},
            {"name": "Options", "description": "Options analytics (PCR, Max Pain, IV)"},
            {"name": "Replay", "description": "Historical replay sessions"},
            {"name": "Backtest", "description": "Backtest execution and results"},
            {"name": "Portfolio", "description": "Positions and PnL"},
            {"name": "Orders", "description": "Order management"},
            {
                "name": "Live Broker",
                "description": "Live broker-backed reads and extended features",
            },
        ],
    )

    # Request logging + correlation ID middleware
    from api.middleware import RateLimitMiddleware, RequestLoggingMiddleware

    app.add_middleware(RequestLoggingMiddleware)

    # Rate limiting middleware (disabled when rate_limit_per_minute == 0)
    if cfg.rate_limit_per_minute > 0:
        app.add_middleware(
            RateLimitMiddleware,
            max_requests=cfg.rate_limit_per_minute,
            window_seconds=60.0,
        )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origins,
        allow_credentials=cfg.cors_allow_credentials,
        allow_methods=cfg.cors_allow_methods,
        allow_headers=cfg.cors_allow_headers,
    )

    # Global exception handler
    from infrastructure.global_exception_handler import setup_exception_handlers

    setup_exception_handlers(app)

    # Attach OpenTelemetry auto-instrumentation to this app instance
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        if FastAPIInstrumentor is not None:
            FastAPIInstrumentor.instrument_app(app)
    except ImportError:
        pass

    # ── Register Routers (imported lazily to avoid circular dependencies) ──

    # Health endpoints
    from api.routers.health import router as health_router

    app.include_router(health_router, prefix=f"{cfg.api_prefix}/health", tags=["Health"])

    # Symbol endpoints
    from api.routers.symbols import router as symbols_router

    app.include_router(symbols_router, prefix=f"{cfg.api_prefix}/symbols", tags=["Symbols"])

    # Market data endpoints
    from api.routers.market import router as market_router

    app.include_router(market_router, prefix=f"{cfg.api_prefix}/market", tags=["Market Data"])

    # Analytics endpoints
    from api.routers.analytics import router as analytics_router

    app.include_router(analytics_router, prefix=f"{cfg.api_prefix}/analytics", tags=["Analytics"])

    # Scanner endpoints
    from api.routers.scanner import router as scanner_router

    app.include_router(scanner_router, prefix=f"{cfg.api_prefix}/scanner", tags=["Scanner"])

    # Strategy endpoints
    from api.routers.strategy import router as strategy_router

    app.include_router(strategy_router, prefix=f"{cfg.api_prefix}/strategy", tags=["Strategy"])

    # Options endpoints
    from api.routers.options import router as options_router

    app.include_router(options_router, prefix=f"{cfg.api_prefix}/options", tags=["Options"])

    # Replay endpoints
    from api.routers.replay import router as replay_router

    app.include_router(replay_router, prefix=f"{cfg.api_prefix}/replay", tags=["Replay"])

    # Backtest endpoints
    from api.routers.backtest import router as backtest_router

    app.include_router(backtest_router, prefix=f"{cfg.api_prefix}/backtest", tags=["Backtest"])

    # Portfolio endpoints
    from api.routers.portfolio import router as portfolio_router

    app.include_router(portfolio_router, prefix=f"{cfg.api_prefix}/portfolio", tags=["Portfolio"])

    # Orders endpoints
    from api.routers.orders import router as orders_router

    app.include_router(orders_router, prefix=f"{cfg.api_prefix}/orders", tags=["Orders"])

    # Risk endpoints
    from api.routers.risk import router as risk_router

    app.include_router(risk_router, prefix=f"{cfg.api_prefix}/risk", tags=["Risk"])

    # Audit trail endpoints
    from api.routers.audit import router as audit_router

    app.include_router(audit_router, prefix=f"{cfg.api_prefix}/audit", tags=["Audit"])

    # News endpoints
    from api.routers.news import router as news_router

    app.include_router(news_router, prefix=f"{cfg.api_prefix}/news", tags=["News"])

    # Feature flags endpoints
    from api.routers.feature_flags import router as feature_flags_router

    app.include_router(feature_flags_router, prefix=f"{cfg.api_prefix}/flags", tags=["Feature Flags"])

    # Live broker endpoints (dual API — explicit live_broker provenance)
    from api.routers.live.router import router as live_router

    app.include_router(live_router, prefix=f"{cfg.api_prefix}/live", tags=["Live Broker"])

    # WebSocket endpoints (mounted separately)
    from api.ws.market import router as ws_market_router

    app.include_router(ws_market_router, prefix="/ws", tags=["WebSocket - Market"])

    from api.ws.replay import router as ws_replay_router

    app.include_router(ws_replay_router, prefix="/ws", tags=["WebSocket - Replay"])

    logger.info("TradeXV2 API app created with %d routers", len(app.routes))

    return app
