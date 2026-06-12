"""WebSocketMultiplexer — manages market data subscriptions and fan-out to listeners.

Enhanced with WebSocket support for real-time market data feeds.

Inspired by Trade_J's WebSocketMultiplexer interface.

Usage::

    mux = WebSocketMultiplexer()
    mux.add_market_data_listener(my_callback)

    reqs = [MarketSubscriptionRequest("2885", NSE), ...]
    mux.subscribe(reqs, FeedMode.FULL)
    mux.connect()

    # Later
    mux.unsubscribe(reqs)
    mux.disconnect()
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock

logger = logging.getLogger(__name__)

from brokers.common.core.enums import ExchangeSegment, FeedMode
from brokers.common.core.models import Quote
from brokers.dhan.websocket.market_data import (
    DhanMarketFeedWebSocketClient,
)


@dataclass(eq=True, frozen=True)
class MarketSubscriptionRequest:
    """A request to subscribe to market data for a specific instrument.

    Immutable and hashable for use in sets and dicts.
    """

    security_id: str
    exchange_segment: ExchangeSegment


class WebSocketMultiplexer:
    """Manages market data subscriptions and notifies registered listeners.

    Provides a unified interface for subscribing/unsubscribing instruments
    across multiple feed modes and fanning out received data to listeners.
    Enhanced with WebSocket support for real-time market data feeds.
    """

    def __init__(
        self,
        url_resolver: Any | None = None,
        token_provider: Callable[[], str] | None = None,
        settings: Any | None = None,
        timeout_seconds: int = 15,
    ):
        self._subscriptions: dict[MarketSubscriptionRequest, FeedMode] = {}
        self._listeners: list[Callable[[Quote], None]] = []
        self._connected: bool = False
        self._lock = Lock()

        # WebSocket support
        self._url_resolver = url_resolver
        self._token_provider = token_provider
        self._settings = settings
        self._timeout_seconds = timeout_seconds
        self._websocket_client: DhanMarketFeedWebSocketClient | None = None
        self._websocket_connected: bool = False

    # ── Connection Lifecycle ─────────────────────────────────────

    def connect(self) -> bool:
        """Open the multiplexer for business."""
        self._connected = True
        return True

    def disconnect(self) -> bool:
        """Close the multiplexer."""
        self._connected = False
        return True

    def is_connected(self) -> bool:
        return self._connected

    # ── Subscription Management ──────────────────────────────────

    def subscribe(
        self,
        instruments: list[MarketSubscriptionRequest],
        feed_mode: FeedMode = FeedMode.LTP,
    ) -> None:
        """Subscribe to market data for the given instruments.

        If an instrument is already subscribed, its feed mode is upgraded
        (last write wins for simplicity).
        """
        with self._lock:
            for req in instruments:
                self._subscriptions[req] = feed_mode

    def unsubscribe(self, instruments: list[MarketSubscriptionRequest]) -> None:
        """Unsubscribe from the given instruments."""
        with self._lock:
            for req in instruments:
                self._subscriptions.pop(req, None)

    def subscriptions(self) -> dict[MarketSubscriptionRequest, FeedMode]:
        """Return a copy of current subscriptions."""
        with self._lock:
            return dict(self._subscriptions)

    def instrument_count(self) -> int:
        """Number of currently subscribed instruments."""
        with self._lock:
            return len(self._subscriptions)

    # ── Listener Management ──────────────────────────────────────

    def add_market_data_listener(self, listener: Callable[[Quote], None]) -> None:
        """Register a callback to receive market data quotes."""
        self._listeners.append(listener)

    def remove_market_data_listener(self, listener: Callable[[Quote], None]) -> None:
        """Unregister a market data listener."""
        self._listeners.remove(listener)

    # ── Internal: notify listeners ───────────────────────────────

    def _notify_listeners(self, quote: Quote) -> None:
        """Fan out a quote to all registered listeners."""
        for listener in self._listeners:
            try:
                listener(quote)
            except Exception as e:
                logger.warning("Market data listener failed: %s", e)

    # ── WebSocket Support ─────────────────────────────────────────

    def connect_websocket(self) -> bool:
        """Connect WebSocket client for real-time market data."""
        if not self._url_resolver or not self._token_provider or not self._settings:
            logger.error("Missing required parameters for WebSocket connection")
            return False

        if self._websocket_client is None:
            self._websocket_client = DhanMarketFeedWebSocketClient(
                url_resolver=self._url_resolver,
                token_provider=self._token_provider,
                settings=self._settings,
                timeout_seconds=self._timeout_seconds,
            )

        success = self._websocket_client.connect()
        if success:
            self._websocket_connected = True
            self._websocket_client.set_multiplexer(self)
            logger.info("WebSocket client connected and multiplexer set")
        return success

    def disconnect_websocket(self) -> bool:
        """Disconnect WebSocket client."""
        if self._websocket_client:
            success = self._websocket_client.disconnect()
            self._websocket_connected = False
            return success
        return True

    def is_websocket_connected(self) -> bool:
        """Check if WebSocket is connected."""
        return (
            self._websocket_connected
            and self._websocket_client
            and self._websocket_client.is_connected()
        )

    def subscribe_websocket(
        self,
        security_id: str,
        exchange_segment: ExchangeSegment,
        feed_mode: FeedMode = FeedMode.LTP,
    ) -> bool:
        """Subscribe to WebSocket market data for a specific instrument."""
        if self._websocket_client:
            return self._websocket_client.subscribe(security_id, exchange_segment, feed_mode)
        return False

    def unsubscribe_websocket(
        self,
        security_id: str,
        exchange_segment: ExchangeSegment,
    ) -> bool:
        """Unsubscribe from WebSocket market data for a specific instrument."""
        if self._websocket_client:
            return self._websocket_client.unsubscribe(security_id, exchange_segment)
        return False

    def get_websocket_subscriptions(self) -> dict[str, dict[str, Any]]:
        """Get WebSocket subscriptions from connection manager."""
        if self._websocket_client and hasattr(self._websocket_client, "_connection_manager"):
            return self._websocket_client._connection_manager.get_subscriptions()
        return {}

    # ── Async WebSocket Support ──────────────────────────────────

    async def connect_websocket_async(self) -> bool:
        """Async WebSocket connection — non-blocking alternative."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.connect_websocket)

    async def disconnect_websocket_async(self) -> bool:
        """Async WebSocket disconnection."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.disconnect_websocket)

    async def subscribe_websocket_async(
        self,
        security_id: str,
        exchange_segment: ExchangeSegment,
        feed_mode: FeedMode = FeedMode.LTP,
    ) -> bool:
        """Async WebSocket subscription."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            self.subscribe_websocket,
            security_id,
            exchange_segment,
            feed_mode,
        )

    async def unsubscribe_websocket_async(
        self,
        security_id: str,
        exchange_segment: ExchangeSegment,
    ) -> bool:
        """Async WebSocket unsubscription."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            self.unsubscribe_websocket,
            security_id,
            exchange_segment,
        )
