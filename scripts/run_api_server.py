"""TradeXV2 API Server Launcher."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
# Library packages live under src/ (single package root).
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root))

from interface.api.config import APIConfig
from interface.api.main import create_app
from infrastructure.auth.environment_bootstrap import bootstrap_environment
from infrastructure.logging_config import configure_logging
from interface.api.bootstrap import initialize_api_services
from runtime.interface_compose import wire_interface_compose

wire_interface_compose()

logger = logging.getLogger(__name__)


def create_api_app():
    """Create API app with all services initialized via runtime bootstrap."""
    import os

    configure_logging()
    project_root = Path(__file__).parent.parent
    bootstrap_environment(project_root)
    services = initialize_api_services(project_root)

    # Honor AUTH_MODE from env (local SPA: AUTH_MODE=none TRADEX_ALLOW_AUTH_NONE=1).
    auth_mode = (os.getenv("AUTH_MODE") or "api_key").strip().lower()
    config = APIConfig(
        host="127.0.0.1",
        port=8080,
        auth_mode=auth_mode,
        api_key=os.getenv("API_KEY", ""),
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
    uvicorn.run(app, host="127.0.0.1", port=8080)
