#!/usr/bin/env python3
"""Generate web/openapi.json from the FastAPI app without live broker bootstrap.

Uses the same lightweight BrokerService factory as API bootstrap wiring tests
(``tests/integration/api/test_api_bootstrap_wiring.py``) so CI and local runs
never touch ``.env.local`` or open live websocket connections.

Usage:
    python -m scripts.generate_openapi
    python -m scripts.generate_openapi --output /tmp/openapi.json
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = ROOT / "web" / "openapi.json"


def _setup_import_paths() -> None:
    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(ROOT))


def _lightweight_broker_service_factory():
    """BrokerService with TradingContext + seeded mock gateway — no network I/O."""

    def factory(*, event_bus=None):
        from domain.enums import BrokerId
        from interface.ui.services.broker_registry import create_seeded_mock_broker
        from interface.ui.services.broker_service import BrokerService
        from tests.conftest import build_test_trading_context

        ctx = build_test_trading_context(event_bus=event_bus)
        bs = BrokerService(event_bus=ctx.event_bus)
        bs._initialized = True
        bs._trading_context = ctx
        bs._gateway = create_seeded_mock_broker(BrokerId.DHAN)
        bs._active_name = BrokerId.DHAN
        bs._live_actionable = True
        bs._paper = None
        bs._mock = None
        return bs

    return factory


def build_openapi_app():
    """Build a fully wired FastAPI app suitable for schema export."""
    from interface.api.bootstrap import initialize_api_services
    from interface.api.config import APIConfig
    from interface.api.main import create_app

    services = initialize_api_services(
        ROOT,
        wire_orchestrator=False,
        skip_parity_gate=True,
        broker_service_factory=_lightweight_broker_service_factory(),
    )
    config = APIConfig(auth_mode="none")
    return create_app(config=config, **services)


def generate_openapi_schema() -> dict[str, Any]:
    """Return the OpenAPI schema dict for the current API surface."""
    app = build_openapi_app()
    return app.openapi()


def write_openapi_json(output_path: Path) -> dict[str, Any]:
    """Generate and write OpenAPI JSON; return the schema dict."""
    schema = generate_openapi_schema()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(schema, indent=2, sort_keys=True) + "\n"
    output_path.write_text(payload, encoding="utf-8")
    return schema


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    os.environ.pop("RISK_FAIL_OPEN", None)

    parser = argparse.ArgumentParser(description="Generate TradeXV2 OpenAPI schema")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output path (default: {DEFAULT_OUTPUT.relative_to(ROOT)})",
    )
    args = parser.parse_args(argv)

    _setup_import_paths()

    schema = write_openapi_json(args.output.resolve())
    path_count = len(schema.get("paths", {}))
    print(f"Wrote OpenAPI schema ({path_count} paths) to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
