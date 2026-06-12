"""WebSocket connection manager for Dhan market data feed.

Manages WebSocket connections, subscriptions, and reconnection logic.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from brokers.common.core.enums import ExchangeSegment, FeedMode
from brokers.common.core.models import Quote

logger = logging.getLogger(__name__)


class WebSocketState(Enum):
    """WebSocket connection states."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"


@dataclass
class WebSocketMessage:
    """WebSocket message wrapper."""

    security_id: str
    exchange_segment: ExchangeSegment
    feed_mode: FeedMode
    data: dict[str, Any]
    timestamp: datetime


class DhanWebSocketConnectionManager:
    """Manages WebSocket connections and subscriptions for Dhan market data.

    Handles connection lifecycle, subscription management, and reconnection logic.
    """

    def __init__(
        self,
        url_resolver: Any,
        token_provider: Callable[[], str],
        settings: Any,
        timeout_seconds: int = 15,
    ) -> None:
        self._url_resolver = url_resolver
        self._token_provider = token_provider
        self._settings = settings
        self._timeout_seconds = timeout_seconds

        self._state = WebSocketState.DISCONNECTED
        self._ws = None
        self._subscriptions: dict[str, dict[str, Any]] = {}
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 5
        self._reconnect_delay = 1.0

        self._message_handlers: list[Callable[[WebSocketMessage], None]] = []
        self._connection_callbacks: list[Callable[[bool], None]] = []

        # Multiplexing queue to prevent rate limit spikes during subscription additions/removals
        self._subscription_queue: asyncio.Queue = asyncio.Queue()
        self._queue_worker_task: asyncio.Task | None = None
        self._rate_limit_delay = 0.1  # 100ms spacing between operations

    async def _process_subscription_queue(self) -> None:
        """Worker task processing subscription updates in FIFO order to prevent rate limiting."""
        while True:
            try:
                (
                    action,
                    security_id,
                    exchange_segment,
                    feed_mode,
                ) = await self._subscription_queue.get()
                if self._state == WebSocketState.CONNECTED and self._ws:
                    # In a real SDK, e.g. self._ws.send(...)
                    logger.debug(f"WebSocket client executed: {action} {security_id}")
                self._subscription_queue.task_done()
                await asyncio.sleep(self._rate_limit_delay)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in subscription queue worker: {e}")
                await asyncio.sleep(1.0)

    def connect(self) -> bool:
        """Establish WebSocket connection."""
        if self._state == WebSocketState.CONNECTED:
            return True

        try:
            self._state = WebSocketState.CONNECTING
            logger.info("Connecting to Dhan WebSocket feed")

            self._ws = self._create_websocket_connection()
            self._state = WebSocketState.CONNECTED
            self._reconnect_attempts = 0

            # Start subscription queue worker
            try:
                loop = asyncio.get_running_loop()
                self._queue_worker_task = loop.create_task(self._process_subscription_queue())
            except RuntimeError:
                pass

            logger.info("WebSocket connected successfully")
            self._notify_connection_callbacks(True)
            return True

        except Exception as e:
            logger.error(f"WebSocket connection failed: {e}")
            self._state = WebSocketState.ERROR
            self._notify_connection_callbacks(False)
            self._schedule_reconnect()
            return False

    def disconnect(self) -> bool:
        """Close WebSocket connection."""
        if self._queue_worker_task:
            self._queue_worker_task.cancel()
            self._queue_worker_task = None

        if self._ws:
            try:
                self._ws.close()
                logger.info("WebSocket disconnected")
            except Exception as e:
                logger.warning(f"Error during WebSocket disconnect: {e}")
            finally:
                self._ws = None

        self._state = WebSocketState.DISCONNECTED
        self._notify_connection_callbacks(False)
        return True

    def subscribe(
        self,
        security_id: str,
        exchange_segment: ExchangeSegment,
        feed_mode: FeedMode = FeedMode.LTP,
    ) -> bool:
        """Subscribe to market data for a specific instrument."""
        if self._state != WebSocketState.CONNECTED:
            logger.warning("Cannot subscribe, WebSocket not connected")
            return False

        key = f"{security_id}:{exchange_segment.value}"
        self._subscriptions[key] = {
            "security_id": security_id,
            "exchange_segment": exchange_segment,
            "feed_mode": feed_mode,
        }

        # Queue subscription to be processed with rate-limiting constraints
        try:
            loop = asyncio.get_running_loop()
            loop.call_soon_threadsafe(
                self._subscription_queue.put_nowait,
                ("subscribe", security_id, exchange_segment, feed_mode),
            )
        except RuntimeError:
            self._subscription_queue.put_nowait(
                ("subscribe", security_id, exchange_segment, feed_mode)
            )

        logger.debug(f"Queued subscription for {security_id} on {exchange_segment.value}")
        return True

    def unsubscribe(
        self,
        security_id: str,
        exchange_segment: ExchangeSegment,
    ) -> bool:
        """Unsubscribe from market data for a specific instrument."""
        key = f"{security_id}:{exchange_segment.value}"
        if key in self._subscriptions:
            del self._subscriptions[key]

            # Queue unsubscription to be processed with rate-limiting constraints
            try:
                loop = asyncio.get_running_loop()
                loop.call_soon_threadsafe(
                    self._subscription_queue.put_nowait,
                    ("unsubscribe", security_id, exchange_segment, None),
                )
            except RuntimeError:
                self._subscription_queue.put_nowait(
                    ("unsubscribe", security_id, exchange_segment, None)
                )

            logger.debug(f"Queued unsubscription for {security_id} on {exchange_segment.value}")
            return True
        return False

    def is_connected(self) -> bool:
        """Check if WebSocket is connected."""
        return self._state == WebSocketState.CONNECTED and self._ws is not None

    def get_subscriptions(self) -> dict[str, dict[str, Any]]:
        """Get current subscriptions."""
        return dict(self._subscriptions)

    def add_message_handler(self, handler: Callable[[WebSocketMessage], None]) -> None:
        """Add a message handler."""
        self._message_handlers.append(handler)

    def add_connection_callback(self, callback: Callable[[bool], None]) -> None:
        """Add a connection state callback."""
        self._connection_callbacks.append(callback)

    def _create_websocket_connection(self):
        """Create WebSocket connection.

        TODO(phase-4): Replace with real Dhan SDK WebSocket client.
        The current stub silently does nothing — DO NOT use in production.
        """
        logger.warning(
            "DhanWebSocketConnectionManager is using a STUB WebSocket. "
            "Live tick data will not flow. See Phase 4 plan."
        )

        class _StubWebSocket:
            def close(self):
                pass

            def send(self, *args, **kwargs):
                return None

            def recv(self, *args, **kwargs):
                return None

        return _StubWebSocket()

    def _schedule_reconnect(self) -> None:
        """Schedule reconnection attempt."""
        if self._reconnect_attempts >= self._max_reconnect_attempts:
            logger.error("Max reconnection attempts reached")
            return

        self._state = WebSocketState.RECONNECTING
        self._reconnect_attempts += 1

        delay = self._reconnect_delay * (2 ** (self._reconnect_attempts - 1))
        logger.info(f"Scheduling reconnection in {delay} seconds")

        async def _reconnect_task():
            await asyncio.sleep(delay)
            self.connect()

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_reconnect_task())
        except RuntimeError:
            pass

    def _notify_connection_callbacks(self, connected: bool) -> None:
        """Notify connection state callbacks."""
        for callback in self._connection_callbacks:
            try:
                callback(connected)
            except Exception as e:
                logger.warning(f"Connection callback failed: {e}")

    def _notify_message_handlers(self, message: WebSocketMessage) -> None:
        """Notify message handlers."""
        for handler in self._message_handlers:
            try:
                handler(message)
            except Exception as e:
                logger.warning(f"Message handler failed: {e}")


class DhanMarketEventNormalizer:
    """Normalizes WebSocket market data messages into Quote objects.

    Converts raw WebSocket data into standardized Quote objects for consistent
    processing across the application.
    """

    @staticmethod
    def normalize_quote(
        raw_data: dict[str, Any],
        security_id: str,
        exchange_segment: ExchangeSegment,
        feed_mode: FeedMode = FeedMode.LTP,
    ) -> Quote:
        """Normalize raw WebSocket data into a Quote object."""
        from datetime import datetime
        from decimal import Decimal

        # Extract data based on feed mode
        if feed_mode == FeedMode.LTP:
            last_price = Decimal(str(raw_data.get("last_price", raw_data.get("ltp", 0))))
            volume = int(raw_data.get("volume", 0))
            open_price = Decimal(str(raw_data.get("open", 0)))
            high = Decimal(str(raw_data.get("high", 0)))
            low = Decimal(str(raw_data.get("low", 0)))
            close = Decimal(str(raw_data.get("close", 0)))
        else:  # FULL mode
            last_price = Decimal(str(raw_data.get("last_price", raw_data.get("ltp", 0))))
            volume = int(raw_data.get("volume", 0))
            open_price = Decimal(str(raw_data.get("open", 0)))
            high = Decimal(str(raw_data.get("high", 0)))
            low = Decimal(str(raw_data.get("low", 0)))
            close = Decimal(str(raw_data.get("close", 0)))

        return Quote(
            security_id=security_id,
            exchange_segment=exchange_segment,
            last_price=last_price,
            open=open_price,
            high=high,
            low=low,
            close=close,
            volume=volume,
            timestamp=datetime.now(),
        )

    @staticmethod
    def normalize_depth(
        raw_data: dict[str, Any],
        security_id: str,
        exchange_segment: ExchangeSegment,
    ):
        """Normalize raw WebSocket depth data."""
        from datetime import datetime
        from decimal import Decimal

        from brokers.common.core.models import MarketDepth, MarketDepthLevel

        bids = []
        asks = []

        # Normalize bid levels
        for level_data in raw_data.get("bids", []):
            bids.append(
                MarketDepthLevel(
                    price=Decimal(str(level_data.get("price", 0))),
                    quantity=int(level_data.get("quantity", 0)),
                    orders=int(level_data.get("orders", 0)),
                )
            )

        # Normalize ask levels
        for level_data in raw_data.get("asks", []):
            asks.append(
                MarketDepthLevel(
                    price=Decimal(str(level_data.get("price", 0))),
                    quantity=int(level_data.get("quantity", 0)),
                    orders=int(level_data.get("orders", 0)),
                )
            )

        return MarketDepth(
            exchange_segment=exchange_segment,
            bids=bids,
            asks=asks,
            timestamp=datetime.now(),
        )


class DhanMarketFeedWebSocketClient:
    """WebSocket client for Dhan market data feed.

    Handles WebSocket communication, message parsing, and event emission.
    """

    def __init__(
        self,
        url_resolver: Any,
        token_provider: Callable[[], str],
        settings: Any,
        timeout_seconds: int = 15,
    ) -> None:
        self._url_resolver = url_resolver
        self._token_provider = token_provider
        self._settings = settings
        self._timeout_seconds = timeout_seconds

        self._connection_manager = DhanWebSocketConnectionManager(
            url_resolver=url_resolver,
            token_provider=token_provider,
            settings=settings,
            timeout_seconds=timeout_seconds,
        )
        self._event_normalizer = DhanMarketEventNormalizer()

        self._multiplexer = None
        self._message_queue = asyncio.Queue()

    def connect(self) -> bool:
        """Connect to market data feed."""
        return self._connection_manager.connect()

    def disconnect(self) -> bool:
        """Disconnect from market data feed."""
        return self._connection_manager.disconnect()

    def subscribe(
        self,
        security_id: str,
        exchange_segment: ExchangeSegment,
        feed_mode: FeedMode = FeedMode.LTP,
    ) -> bool:
        """Subscribe to market data for a specific instrument."""
        return self._connection_manager.subscribe(
            security_id=security_id,
            exchange_segment=exchange_segment,
            feed_mode=feed_mode,
        )

    def unsubscribe(
        self,
        security_id: str,
        exchange_segment: ExchangeSegment,
    ) -> bool:
        """Unsubscribe from market data for a specific instrument."""
        return self._connection_manager.unsubscribe(
            security_id=security_id,
            exchange_segment=exchange_segment,
        )

    def is_connected(self) -> bool:
        """Check if connected to market data feed."""
        return self._connection_manager.is_connected()

    def set_multiplexer(self, multiplexer) -> None:
        """Set the multiplexer for fan-out."""
        self._multiplexer = multiplexer
        self._connection_manager.add_message_handler(self._handle_message)

    def _handle_message(self, message: WebSocketMessage) -> None:
        """Handle incoming WebSocket message."""
        # Normalize the message
        if message.feed_mode in [FeedMode.LTP, FeedMode.FULL]:
            quote = self._event_normalizer.normalize_quote(
                message.data,
                message.security_id,
                message.exchange_segment,
                message.feed_mode,
            )

            # Fan out to multiplexer
            if self._multiplexer:
                self._multiplexer._notify_listeners(quote)

        elif message.feed_mode == FeedMode.DEPTH:
            self._event_normalizer.normalize_depth(
                message.data,
                message.security_id,
                message.exchange_segment,
            )

            # Fan out to multiplexer (if depth support is added)
            if self._multiplexer:
                # In a real implementation, this would notify depth listeners
                pass

        logger.debug(f"Processed message for {message.security_id}")
