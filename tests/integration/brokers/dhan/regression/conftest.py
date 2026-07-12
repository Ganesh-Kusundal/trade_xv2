"""Fixtures for the Dhan regression test package.

Provides the session-scoped ``live_gateway`` fixture used by
``test_regression_suite.py``, ``test_e2e_smoke.py``, and any future
tests in this directory.

The fixture is intentionally lightweight: it delegates to
``BrokerFactory`` (same as the integration conftest) and auto-skips
when ``.env.local`` is missing.
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path

import pytest

from brokers.dhan.wire import DhanBrokerGateway
from infrastructure.gateway.factory import bootstrap_gateway

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
ENV_PATH = _PROJECT_ROOT / ".env.local"

_live_env_loaded = False
if ENV_PATH.exists() and ENV_PATH.stat().st_size > 0:
    try:
        from dotenv import load_dotenv

        load_dotenv(ENV_PATH, override=True)
        _live_env_loaded = bool(os.environ.get("DHAN_CLIENT_ID"))
    except ImportError:
        pass


@pytest.fixture(scope="session")
def live_gateway() -> DhanBrokerGateway:
    """Session-scoped live DhanBrokerGateway for regression tests.

    Skipped automatically when .env.local is absent or has no DHAN_CLIENT_ID.
    """
    if not _live_env_loaded:
        pytest.skip(
            ".env.local with DHAN_CLIENT_ID required for Dhan regression tests"
        )

    result = bootstrap_gateway(
        "dhan",
        env_path=ENV_PATH,
        load_instruments=True,
        require_authenticated=True,
    )
    if not result.live_ready or result.gateway is None:
        pytest.skip(f"Dhan bootstrap failed: {result.error or result.status.value}")
    gw = result.gateway
    yield gw
    with contextlib.suppress(Exception):
        gw.close()
