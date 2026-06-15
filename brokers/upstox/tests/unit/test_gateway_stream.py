"""Tests for UpstoxBrokerGateway.stream() connectivity and listener safety."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

from brokers.upstox.gateway import UpstoxBrokerGateway


class _MockWebsocket:
    def __init__(self, connected: bool = False) -> None:
        self._connected = connected
        self.subscribed: list[tuple[list[str], str]] = []
        self.listeners: list[Callable[[str, Any], None]] = []
        self.connect_called = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    def subscribe(self, keys: list[str], mode: str) -> None:
        self.subscribed.append((keys, mode))

    def add_listener(self, listener: Callable[[str, Any], None]) -> None:
        self.listeners.append(listener)

    async def connect(self) -> None:
        self.connect_called = True
        self._connected = True


def _make_gateway(connected: bool = False) -> tuple[UpstoxBrokerGateway, _MockWebsocket, MagicMock]:
    ws = _MockWebsocket(connected=connected)
    broker = MagicMock()
    broker.market_data_websocket = ws
    gateway = UpstoxBrokerGateway(broker)
    return gateway, ws, broker


class TestUpstoxGatewayStream:
    def test_stream_subscribes_when_already_connected(self):
        gateway, ws, _broker = _make_gateway(connected=True)

        gateway.stream("INFY", exchange="NSE", mode="LTP")

        assert not ws.connect_called
        assert len(ws.subscribed) == 1
        keys, mode = ws.subscribed[0]
        assert keys == ["NSE|INFY"]
        assert mode == "ltp"

    def test_stream_connects_when_not_connected(self):
        gateway, ws, _broker = _make_gateway(connected=False)

        gateway.stream("INFY", exchange="NSE", mode="LTP")

        assert ws.connect_called
        assert len(ws.subscribed) == 1
        keys, mode = ws.subscribed[0]
        assert keys == ["NSE|INFY"]
        assert mode == "ltp"

    def test_stream_wraps_on_tick_callback_signature(self):
        """The sync one-arg on_tick(payload) must be adapted to listener(event_type, payload)."""
        gateway, ws, _broker = _make_gateway(connected=True)

        received: list[Any] = []

        def on_tick(payload: Any) -> None:
            received.append(payload)

        gateway.stream("INFY", exchange="NSE", mode="LTP", on_tick=on_tick)

        assert len(ws.listeners) == 1
        listener = ws.listeners[0]
        # Listener must accept two args and forward only the payload.
        listener("tick", {"ltp": 1500})

        assert len(received) == 1
        assert received[0] == {"ltp": 1500}

    def test_stream_maps_exchange_segment(self):
        gateway, ws, _broker = _make_gateway(connected=True)

        gateway.stream("RELIANCE", exchange="BSE", mode="FULL")

        keys, mode = ws.subscribed[0]
        assert keys == ["BSE|RELIANCE"]
        assert mode == "full"

    def test_stream_accepts_on_tick_none(self):
        gateway, ws, _broker = _make_gateway(connected=True)

        result = gateway.stream("INFY", exchange="NSE", mode="LTP")

        assert result is ws
        assert ws.listeners == []

    def test_stream_connects_async_when_loop_running(self):
        async def _inner() -> None:
            gateway, ws, _broker = _make_gateway(connected=False)
            gateway.stream("INFY", exchange="NSE", mode="LTP")
            await asyncio.sleep(0)
            assert ws.connect_called

        asyncio.run(_inner())
