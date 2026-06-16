"""Shared test configuration for TradeXV2.

Provides market-hours-aware fixtures and skip logic for live tests.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.market_hours import is_market_open, now_ist


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
            f"Market is closed (IST {now.strftime('%H:%M')}, "
            f"trading hours 09:15-15:30 Mon-Fri)"
        )


@pytest.fixture(autouse=False)
def live_credentials():
    """Fixture that provides Dhan credentials or skips.

    Returns tuple of (client_id, access_token).
    Skips if .env.local is missing or credentials are invalid.
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

    return client_id, access_token


@pytest.fixture(autouse=False)
def upstox_credentials():
    """Fixture that provides Upstox credentials or skips.

    Returns tuple of (api_key, access_token).
    Skips if .env.upstox is missing or credentials are invalid.
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

    return api_key, access_token


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "market_hours: mark test as requiring open market hours"
    )
    config.addinivalue_line(
        "markers",
        "live_api: mark test as requiring live API credentials and open market"
    )
