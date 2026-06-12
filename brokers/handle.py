"""BrokerHandle — fluent API wrapper around a BrokerConnection.

Inspired by Trade_J's BrokerHandle providing a concise, readable interface
for interacting with broker connections.

Usage::
    handle = BrokerHandle(connection)
    handle.connect()
    provider = handle.get_provider(Capability.MARKET_DATA)
"""

from __future__ import annotations

from typing import Any

from brokers.common.core.connection import BrokerConnection, Capability, ConnectionStatus


class BrokerHandle:
    """A fluent API handle that wraps a BrokerConnection.

    Provides capability-based provider discovery and connection lifecycle
    management in a single consistent interface.
    """

    def __init__(self, connection: BrokerConnection):
        self._connection = connection

    # ── Identity ─────────────────────────────────────────────────

    @property
    def name(self) -> str:
        return self._connection.name

    @property
    def broker_id(self) -> str:
        return self._connection.broker_id

    @property
    def connection(self) -> BrokerConnection:
        return self._connection

    # ── Connection Lifecycle ─────────────────────────────────────

    def connect(self) -> bool:
        return self._connection.connect()

    def disconnect(self) -> bool:
        return self._connection.disconnect()

    def reconnect(self) -> bool:
        return self._connection.reconnect()

    def is_connected(self) -> bool:
        return self._connection.status.is_connected()

    @property
    def status(self) -> ConnectionStatus:
        return self._connection.status

    # ── Capability Discovery (Trade_J pattern) ───────────────────

    def capabilities(self) -> set[Capability]:
        return self._connection.capabilities()

    def has_capability(self, capability: Capability) -> bool:
        return self._connection.has_capability(capability)

    def get_provider(self, capability: Capability) -> Any:
        """Get the provider implementation for a capability."""
        return self._connection.get_capability(capability)

    # ── Utility ──────────────────────────────────────────────────

    # ── Context Manager ──────────────────────────────────────────

    def __enter__(self) -> BrokerHandle:
        self.connect()
        return self

    def __exit__(self, *args) -> None:
        self.disconnect()

    def __repr__(self) -> str:
        status = "connected" if self.is_connected() else "disconnected"
        caps = len(self.capabilities())
        return (
            f"BrokerHandle(name='{self.name}', id='{self.broker_id}', "
            f"status={status}, capabilities={caps})"
        )

    def __str__(self) -> str:
        return f"BrokerHandle({self.name}/{self.broker_id})"
