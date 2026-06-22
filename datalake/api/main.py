"""TradeXV2 FastAPI Application Factory.

Creates and configures the FastAPI application with:
- CORS middleware
- All API routers
- WebSocket handlers
- OpenAPI documentation
- Service dependency injection
- Health/readiness endpoints

Usage:
    from datalake.api.main import create_app
    
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

from datalake.api.config import APIConfig
from datalake.api.deps import initialize_all_services, set_trading_context, get_trading_context

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup/shutdown events."""
    # Startup
    logger.info("TradeXV2 API server starting...")
    logger.info("OpenAPI docs available at %s%s", app.docs_url or "/docs", "")
    
    # Start TradingContext lifecycle (reconciliation, DLQ monitor, daily PnL reset)
    from brokers.common.lifecycle import LifecycleManager
    from datalake.api.ws.market import market_manager
    from datalake.api.ws.bridge import MarketBridge
    
    lifecycle = LifecycleManager()
    market_bridge = None
    try:
        ctx = get_trading_context()
        ctx.attach_lifecycle(lifecycle)
        lifecycle.start_all()
        logger.info("TradingContext lifecycle started")
        
        # Start MarketBridge for WebSocket market data
        market_bridge = MarketBridge(
            event_bus=ctx.event_bus,
            connection_manager=market_manager,
        )
        await market_bridge.start()
        logger.info("MarketBridge started")
    except HTTPException:
        logger.warning("No TradingContext available — OMS endpoints disabled")
    
    yield
    
    # Shutdown
    try:
        if market_bridge:
            await market_bridge.stop()
            logger.info("MarketBridge stopped")
        lifecycle.stop_all()
        logger.info("TradingContext lifecycle stopped")
    except Exception:
        pass  # Lifecycle may not be started if no TradingContext
    
    from datalake.duckdb_utils import close_all_connections
    close_all_connections()
    logger.info("TradeXV2 API server shutting down...")


def create_app(
    config: APIConfig | None = None,
    datalake_gateway: Any = None,
    view_manager: Any = None,
    data_catalog: Any = None,
    event_bus: Any = None,
    broker_service: Any = None,
    trading_context: Any = None,
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
    **additional_services:
        Additional services to register in DI container.
    
    Returns
    -------
    Configured FastAPI application instance.
    """
    cfg = config or APIConfig()
    
    # Auto-build TradingContext if not provided but event_bus is available
    if trading_context is None and event_bus is not None:
        from datalake.api.lifecycle import build_trading_context
        trading_context = build_trading_context(event_bus=event_bus)
    
    # Initialize services (now includes TradingContext)
    initialize_all_services(
        datalake_gateway=datalake_gateway,
        view_manager=view_manager,
        data_catalog=data_catalog,
        event_bus=event_bus,
        broker_service=broker_service,
        trading_context=trading_context,
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
        ],
    )
    
    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origins,
        allow_credentials=cfg.cors_allow_credentials,
        allow_methods=cfg.cors_allow_methods,
        allow_headers=cfg.cors_allow_headers,
    )
    
    # ── Register Routers (imported lazily to avoid circular dependencies) ──
    
    # Health endpoints
    from datalake.api.routers.health import router as health_router
    app.include_router(health_router, prefix=f"{cfg.api_prefix}/health", tags=["Health"])
    
    # Symbol endpoints
    from datalake.api.routers.symbols import router as symbols_router
    app.include_router(symbols_router, prefix=f"{cfg.api_prefix}/symbols", tags=["Symbols"])
    
    # Market data endpoints
    from datalake.api.routers.market import router as market_router
    app.include_router(market_router, prefix=f"{cfg.api_prefix}/market", tags=["Market Data"])
    
    # Analytics endpoints
    from datalake.api.routers.analytics import router as analytics_router
    app.include_router(analytics_router, prefix=f"{cfg.api_prefix}/analytics", tags=["Analytics"])
    
    # Scanner endpoints
    from datalake.api.routers.scanner import router as scanner_router
    app.include_router(scanner_router, prefix=f"{cfg.api_prefix}/scanner", tags=["Scanner"])
    
    # Strategy endpoints
    from datalake.api.routers.strategy import router as strategy_router
    app.include_router(strategy_router, prefix=f"{cfg.api_prefix}/strategy", tags=["Strategy"])
    
    # Options endpoints
    from datalake.api.routers.options import router as options_router
    app.include_router(options_router, prefix=f"{cfg.api_prefix}/options", tags=["Options"])
    
    # Replay endpoints
    from datalake.api.routers.replay import router as replay_router
    app.include_router(replay_router, prefix=f"{cfg.api_prefix}/replay", tags=["Replay"])
    
    # Backtest endpoints
    from datalake.api.routers.backtest import router as backtest_router
    app.include_router(backtest_router, prefix=f"{cfg.api_prefix}/backtest", tags=["Backtest"])
    
    # Portfolio endpoints
    from datalake.api.routers.portfolio import router as portfolio_router
    app.include_router(portfolio_router, prefix=f"{cfg.api_prefix}/portfolio", tags=["Portfolio"])
    
    # Orders endpoints
    from datalake.api.routers.orders import router as orders_router
    app.include_router(orders_router, prefix=f"{cfg.api_prefix}/orders", tags=["Orders"])
    
    # Risk endpoints
    from datalake.api.routers.risk import router as risk_router
    app.include_router(risk_router, prefix=f"{cfg.api_prefix}/risk", tags=["Risk"])
    
    # WebSocket endpoints (mounted separately)
    from datalake.api.ws.market import router as ws_market_router
    app.include_router(ws_market_router, prefix="/ws", tags=["WebSocket - Market"])
    
    from datalake.api.ws.replay import router as ws_replay_router
    app.include_router(ws_replay_router, prefix="/ws", tags=["WebSocket - Replay"])
    
    logger.info("TradeXV2 API app created with prefix: %s", cfg.api_prefix)
    
    return app
