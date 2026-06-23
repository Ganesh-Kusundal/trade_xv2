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
from datalake.gateway import DataLakeGateway
from datalake.catalog import DataCatalog
from analytics.views.manager import ViewManager
from runtime.trading_runtime_factory import TradingRuntimeFactory

logger = logging.getLogger(__name__)


def initialize_services():
    """Initialize all TradeXV2 services for the API."""
    logger.info("Initializing TradeXV2 services...")

    datalake_gateway = DataLakeGateway(
        root=str(project_root / "market_data"),
    )

    data_catalog = DataCatalog(
        root=str(project_root / "market_data"),
        read_only=True,
    )

    view_manager = ViewManager(
        catalog_path=project_root / "market_data" / "catalog.duckdb",
        read_only=True,
    )

    logger.info("Building unified trading runtime (single EventBus + BrokerService)...")
    runtime = TradingRuntimeFactory.build_for_api(
        wire_orchestrator=True,
        skip_parity_gate=False,
    )

    trading_context = runtime.trading_context
    event_bus = runtime.event_bus
    if trading_context is not None and event_bus is not trading_context.event_bus:
        logger.warning(
            "Runtime event_bus differs from TradingContext event_bus; using context bus"
        )
        event_bus = trading_context.event_bus

    logger.info("All services initialized successfully")

    return {
        "datalake_gateway": datalake_gateway,
        "data_catalog": data_catalog,
        "view_manager": view_manager,
        "event_bus": event_bus,
        "trading_context": trading_context,
        "broker_service": runtime.broker_service,
    }


def create_api_app():
    """Create API app with all services initialized."""
    services = initialize_services()

    config = APIConfig(
        host="127.0.0.1",
        port=8000,
        cors_origins=[
            "http://localhost:5173",
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

    logging.basicConfig(level=logging.INFO)
    app = create_api_app()
    uvicorn.run(app, host="127.0.0.1", port=8000)
