"""OMS module -- Order Management System.

Provides an abstraction layer over broker order operations with optional
event bus integration for decoupled downstream processing.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, List, Optional

from brokers.common.core.domain import (
    Order,
    OrderResponse,
    OrderStatus,
    OrderType,
    Side,
)
from event_bus import EventBus, OrderFilledEvent, OrderPlacedEvent

# -- OMS ABC -----------------------------------------------------------------


class OrderManager(ABC):
    """Abstract order management interface."""

    @abstractmethod
    def submit_order(
        self,
        symbol: str,
        exchange: str,
        side: Side,
        quantity: int,
        **kwargs: Any,
    ) -> OrderResponse:
        """Place an order and return the broker response."""
        ...

    @abstractmethod
    def get_order(self, order_id: str) -> Order | None:
        """Retrieve a single order by its ID, or ``None`` if not found."""
        ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Attempt to cancel an order. Returns ``True`` on success."""
        ...

    @abstractmethod
    def get_all_orders(self) -> list[Order]:
        """Return all known orders."""
        ...


# -- Simple OMS Implementation ------------------------------------------------


class SimpleOrderManager(OrderManager):
    """Order manager that delegates to a broker-like object.

    The *broker* must expose ``place_order``, ``get_order``,
    ``cancel_order``, and ``get_orders`` methods.

    If an *event_bus* is provided, events are published on successful
    order placement and fill detection.
    """

    def __init__(self, broker: Any, event_bus: EventBus | None = None) -> None:
        self._broker = broker
        self._event_bus = event_bus

    # -- public API ----------------------------------------------------------

    def submit_order(
        self,
        symbol: str,
        exchange: str,
        side: Side,
        quantity: int,
        **kwargs: Any,
    ) -> OrderResponse:
        response: OrderResponse = self._broker.place_order(
            symbol=symbol,
            exchange=exchange,
            side=side,
            quantity=quantity,
            **kwargs,
        )
        if response.success and self._event_bus is not None:
            order = self._broker.get_order(response.order_id)
            if order is not None:
                self._event_bus.publish(OrderPlacedEvent(order=order, source="SimpleOrderManager"))
        return response

    def get_order(self, order_id: str) -> Order | None:
        return self._broker.get_order(order_id)

    def cancel_order(self, order_id: str) -> bool:
        return self._broker.cancel_order(order_id)

    def get_all_orders(self) -> list[Order]:
        return self._broker.get_orders()
