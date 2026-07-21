"""BrokerStreamingPort — live streaming operations for broker adapters.

Narrow ABC that captures the streaming surface of a broker. Callers that
only need live data feeds (real-time dashboards, streaming analytics) should
depend on this port instead of the full :class:`BrokerAdapter`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BrokerStreamingPort(ABC):
    """Live streaming operations — the streaming surface of a broker.

    This is a focused subset of :class:`BrokerAdapter`. Callers that only need
    live data feeds should depend on this port instead of the full broker
    interface.
    """

    @abstractmethod
    def stream(
        self,
        symbol: str,
        exchange: str = "NSE",
        mode: str = "LTP",
        on_tick: Any | None = None,
    ) -> Any:
        """Subscribe to a live tick stream."""
        ...

    @abstractmethod
    def unstream(
        self,
        symbol: str,
        exchange: str = "NSE",
        on_tick: Any | None = None,
    ) -> None:
        """Unsubscribe from a live tick stream."""
        ...

    @abstractmethod
    def stream_depth(
        self,
        symbol: str,
        exchange: str = "NSE",
        *,
        levels: int = 5,
        on_depth: Any | None = None,
    ) -> Any:
        """Subscribe to depth (order book) streaming."""
        ...

    @abstractmethod
    def stream_order(self, on_order: Any | None = None) -> Any:
        """Subscribe to order updates."""
        ...
