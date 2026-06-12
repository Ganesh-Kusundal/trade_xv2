"""Unit tests for Dhan adapter resilience hardening (connection pooling, cooldowns, and multiplexing)."""

import asyncio
import time
from unittest.mock import MagicMock

import requests

from brokers.common.core.enums import ExchangeSegment
from brokers.common.resilience.retry import RetryConfig, RetryExecutor
from brokers.dhan.auth.http import DhanAuthenticatedHttpClient
from brokers.dhan.market_data.options import DhanOptionsClient
from brokers.dhan.websocket.market_data import DhanWebSocketConnectionManager, WebSocketState


def test_http_client_connection_pooling():
    """Verify that DhanAuthenticatedHttpClient sets up requests HTTPAdapter connection pooling."""
    settings = MagicMock()
    settings.client_id = "test_client"
    settings.pool_connections = 40
    settings.pool_maxsize = 80

    client = DhanAuthenticatedHttpClient(
        token_provider=lambda: "test_token",
        settings=settings,
    )

    session = client._session
    assert isinstance(session, requests.Session)

    # Check mounts
    https_adapter = session.adapters.get("https://")
    http_adapter = session.adapters.get("http://")

    assert https_adapter is not None
    assert http_adapter is not None
    assert https_adapter._pool_connections == 40
    assert https_adapter._pool_maxsize == 80


def test_options_client_option_chain_cooldown():
    """Verify that DhanOptionsClient enforces a 3.1-second cooldown per underlying/expiry combo."""
    http_client = MagicMock()
    http_client.post_json.return_value = {"status": "success", "data": {"optionChain": []}}
    settings = MagicMock()
    url_resolver = MagicMock()

    executor = RetryExecutor(
        config=RetryConfig(max_attempts=1),
        circuit_breaker=MagicMock(),
        rate_limiter=MagicMock(),
        rate_limit_category="data",
    )

    client = DhanOptionsClient(
        http_client=http_client,
        settings=settings,
        url_resolver=url_resolver,
        retry_executor=executor,
    )

    # Cooldown should be initialized
    assert client._cooldown == 3.1

    # First call - instant
    start_time = time.time()
    client.get_option_chain(
        underlying="NIFTY", exchange_segment=ExchangeSegment.NSE_FNO, expiry="2026-07-30"
    )
    first_call_duration = time.time() - start_time
    assert first_call_duration < 1.0  # Should be instant

    # Second call - should trigger sleep / throttling delay
    start_time = time.time()
    client.get_option_chain(
        underlying="NIFTY", exchange_segment=ExchangeSegment.NSE_FNO, expiry="2026-07-30"
    )
    second_call_duration = time.time() - start_time
    # Should take at least ~3 seconds because of the cooldown
    assert second_call_duration >= 2.9


def test_websocket_multiplexing_queue():
    """Verify that DhanWebSocketConnectionManager queues subscriptions and processes them sequentially."""

    async def run_test():
        url_resolver = MagicMock()

        def token_provider():
            return "token"

        settings = MagicMock()

        manager = DhanWebSocketConnectionManager(
            url_resolver=url_resolver,
            token_provider=token_provider,
            settings=settings,
        )
        manager._rate_limit_delay = 0.01  # Use a small delay for faster tests

        # Connect to start the queue task
        manager.connect()
        assert manager._state == WebSocketState.CONNECTED
        assert manager._queue_worker_task is not None

        # Queue multiple subscriptions
        manager.subscribe("1001", ExchangeSegment.NSE)
        manager.subscribe("1002", ExchangeSegment.NSE)
        manager.subscribe("1003", ExchangeSegment.NSE)

        # Let the worker run
        await asyncio.sleep(0.05)

        # Check that subscriptions are recorded
        subs = manager.get_subscriptions()
        assert len(subs) == 3
        assert "1001:NSE_EQ" in subs
        assert "1002:NSE_EQ" in subs
        assert "1003:NSE_EQ" in subs

        # Clean up
        manager.disconnect()
        assert manager._queue_worker_task is None

    asyncio.run(run_test())


def test_websocket_async_reconnection_schedule():
    """Verify that _schedule_reconnect schedules connect() in the event loop."""

    async def run_test():
        url_resolver = MagicMock()

        def token_provider():
            return "token"

        settings = MagicMock()

        manager = DhanWebSocketConnectionManager(
            url_resolver=url_resolver,
            token_provider=token_provider,
            settings=settings,
        )
        manager._reconnect_delay = 0.01  # Very short delay for fast test

        # Start disconnected
        assert manager._state == WebSocketState.DISCONNECTED

        # Schedule reconnect
        manager._schedule_reconnect()
        assert manager._state == WebSocketState.RECONNECTING

        # Wait for scheduled task to run connect()
        await asyncio.sleep(0.03)
        assert manager._state == WebSocketState.CONNECTED

        manager.disconnect()

    asyncio.run(run_test())
