"""Minimal WebSocket streaming port — structural conformance for broker plugins."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class BrokerStreamGateway(Protocol):
    """Minimal streaming surface shared by Dhan/Upstox WS adapters."""

    def connect(self) -> bool:
        """Establish transport connection."""
        ...

    def subscribe(self, instruments: list[Any]) -> bool:
        """Subscribe to instruments; returns True when accepted."""
        ...

    def on_tick(self, callback: Callable[[Any], None]) -> None:
        """Register tick callback."""
        ...

    def disconnect(self) -> None:
        """Tear down transport and subscriptions."""
        ...
