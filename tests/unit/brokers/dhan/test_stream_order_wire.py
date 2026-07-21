"""Dhan wire adapter must expose distinct order-stream entry points."""

from __future__ import annotations

from unittest.mock import MagicMock

from brokers.providers.dhan.wire import DhanWireAdapter


def test_gateway_constructible_with_order_stream_capability() -> None:
    conn = MagicMock()
    conn.subscription_engine = MagicMock()
    conn.subscription_engine.subscribe_order.return_value = MagicMock()
    client = MagicMock()
    client.access_token = "token"
    conn._client = client

    gw = DhanWireAdapter(conn)

    assert gw.capabilities().supports_order_stream is True
    assert callable(gw.stream_order)
    assert callable(gw.unstream_order)
    assert gw.stream_order is not gw.stream


def test_stream_order_delegates_to_subscription_engine() -> None:
    conn = MagicMock()
    conn.subscription_engine = MagicMock()
    handle = MagicMock()
    conn.subscription_engine.subscribe_order.return_value = handle
    client = MagicMock()
    client.access_token = "token"
    conn._client = client

    gw = DhanWireAdapter(conn)
    cb = MagicMock()
    result = gw.stream_order(cb)

    conn.subscription_engine.subscribe_order.assert_called_once_with(cb)
    assert result is handle


def test_unstream_order_delegates_to_subscription_engine() -> None:
    conn = MagicMock()
    conn.subscription_engine = MagicMock()
    client = MagicMock()
    client.access_token = "token"
    conn._client = client

    gw = DhanWireAdapter(conn)
    cb = MagicMock()
    gw.unstream_order(cb)

    conn.subscription_engine.unsubscribe_order.assert_called_once_with(cb)
