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


@pytest.fixture(scope="session", autouse=False)
def _register_domain_runtime_hooks() -> None:
    """Wire broker factories into domain hooks for analytics engines in tests."""
    from application.execution.oms_backtest_adapter import create_oms_backtest_adapter
    from application.oms.factory import create_trading_context
    from domain.runtime_hooks import (
        create_domain_event,
        register_domain_event_factory,
        register_oms_backtest_factory,
        register_trading_context_factory,
    )

    register_oms_backtest_factory(create_oms_backtest_adapter)
    register_domain_event_factory(create_domain_event)
    register_trading_context_factory(create_trading_context)

    # Ensure broker adapter classes are registered into infrastructure.adapter_factory.
    # Brokers self-register on package import; importing them here guarantees the
    # registry is populated for every test (idempotent).
    import brokers.providers.dhan
    import brokers.providers.upstox  # noqa: F401


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

    .. warning::

       ``load_dotenv(override=True)`` is **process-global**.  Under
       ``pytest-xdist`` or any parallel runner the env-vars leak across workers,
       which may cause one worker to see another's credentials.  This is
       acceptable for the single-process session today but would need
       per-worker isolation (e.g. ``monkeypatch.setenv``) if parallel execution
       is ever enabled.
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

    .. warning::

       ``load_dotenv(override=True)`` is **process-global**.  Under
       ``pytest-xdist`` or any parallel runner the env-vars leak across workers,
       which may cause one worker to see another's credentials.  This is
       acceptable for the single-process session today but would need
       per-worker isolation (e.g. ``monkeypatch.setenv``) if parallel execution
       is ever enabled.
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


def build_test_trading_context(*, events_dir: Path | None = None, **kwargs: Any) -> TradingContext:
    """Build a TradingContext with default event infrastructure for tests.

    The OMS no longer constructs infrastructure objects itself (see D4 port
    extraction), so event collaborators must be injected.  This helper fills
    ``event_bus`` / ``event_log`` / ``processed_trade_repository`` /
    ``dead_letter_queue`` defaults — importing the concrete classes from
    ``infrastructure`` (allowed inside the test tree) — and forwards every other
    keyword argument to :func:`create_trading_context`.  Use it anywhere a test
    previously relied on ``TradingContext(...)`` / ``create_trading_context(...)``
    building its own defaults.

    Args:
        events_dir: Directory for BufferedEventLog. Pass ``tmp_path`` from a
            pytest fixture for automatic cleanup; if *None*, creates a
            temporary directory that will NOT be cleaned up (legacy behavior).
        **kwargs: Forwarded to :func:`create_trading_context`.
    """
    from application.oms.factory import create_trading_context
    from infrastructure.event_bus import (
        EventBus,
        ProcessedTradeRepository,
        create_default_dead_letter_queue,
    )
    from infrastructure.event_log import BufferedEventLog

    if "event_bus" not in kwargs:
        if "dead_letter_queue" not in kwargs:
            kwargs["dead_letter_queue"] = create_default_dead_letter_queue()
        kwargs["event_bus"] = EventBus(
            event_log=kwargs.get("event_log"),
            dead_letter_queue=kwargs["dead_letter_queue"],
        )
    if "processed_trade_repository" not in kwargs:
        kwargs["processed_trade_repository"] = ProcessedTradeRepository()
    import tempfile

    if "event_log" not in kwargs:
        if events_dir is None:
            events_dir = Path(tempfile.mkdtemp(prefix="tradex-test-events-"))
        kwargs["event_log"] = BufferedEventLog(events_dir=events_dir)
    if "metrics" not in kwargs:
        from infrastructure.observability.event_metrics import EventMetrics

        kwargs["metrics"] = EventMetrics()
    if "metrics_registry" not in kwargs:
        from infrastructure.metrics import metrics_registry

        kwargs["metrics_registry"] = metrics_registry
    ctx = create_trading_context(**kwargs)
    if ctx.risk_manager is not None:
        rm = ctx.risk_manager
        if getattr(rm, "_instrument_provider", None) is None:
            from dataclasses import dataclass
            from decimal import Decimal

            @dataclass
            class _TestInstrument:
                tick_size: Decimal = Decimal("0.05")

            class _TestInstrumentProvider:
                def resolve(self, symbol: str, exchange: str):
                    return _TestInstrument()

            rm._instrument_provider = _TestInstrumentProvider()
    return ctx


@pytest.fixture
def event_bus():
    """Create a fresh EventBus for a single test."""
    from infrastructure.event_bus import EventBus

    return EventBus()


@pytest.fixture
def processed_trade_repository():
    """Create a fresh ProcessedTradeRepository for a single test."""
    from infrastructure.event_bus import ProcessedTradeRepository

    return ProcessedTradeRepository()
