"""Shared configuration for Upstox live integration tests.

Provides centralized skip guards, gateway fixtures, and markers for all
Upstox integration tests. Tests should import ``skip_live`` and use the
``gateway`` fixture from this conftest.

Usage::

    from brokers.upstox.tests.integration.conftest import skip_live

    @skip_live
    class TestMyFeature:
        def test_something(self, gateway):
            result = gateway.ltp("RELIANCE", "NSE")
            assert result > 0
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

_INTEGRATION_DIR = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Environment loading
# ---------------------------------------------------------------------------
ENV_PATH = Path(__file__).resolve().parent.parent.parent.parent.parent / ".env.upstox"
_live_env_loaded = False
if ENV_PATH.exists() and ENV_PATH.stat().st_size > 0:
    from dotenv import load_dotenv

    load_dotenv(ENV_PATH, override=True)
    _live_env_loaded = bool(
        os.environ.get("UPSTOX_API_KEY") and os.environ.get("UPSTOX_ACCESS_TOKEN")
    )


# ---------------------------------------------------------------------------
# Skip guard — credentials, token expiry, market hours
# ---------------------------------------------------------------------------
def _should_skip_live() -> bool:
    """Determine if live tests should be skipped.

    Returns True if:
    - .env.upstox is missing or empty
    - UPSTOX_INTEGRATION env var is not set to "1"
    - Access token is expired (JWT exp claim)
    - Market is closed (NSE trading hours)
    """
    if not _live_env_loaded:
        return True
    if os.environ.get("UPSTOX_INTEGRATION") != "1":
        return True
    token = os.environ.get("UPSTOX_ACCESS_TOKEN", "")
    try:
        from brokers.common.auth.jwt_expiry import JwtExpiry

        exp_ms = JwtExpiry.parse_expiry_epoch_ms(token)
        if exp_ms > 0 and exp_ms < time.time() * 1000:
            return True
    except Exception:
        pass
    try:
        from tests.market_hours import is_market_open

        return not is_market_open()
    except Exception:
        # If market_hours is unavailable, run tests
        return False


skip_live = pytest.mark.skipif(
    _should_skip_live(),
    reason="Live API tests require UPSTOX_INTEGRATION=1, .env.upstox credentials, valid token, and open market hours",
)


# ---------------------------------------------------------------------------
# Session-scoped gateway fixture
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def gateway():
    """Session-scoped live gateway — instruments loaded ONCE for all test files.

    This fixture creates a single UpstoxBrokerGateway instance that is shared
    across all test files in the session. Instruments are loaded once, saving
    ~45 seconds compared to per-file fixtures.

    Yields:
        UpstoxBrokerGateway: Live gateway with instruments loaded
    """
    from brokers.upstox.factory import UpstoxBrokerFactory

    gw = UpstoxBrokerFactory().create(env_path=ENV_PATH, load_instruments=True)
    yield gw
    gw.close()


# ---------------------------------------------------------------------------
# Pytest markers
# ---------------------------------------------------------------------------
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Auto-apply integration and sandbox markers to all tests in this directory."""
    for item in items:
        if _INTEGRATION_DIR not in Path(str(item.fspath)).resolve().parents:
            continue
        item.add_marker(pytest.mark.integration)
        item.add_marker(pytest.mark.sandbox)
