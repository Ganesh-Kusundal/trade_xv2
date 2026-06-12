"""Order stream adapter for Dhan.

Implements order stream provider interface for real-time order event tracking.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable
from typing import Any

from brokers.common.api.ports import OrderUpdateListener
from brokers.common.core.models import Order
from brokers.dhan.auth.context import DhanAdapterContext
from brokers.dhan.websocket.order_stream import (
    DhanOrderStreamWebSocketClient,
    OrderEvent,
)

logger = logging.getLogger(__name__)


class DhanOrderStreamProvider:
    """Trade_J-style order stream provider for Dhan.

    Provides real-time order event tracking including:
    - Order placed
    - Order modified
    - Order cancelled
    - Order filled (partial/full)
    - Order status updates
    - Order rejection

    Integrates with existing broker connection and manages listener lifecycle.
    """

    def __init__(self, context: DhanAdapterContext) -> None:
        self._context = context
        self._websocket_client: DhanOrderStreamWebSocketClient | None = None
        self._listeners: list[OrderUpdateListener] = []
        self._order_subscriptions: dict[str, dict[str, Any]] = {}
        self._connection_callbacks: list[Callable[[bool], None]] = []
        self._connection_task: asyncio.Task | None = None

        # Initialize WebSocket client
        self._websocket_client = DhanOrderStreamWebSocketClient(
            url_resolver=self._context.url_resolver,
            token_provider=self._context.token_provider,
            settings=self._context.settings,
            timeout_seconds=self._context._timeout_seconds,
        )

    @property
    def websocket_client(self) -> DhanOrderStreamWebSocketClient:
        """Get or create WebSocket client for order stream."""
        if self._websocket_client is None:
            self._websocket_client = DhanOrderStreamWebSocketClient(
                url_resolver=self._context.url_resolver,
                token_provider=self._context.token_provider,
                settings=self._context.settings,
                timeout_seconds=self._context._timeout_seconds,
            )
        return self._websocket_client

    def subscribe_order_stream(self, order_ids: list[str]) -> bool:
        """Subscribe to order stream for specific order IDs."""
        if not self._websocket_client:
            logger.error("WebSocket client not initialized")
            return False

        if not self._websocket_client.is_connected():
            logger.error("WebSocket client not connected")
            return False

        success = self._websocket_client.subscribe(order_ids)
        if success:
            for order_id in order_ids:
                self._order_subscriptions[order_id] = {
                    "order_id": order_id,
                    "subscribed_at": asyncio.get_event_loop().time(),
                }

        return success

    def unsubscribe_order_stream(self, order_ids: list[str]) -> bool:
        """Unsubscribe from order stream for specific order IDs."""
        if not self._websocket_client:
            return False

        success = self._websocket_client.unsubscribe(order_ids)
        if success:
            for order_id in order_ids:
                self._order_subscriptions.pop(order_id, None)

        return success

    def get_order_stream_status(self) -> dict[str, Any]:
        """Get order stream status."""
        status = {
            "connected": self._websocket_client is not None
            and self._websocket_client.is_connected(),
            "subscriptions": len(self._order_subscriptions),
            "listeners": len(self._listeners),
        }

        if self._websocket_client:
            status["websocket_subscriptions"] = self._websocket_client.get_subscriptions()

        return status

    def add_order_listener(self, listener: OrderUpdateListener) -> None:
        """Add an order event listener."""
        self._listeners.append(listener)
        logger.debug(f"Added order listener, total listeners: {len(self._listeners)}")

    def remove_order_listener(self, listener: OrderUpdateListener) -> None:
        """Remove an order event listener."""
        if listener in self._listeners:
            self._listeners.remove(listener)
            logger.debug(f"Removed order listener, total listeners: {len(self._listeners)}")

    def add_connection_callback(self, callback: Callable[[bool], None]) -> None:
        """Add a connection state callback."""
        self._connection_callbacks.append(callback)

    def connect(self) -> bool:
        """Connect to order stream."""
        if not self._websocket_client:
            return False

        if self._connection_task and not self._connection_task.done():
            return True

        try:
            self._connection_task = asyncio.create_task(self._maintain_connection())
            return True
        except RuntimeError:
            # No event loop running
            return False

    def disconnect(self) -> bool:
        """Disconnect from order stream."""
        if self._websocket_client:
            self._websocket_client.disconnect()

        if self._connection_task and not self._connection_task.done():
            with contextlib.suppress(RuntimeError):
                self._connection_task.cancel()
            self._connection_task = None

        return True

    async def _maintain_connection(self) -> None:
        """Maintain WebSocket connection and handle reconnections."""
        if not self._websocket_client:
            return

        self._websocket_client.add_connection_callback(self._on_connection_state_changed)
        self._websocket_client.add_message_handler(self._on_order_event)

        while True:
            try:
                if not self._websocket_client.is_connected():
                    logger.info("Connecting to order stream WebSocket")
                    self._websocket_client.connect()

                await asyncio.sleep(30)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in connection maintenance: {e}")
                await asyncio.sleep(5)

    def _on_connection_state_changed(self, connected: bool) -> None:
        """Handle connection state changes."""
        for callback in self._connection_callbacks:
            try:
                callback(connected)
            except Exception as e:
                logger.warning(f"Connection callback failed: {e}")

        logger.info(f"Order stream connection state changed: {connected}")

    def _on_order_event(self, event: OrderEvent) -> None:
        """Handle incoming order events."""
        logger.debug(f"Received order event: {event.event_type} for order {event.order_id}")

        # Normalize event to Order domain object
        order = self._normalize_event_to_order(event)

        # Notify all listeners
        for listener in self._listeners:
            try:
                listener.on_order_update(order)
            except Exception as e:
                logger.warning(f"Order listener failed: {e}")

    def _normalize_event_to_order(self, event: OrderEvent) -> Order:
        """Normalize order event to Order domain object."""
        from brokers.common.core.enums import ExchangeSegment, OrderStatus

        order_data = event.order_data

        return Order(
            order_id=event.order_id,
            correlation_id=order_data.get("correlationId"),
            exchange_segment=ExchangeSegment.NSE,
            transaction_type=order_data.get("transactionType", "BUY"),
            quantity=order_data.get("quantity", 0),
            price=order_data.get("price", 0),
            trigger_price=order_data.get("triggerPrice"),
            order_type=order_data.get("orderType", "LIMIT"),
            product_type=order_data.get("productType", "CNC"),
            validity=order_data.get("validity", "DAY"),
            status=OrderStatus.PENDING,
            filled_quantity=order_data.get("filledQuantity", order_data.get("filled_qty", 0)),
            remaining_quantity=order_data.get(
                "remainingQuantity", order_data.get("pendingQuantity", 0)
            ),
            average_price=order_data.get("averagePrice"),
            order_timestamp=event.timestamp,
            exchange_order_id=order_data.get("exchangeOrderId"),
            reject_reason=order_data.get("rejectReason"),
        )
