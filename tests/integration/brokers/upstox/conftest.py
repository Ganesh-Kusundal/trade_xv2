"""Shared configuration for Upstox live integration tests.

Provides centralized skip guards, gateway fixtures, and markers for all
Upstox integration tests. Tests should import ``skip_live`` and use the
``gateway`` fixture from this conftest.

TOTP-first: live tests bootstrap tokens via ``UpstoxBrokerFactory`` when
``UPSTOX_AUTH_MODE=TOTP`` — no pre-pasted ``UPSTOX_ACCESS_TOKEN`` required.
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
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent


def _resolve_upstox_env_path() -> Path:
    from infrastructure.auth.credential_resolver import CredentialResolver

    return CredentialResolver.resolve_upstox_env_path() or _REPO_ROOT / ".env.upstox"


ENV_PATH = _resolve_upstox_env_path()

if ENV_PATH.exists() and ENV_PATH.stat().st_size > 0:
    from dotenv import load_dotenv

    load_dotenv(ENV_PATH, override=True)


def _has_live_credentials() -> bool:
    if not ENV_PATH.exists() or ENV_PATH.stat().st_size == 0:
        return False
    client_id = (
        os.environ.get("UPSTOX_CLIENT_ID", "").strip()
        or os.environ.get("UPSTOX_API_KEY", "").strip()
    )
    if not client_id:
        return False
    auth_mode = os.environ.get("UPSTOX_AUTH_MODE", "STATIC").strip().upper()
    if auth_mode == "TOTP":
        from tests.integration.auth_gates import upstox_totp_gate

        return upstox_totp_gate().configured
    return bool(os.environ.get("UPSTOX_ACCESS_TOKEN", "").strip())


_live_env_loaded = _has_live_credentials()


# ---------------------------------------------------------------------------
# Skip guards
# ---------------------------------------------------------------------------
def _should_skip_live() -> bool:
    """Skip only when credentials/integration flags are missing.

    Token mint/refresh is handled by broker factories (TOTP/401-retry); do not
    pre-check JWT expiry here. Market-hours gating applies only to stream/depth.
    """
    if not _has_live_credentials():
        return True
    if os.environ.get("UPSTOX_INTEGRATION") != "1":
        return True
    env = os.environ.get("UPSTOX_ENVIRONMENT", "LIVE").strip().upper()
    return env not in ("LIVE", "SANDBOX")


def _should_skip_live_market_hours() -> bool:
    if _should_skip_live():
        return True
    if os.environ.get("FORCE_MARKET_OPEN") == "1":
        return False
    try:
        from tests.market_hours import is_market_open

        return not is_market_open()
    except Exception:
        return False


def _should_skip_pre_prod() -> bool:
    if _should_skip_live():
        return True
    return os.environ.get("PRE_PROD_GATE", "0") != "1"


skip_live = pytest.mark.skipif(
    _should_skip_live(),
    reason=(
        "Live API tests require UPSTOX_INTEGRATION=1, .env.upstox or .env.local "
        "credentials (TOTP or access token), UPSTOX_ENVIRONMENT=LIVE|SANDBOX"
    ),
)

skip_live_market_hours = pytest.mark.skipif(
    _should_skip_live_market_hours(),
    reason=(
        "Live stream/depth tests require NSE market hours (09:15–15:30 IST) "
        "or FORCE_MARKET_OPEN=1"
    ),
)

requires_pre_prod = pytest.mark.skipif(
    _should_skip_pre_prod(),
    reason="Pre-prod gate requires PRE_PROD_GATE=1 plus live Upstox credentials",
)


# ---------------------------------------------------------------------------
# Session-scoped gateway fixture
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def gateway():
    """Session-scoped live gateway — TOTP bootstrap runs at connect."""
    from infrastructure.gateway.factory import bootstrap_gateway

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
    gw.close()


@pytest.fixture(scope="session")
def live_gateway(gateway):
    """Alias for ``gateway`` (contract-test compatibility)."""
    return gateway


@pytest.fixture
def ws_teardown(gateway):
    """Disconnect WS streams after each test using the session gateway."""
    yield
    broker = gateway._broker
    from infrastructure.async_compat import run_async_compat

    mux = getattr(broker, "market_data_websocket", None)
    portfolio = getattr(broker, "portfolio_stream", None)
    if mux is not None and getattr(mux, "is_connected", False):
        run_async_compat(mux.disconnect(), fire_and_forget=False)
    if portfolio is not None and getattr(portfolio, "is_connected", False):
        run_async_compat(portfolio.disconnect(), fire_and_forget=False)


# ---------------------------------------------------------------------------
# Pytest markers
# ---------------------------------------------------------------------------
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Auto-apply integration, sandbox, and upstox markers."""
    for item in items:
        if _INTEGRATION_DIR not in Path(str(item.fspath)).resolve().parents:
            continue
        item.add_marker(pytest.mark.integration)
        item.add_marker(pytest.mark.sandbox)
        item.add_marker(pytest.mark.upstox)
