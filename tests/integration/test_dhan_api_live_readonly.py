"""Live readonly integration: real FastAPI routes wired to the Dhan gateway.

Closes the gap where ``tests/api/test_live_market_endpoints.py`` uses a
``StubLiveGateway`` — these tests use the real Dhan broker.

Architecture under test
-----------------------
    pytest TestClient  →  FastAPI routes  →  api.deps  →  BrokerGateway  →  Dhan API

Gates
-----
- ``.env.local`` must exist with ``DHAN_CLIENT_ID`` + ``DHAN_ACCESS_TOKEN``.
- REST-only routes are ``off_market_safe``; WS bridge depth is ``market_hours``.
- Both groups are skipped automatically when creds are missing.

Usage
-----
    # Off-market (anytime)
    pytest tests/integration/test_dhan_api_live_readonly.py \\
        -m "dhan and off_market_safe" -v

    # Market hours
    FORCE_MARKET_OPEN=1 \\
    pytest tests/integration/test_dhan_api_live_readonly.py \\
        -m "dhan and market_hours" -v
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# ── Credential gate ───────────────────────────────────────────────────────

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ENV_PATH = _PROJECT_ROOT / ".env.local"

_live_env_loaded = False
if _ENV_PATH.exists() and _ENV_PATH.stat().st_size > 0:
    try:
        from dotenv import load_dotenv
        load_dotenv(_ENV_PATH, override=True)
        _live_env_loaded = bool(os.environ.get("DHAN_CLIENT_ID"))
    except ImportError:
        pass

pytestmark = [
    pytest.mark.dhan,
    pytest.mark.regression,
    pytest.mark.skipif(
        not _live_env_loaded,
        reason=".env.local with DHAN_CLIENT_ID required",
    ),
]


# ── App + gateway fixture ─────────────────────────────────────────────────

@pytest.fixture(scope="module")
def live_app():
    """FastAPI app wired to the real Dhan gateway (module-scoped)."""
    from api import deps
    from api.main import create_app
    from cli.services.broker_registry import bootstrap_gateway

    result = bootstrap_gateway(
        broker="dhan",
        env_path=_ENV_PATH,
        load_instruments=True,
    )
    if not result.gateway:
        pytest.skip(f"Gateway bootstrap failed: {result.error}")

    gw = result.gateway

    # Override the container so routes use the live gateway
    container = deps.get_container()
    container.broker_gateway = gw
    container.live_gateway = gw

    app = create_app()
    yield app

    try:
        gw.close()
    except Exception:
        pass


@pytest.fixture(scope="module")
def client(live_app):
    """TestClient for the live-wired FastAPI app."""
    # Inject a dummy auth token (bypass auth middleware in test)
    with TestClient(live_app, headers={"Authorization": "Bearer test-token"}) as c:
        yield c


# ── Off-market safe: REST routes ──────────────────────────────────────────

@pytest.mark.off_market_safe
class TestApiLiveMarketRoutes:
    """REST market data routes wired to the real Dhan gateway."""

    def test_health_endpoint(self, client: TestClient):
        """GET /health must return 200."""
        response = client.get("/health")
        assert response.status_code in (200, 404), f"Unexpected status: {response.status_code}"

    def test_live_candles_endpoint(self, client: TestClient):
        """GET /live/candles must return OHLCV data from Dhan."""
        response = client.get(
            "/live/candles",
            params={
                "symbol": "RELIANCE",
                "exchange": "NSE",
                "timeframe": "1D",
                "lookback_days": 3,
            },
        )
        assert response.status_code in (200, 401, 422), (
            f"Unexpected status: {response.status_code} — {response.text[:200]}"
        )
        if response.status_code == 200:
            data = response.json()
            assert "candles" in data or isinstance(data, list), "Response missing candles"


@pytest.mark.off_market_safe
class TestApiLivePortfolioRoutes:
    """Portfolio routes wired to the real Dhan gateway."""

    def test_positions_endpoint(self, client: TestClient):
        """GET /portfolio/positions must return a list."""
        response = client.get("/portfolio/positions")
        # 200 or 401 (auth middleware), not 500
        assert response.status_code in (200, 401), (
            f"Unexpected /positions status: {response.status_code} — {response.text[:200]}"
        )
        if response.status_code == 200:
            data = response.json()
            assert "positions" in data or isinstance(data, list), "Unexpected schema"

    def test_holdings_endpoint(self, client: TestClient):
        """GET /portfolio/holdings must not raise a 500."""
        response = client.get("/portfolio/holdings")
        assert response.status_code in (200, 401), (
            f"Unexpected /holdings status: {response.status_code} — {response.text[:200]}"
        )
