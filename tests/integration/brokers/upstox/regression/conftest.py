"""Fixtures for the Upstox regression test package."""

from __future__ import annotations

import contextlib
import os
from pathlib import Path

import pytest

from brokers.upstox.wire import UpstoxBrokerGateway
from infrastructure.gateway.factory import bootstrap_gateway

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
ENV_PATH = _PROJECT_ROOT / ".env.upstox"

_live_env_loaded = False
if ENV_PATH.exists() and ENV_PATH.stat().st_size > 0:
    try:
        from dotenv import load_dotenv

        load_dotenv(ENV_PATH, override=True)
        client_id = (
            os.environ.get("UPSTOX_CLIENT_ID", "").strip()
            or os.environ.get("UPSTOX_API_KEY", "").strip()
        )
        _live_env_loaded = bool(client_id)
    except ImportError:
        pass


@pytest.fixture(scope="session")
def live_gateway() -> UpstoxBrokerGateway:
    """Session-scoped live UpstoxBrokerGateway for regression tests."""
    if not _live_env_loaded:
        pytest.skip(".env.upstox with UPSTOX_CLIENT_ID required for Upstox regression tests")

    result = bootstrap_gateway(
        "upstox",
        env_path=ENV_PATH,
        load_instruments=True,
        require_authenticated=True,
    )
    if not result.live_ready or result.gateway is None:
        pytest.skip(f"Upstox bootstrap failed: {result.error or result.status.value}")
    gw = result.gateway
    yield gw
    with contextlib.suppress(Exception):
        gw.close()
