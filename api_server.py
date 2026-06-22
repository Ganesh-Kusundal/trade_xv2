"""TradeXV2 API Server Launcher.

Initializes all TradeXV2 services and starts the FastAPI server.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from datalake.api.main import create_app
from datalake.api.config import APIConfig
from datalake.api.lifecycle import build_trading_context
from datalake.gateway import DataLakeGateway
from datalake.catalog import DataCatalog
from analytics.views.manager import ViewManager
from brokers.common.event_bus import EventBus
from brokers.common.event_bus.factory import AsyncEventBusFactory

logger = logging.getLogger(__name__)


def initialize_services():
    """Initialize all TradeXV2 services for the API."""
    logger.info("Initializing TradeXV2 services...")
    
    # Initialize DataLakeGateway (historical OHLCV from Parquet)
    logger.info("Loading DataLakeGateway...")
    datalake_gateway = DataLakeGateway(
        root=str(project_root / "market_data"),
    )
    
    # Initialize DataCatalog (symbol metadata from DuckDB)
    logger.info("Loading DataCatalog...")
    data_catalog = DataCatalog(
        root=str(project_root / "market_data"),
        read_only=True,
    )
    
    # Initialize ViewManager (analytics views)
    logger.info("Loading ViewManager...")
    view_manager = ViewManager(
        catalog_path=project_root / "market_data" / "catalog.duckdb",
    )
    
    # Initialize EventBus (real-time events)
    # Use AsyncEventBus for API tick path to avoid blocking the event loop
    logger.info("Loading AsyncEventBus (API tick path)...")
    event_bus, is_async = AsyncEventBusFactory.create_from_config(
        force_async=True,  # API server always uses async bus
        maxsize=2000,  # Larger queue for API throughput
    )
    logger.info("EventBus mode: async=%s", is_async)
    
    # Build TradingContext (OMS)
    logger.info("Loading TradingContext (OMS)...")
    trading_context = build_trading_context(event_bus=event_bus)
    
    logger.info("All services initialized successfully")
    
    return {
        "datalake_gateway": datalake_gateway,
        "data_catalog": data_catalog,
        "view_manager": view_manager,
        "event_bus": event_bus,
        "trading_context": trading_context,
    }


def create_api_app():
    """Create API app with all services initialized."""
    services = initialize_services()
    
    config = APIConfig(
        host="127.0.0.1",
        port=8000,
        cors_origins=[
            "http://localhost:5173",  # Vite dev server
            "http://localhost:3000",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:3000",
        ],
    )
    
    app = create_app(
        config=config,
        **services,
    )
    
    return app


if __name__ == "__main__":
    import uvicorn
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    
    logger.info("Starting TradeXV2 API Server...")
    logger.info("Documentation: http://127.0.0.1:8000/docs")
    
    uvicorn.run(
        "api_server:create_api_app",
        factory=True,
        host="127.0.0.1",
        port=8000,
        reload=True,
        log_level="info",
    )
