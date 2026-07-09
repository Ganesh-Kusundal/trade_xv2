"""Shared test configuration for TradeXV2.

Provides market-hours-aware fixtures and skip logic for live tests.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any

import pytest

from tests.market_hours import is_market_open, now_ist

logger = logging.getLogger(__name__)


@pytest.fixture(scope="session", autouse=True)
def _register_domain_runtime_hooks() -> None:
    """Wire broker factories into domain hooks for analytics engines in tests."""
    from application.execution.factory import create_oms_backtest_adapter
    from application.oms.factory import create_trading_context
    from domain.runtime_hooks import (
        register_domain_event_factory,
        register_oms_backtest_factory,
        register_trading_context_factory,
    )
    from infrastructure.event_bus.factory import create_domain_event

    register_oms_backtest_factory(create_oms_backtest_adapter)
    register_domain_event_factory(create_domain_event)
    register_trading_context_factory(create_trading_context)

    # Ensure broker adapter classes are registered into brokers.common.adapter_factory.
    # Brokers self-register on package import; importing them here guarantees the
    # registry is populated for every test (idempotent).
    import brokers.dhan  # noqa: F401
    import brokers.upstox  # noqa: F401


def is_token_expired(token: str) -> bool:
    """Check if a JWT token is expired.

    Decodes the token without signature verification to check the 'exp' claim.
    Returns True if the token is expired or cannot be decoded.
    Returns False if the token is valid or has no expiry claim.

    Args:
        token: JWT token string

    Returns:
        True if token is expired, False otherwise
    """
    if not token:
        return True

    try:
        # Try to decode JWT payload without signature verification
        parts = token.split(".")
        if len(parts) != 3:
            return True  # Not a valid JWT format

        import base64
        import json

        # Decode payload (second part)
        payload = parts[1]
        # Add padding if needed
        padding = 4 - len(payload) % 4
        if padding != 4:
            payload += "=" * padding

        decoded_bytes = base64.urlsafe_b64decode(payload)
        decoded: dict[str, Any] = json.loads(decoded_bytes)

        exp = decoded.get("exp")
        if exp is None:
            return False  # No expiry claim — let test run

        return time.time() > exp
    except Exception as exc:
        logger.debug("token_decode_failed: %s", exc)
        return False  # Can't decode — let test run and fail naturally


@pytest.fixture(autouse=False)
def market_is_open():
    """Fixture that skips test if market is closed.

    Use in tests that require live market data::

        @pytest.mark.usefixtures("market_is_open")
        def test_websocket_ticks():
            ...
    """
    if not is_market_open():
        now = now_ist()
        pytest.skip(
            f"Market is closed (IST {now.strftime('%H:%M')}, trading hours 09:15-15:30 Mon-Fri)"
        )


@pytest.fixture(autouse=False)
def live_credentials():
    """Fixture that provides Dhan credentials or skips.

    Returns tuple of (client_id, access_token).
    Skips if .env.local is missing, credentials are invalid, or token is expired.
    """
    env_path = Path(".env.local")
    if not env_path.exists():
        pytest.skip(".env.local not found")

    from dotenv import load_dotenv

    load_dotenv(env_path, override=True)

    client_id = os.environ.get("DHAN_CLIENT_ID", "")
    access_token = os.environ.get("DHAN_ACCESS_TOKEN", "")

    if not client_id or not access_token:
        pytest.skip("DHAN_CLIENT_ID or DHAN_ACCESS_TOKEN not set")

    if is_token_expired(access_token):
        pytest.skip("DHAN_ACCESS_TOKEN is expired")

    return client_id, access_token


@pytest.fixture(autouse=False)
def upstox_credentials():
    """Fixture that provides Upstox credentials or skips.

    Returns tuple of (api_key, access_token).
    Skips if .env.upstox is missing, credentials are invalid, or token is expired.
    """
    env_path = Path(".env.upstox")
    if not env_path.exists():
        pytest.skip(".env.upstox not found")

    from dotenv import load_dotenv

    load_dotenv(env_path, override=True)

    api_key = os.environ.get("UPSTOX_API_KEY", "")
    access_token = os.environ.get("UPSTOX_ACCESS_TOKEN", "")

    if not api_key or not access_token:
        pytest.skip("UPSTOX_API_KEY or UPSTOX_ACCESS_TOKEN not set")

    if is_token_expired(access_token):
        pytest.skip("UPSTOX_ACCESS_TOKEN is expired")

    return api_key, access_token


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "market_hours: mark test as requiring open market hours")
    config.addinivalue_line(
        "markers", "live_api: mark test as requiring live API credentials and open market"
    )
    config.addinivalue_line(
        "markers", "sandbox: test requires sandbox environment (write operations)"
    )
    config.addinivalue_line(
        "markers", "live_read: test requires live environment (read-only operations)"
    )
    config.addinivalue_line(
        "markers", "live_write: test requires live environment with order execution enabled"
    )
    config.addinivalue_line(
        "markers", "split_env: test uses split read/write routing (reads live, writes sandbox)"
    )
