"""TradeXV2 API Server Launcher."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from api.config import APIConfig  # noqa: E402
from api.main import create_app  # noqa: E402
from brokers.common.auth.environment_bootstrap import bootstrap_environment  # noqa: E402
from infrastructure.logging_config import configure_logging  # noqa: E402
from runtime.api_bootstrap import initialize_api_services  # noqa: E402

logger = logging.getLogger(__name__)


def create_api_app():
    """Create API app with all services initialized via runtime bootstrap."""
    configure_logging()
    project_root = Path(__file__).parent
    bootstrap_environment(project_root)
    services = initialize_api_services(project_root)

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

    return create_app(config=config, **services)


if __name__ == "__main__":
    import uvicorn

    app = create_api_app()
    uvicorn.run(app, host="127.0.0.1", port=8000)
