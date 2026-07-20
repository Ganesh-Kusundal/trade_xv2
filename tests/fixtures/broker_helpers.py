"""Shared broker gateway/connection factories for tests."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Dhan gateway factory
# ---------------------------------------------------------------------------


def make_dhan_gateway() -> DhanBrokerGateway:
    """Create a DhanBrokerGateway backed by a FakeHttpClient (offline)."""
    from brokers.dhan.streaming.connection import DhanConnection
    from brokers.dhan.wire import DhanBrokerGateway
    from tests.support.brokers.dhan.fixtures import FakeHttpClient

    client = FakeHttpClient()
    conn = DhanConnection(client=client)
    return DhanBrokerGateway(conn)


# ---------------------------------------------------------------------------
# Upstox gateway factory
# ---------------------------------------------------------------------------


class MockWebsocket:
    """Minimal WebSocket stub for Upstox gateway tests."""

    def __init__(self, connected: bool = False) -> None:
        self._connected = connected
        self.subscribed: list[tuple[list[str], str]] = []
        self.listeners: list[Any] = []
        self.connect_called = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    def subscribe(self, keys: list[str], mode: str) -> None:
        self.subscribed.append((keys, mode))

    def add_listener(self, listener: Any) -> None:
        self.listeners.append(listener)

    def remove_listener(self, listener: Any) -> None:
        if listener in self.listeners:
            self.listeners.remove(listener)

    def unsubscribe(self, keys: list[str]) -> None:
        pass

    async def connect(self) -> None:
        self.connect_called = True
        self._connected = True


def make_upstox_gateway(
    connected: bool = False,
    resolver_defn: Any = None,
) -> tuple[UpstoxBrokerGateway, MockWebsocket, MagicMock]:
    """Create an UpstoxBrokerGateway with a mock broker and WebSocket.

    Returns (gateway, websocket, broker) — the websocket and broker are
    exposed so tests can inspect subscriptions and wire up listeners.
    """
    from brokers.upstox.wire import UpstoxBrokerGateway

    ws = MockWebsocket(connected=connected)
    broker = MagicMock()
    broker.market_data_websocket = ws

    mock_resolver = MagicMock()
    mock_resolver.resolve.return_value = resolver_defn
    broker.instrument_resolver = mock_resolver

    gateway = UpstoxBrokerGateway(broker)
    return gateway, ws, broker
