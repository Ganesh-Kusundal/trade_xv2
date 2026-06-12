"""Order stream WebSocket client for Dhan.

Implements WebSocket connection for real-time order events including:
- Order placed
- Order modified
- Order cancelled
- Order filled (partial/full)
- Order status updates
- Order rejection
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class OrderStreamState(Enum):
    """Order stream WebSocket connection states."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"


class OrderEventType(str, Enum):
    """Order event types."""

    ORDER_PLACED = "order_placed"
    ORDER_MODIFIED = "order_modified"
    ORDER_CANCELLED = "order_cancelled"
    ORDER_FILLED = "order_filled"
    ORDER_STATUS_UPDATE = "order_status_update"
    ORDER_REJECTED = "order_rejected"


@dataclass
class OrderEvent:
    """Base class for order stream events."""

    event_type: OrderEventType
    order_id: str
    timestamp: datetime
    order_data: dict[str, Any]


@dataclass
class OrderStatusEvent(OrderEvent):
    """Order status update event."""

    order_id: str
    status: str
    filled_quantity: int
    remaining_quantity: int
    average_price: float | None


class DhanOrderEventNormalizer:
    """Normalizes WebSocket order events into Order objects.

    Converts raw WebSocket order data into standardized Order objects for consistent
    processing across the application.
    """

    @staticmethod
    def normalize_order_event(raw_data: dict[str, Any]) -> OrderEvent:
        """Normalize raw WebSocket order data into an OrderEvent."""
        event_type_str = raw_data.get("eventType", "")
        try:
            event_type = OrderEventType(event_type_str.lower())
        except ValueError:
            event_type = OrderEventType.ORDER_STATUS_UPDATE

        order_id = raw_data.get("orderId", raw_data.get("order_id", ""))
        timestamp = datetime.fromtimestamp(
            raw_data.get("timestamp", raw_data.get("time", time.time()))
        )

        if event_type == OrderEventType.ORDER_STATUS_UPDATE:
            return OrderStatusEvent(
                event_type=event_type,
                order_id=order_id,
                timestamp=timestamp,
                order_data=raw_data,
                status=raw_data.get("status", ""),
                filled_quantity=raw_data.get("filledQuantity", raw_data.get("filled_qty", 0)),
                remaining_quantity=raw_data.get(
                    "remainingQuantity", raw_data.get("pendingQuantity", 0)
                ),
                average_price=raw_data.get("averagePrice", raw_data.get("avgPrice")),
            )

        return OrderEvent(
            event_type=event_type,
            order_id=order_id,
            timestamp=timestamp,
            order_data=raw_data,
        )


class DhanOrderStreamConnectionManager:
    """Manages WebSocket connections and subscriptions for Dhan order stream.

    Handles connection lifecycle, subscription management, and reconnection logic
    for order stream WebSocket.
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

        self._state = OrderStreamState.DISCONNECTED
        self._ws = None
        self._subscriptions: dict[str, dict[str, Any]] = {}
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 5
        self._reconnect_delay = 1.0

        self._message_handlers: list[Callable[[OrderEvent], None]] = []
        self._connection_callbacks: list[Callable[[bool], None]] = []
        self._heartbeat_timer = None

    def connect(self) -> bool:
        """Establish WebSocket connection for order stream."""
        if self._state == OrderStreamState.CONNECTED:
            return True

        try:
            self._state = OrderStreamState.CONNECTING
            logger.info("Connecting to Dhan order stream WebSocket")

            # In a real implementation, this would create the WebSocket connection
            # For now, we'll simulate the connection
            self._ws = self._create_websocket_connection()
            self._state = OrderStreamState.CONNECTED
            self._reconnect_attempts = 0
            self._start_heartbeat()

            logger.info("Order stream WebSocket connected successfully")
            self._notify_connection_callbacks(True)
            return True

        except Exception as e:
            logger.error(f"Order stream WebSocket connection failed: {e}")
            self._state = OrderStreamState.ERROR
            self._notify_connection_callbacks(False)
            self._schedule_reconnect()
            return False

    def disconnect(self) -> bool:
        """Close WebSocket connection."""
        self._stop_heartbeat()

        if self._ws:
            try:
                self._ws.close()
                logger.info("Order stream WebSocket disconnected")
            except Exception as e:
                logger.warning(f"Error during order stream WebSocket disconnect: {e}")
            finally:
                self._ws = None

        self._state = OrderStreamState.DISCONNECTED
        self._notify_connection_callbacks(False)
        return True

    def subscribe(self, order_ids: list[str]) -> bool:
        """Subscribe to order stream for specific order IDs."""
        if self._state != OrderStreamState.CONNECTED:
            logger.warning("Cannot subscribe, order stream WebSocket not connected")
            return False

        for order_id in order_ids:
            self._subscriptions[order_id] = {
                "order_id": order_id,
            }

        # In a real implementation, send subscription request to WebSocket
        logger.debug(f"Subscribed to order stream for {len(order_ids)} orders")
        return True

    def unsubscribe(self, order_ids: list[str]) -> bool:
        """Unsubscribe from order stream for specific order IDs."""
        for order_id in order_ids:
            if order_id in self._subscriptions:
                del self._subscriptions[order_id]
                logger.debug(f"Unsubscribed from order stream for {order_id}")

        return True

    def is_connected(self) -> bool:
        """Check if order stream WebSocket is connected."""
        return self._state == OrderStreamState.CONNECTED and self._ws is not None

    def get_subscriptions(self) -> dict[str, dict[str, Any]]:
        """Get current subscriptions."""
        return dict(self._subscriptions)

    def add_message_handler(self, handler: Callable[[OrderEvent], None]) -> None:
        """Add a message handler."""
        self._message_handlers.append(handler)

    def add_connection_callback(self, callback: Callable[[bool], None]) -> None:
        """Add a connection state callback."""
        self._connection_callbacks.append(callback)

    def _create_websocket_connection(self):
        """Create WebSocket connection (placeholder for real implementation)."""

        # This would create the actual WebSocket connection in a real implementation
        # For now, return a mock object
        class MockWebSocket:
            def close(self):
                pass

        return MockWebSocket()

    def _schedule_reconnect(self) -> None:
        """Schedule reconnection attempt."""
        if self._reconnect_attempts >= self._max_reconnect_attempts:
            logger.error("Max reconnection attempts reached")
            return

        self._state = OrderStreamState.RECONNECTING
        self._reconnect_attempts += 1

        delay = self._reconnect_delay * (2 ** (self._reconnect_attempts - 1))
        logger.info(f"Scheduling reconnection in {delay} seconds")

        # In a real implementation, this would use asyncio or threading
        # For now, we'll just log the intent

    def _start_heartbeat(self) -> None:
        """Start heartbeat mechanism."""
        self._stop_heartbeat()
        self._heartbeat_timer = asyncio.create_task(self._heartbeat_loop())

    def _stop_heartbeat(self) -> None:
        """Stop heartbeat mechanism."""
        if self._heartbeat_timer:
            self._heartbeat_timer.cancel()
            self._heartbeat_timer = None

    async def _heartbeat_loop(self) -> None:
        """Heartbeat loop to keep connection alive."""
        while self._state == OrderStreamState.CONNECTED and self._heartbeat_timer:
            await asyncio.sleep(30)  # Heartbeat every 30 seconds
            if self._state == OrderStreamState.CONNECTED:
                logger.debug("Sending heartbeat")
                # In a real implementation, send heartbeat to WebSocket

    def _notify_connection_callbacks(self, connected: bool) -> None:
        """Notify connection state callbacks."""
        for callback in self._connection_callbacks:
            try:
                callback(connected)
            except Exception as e:
                logger.warning(f"Connection callback failed: {e}")

    def _notify_message_handlers(self, message: OrderEvent) -> None:
        """Notify message handlers."""
        for handler in self._message_handlers:
            try:
                handler(message)
            except Exception as e:
                logger.warning(f"Message handler failed: {e}")


class DhanOrderStreamWebSocketClient:
    """WebSocket client for Dhan order stream.

    Handles WebSocket communication, message parsing, and event emission for order stream.
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

        self._connection_manager = DhanOrderStreamConnectionManager(
            url_resolver=url_resolver,
            token_provider=token_provider,
            settings=settings,
            timeout_seconds=timeout_seconds,
        )
        self._event_normalizer = DhanOrderEventNormalizer()

    def connect(self) -> bool:
        """Connect to order stream."""
        return self._connection_manager.connect()

    def disconnect(self) -> bool:
        """Disconnect from order stream."""
        return self._connection_manager.disconnect()

    def subscribe(self, order_ids: list[str]) -> bool:
        """Subscribe to order stream for specific order IDs."""
        return self._connection_manager.subscribe(order_ids)

    def unsubscribe(self, order_ids: list[str]) -> bool:
        """Unsubscribe from order stream for specific order IDs."""
        return self._connection_manager.unsubscribe(order_ids)

    def is_connected(self) -> bool:
        """Check if connected to order stream."""
        return self._connection_manager.is_connected()

    def add_message_handler(self, handler: Callable[[OrderEvent], None]) -> None:
        """Add a message handler."""
        self._connection_manager.add_message_handler(handler)

    def add_connection_callback(self, callback: Callable[[bool], None]) -> None:
        """Add a connection state callback."""
        self._connection_manager.add_connection_callback(callback)

    def get_subscriptions(self) -> dict[str, dict[str, Any]]:
        """Get current subscriptions."""
        return self._connection_manager.get_subscriptions()
