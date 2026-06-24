"""FakeBrokerGateway — test double for broker gateway port.

Provides an in-memory implementation of OrderTransportPort for unit testing
application-layer code without real broker connections.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from domain.entities import OrderResponse


class FakeBrokerGateway:
    """In-memory fake broker gateway for testing.

    Implements OrderTransportPort protocol. Records all place_order calls
    and returns configurable responses.
    """

    def __init__(self) -> None:
        self._orders: list[dict[str, Any]] = []
        self._order_counter: int = 0
        self._default_response: OrderResponse | None = None
        self._responses: dict[str, OrderResponse] = {}

    def place_order(
        self,
        symbol: str,
        exchange: str,
        side: str,
        quantity: int,
        price: Decimal = Decimal("0"),
        order_type: str = "MARKET",
        product_type: str = "INTRADAY",
        correlation_id: str | None = None,
        transport_only: bool = False,
    ) -> OrderResponse:
        """Record the order and return a configurable response."""
        self._order_counter += 1
        order_id = f"FAKE-{self._order_counter:06d}"

        self._orders.append(
            {
                "order_id": order_id,
                "symbol": symbol,
                "exchange": exchange,
                "side": side,
                "quantity": quantity,
                "price": price,
                "order_type": order_type,
                "product_type": product_type,
                "correlation_id": correlation_id,
                "transport_only": transport_only,
            }
        )

        # Return configured response or default success
        if symbol in self._responses:
            return self._responses[symbol]
        if self._default_response is not None:
            return self._default_response

        return OrderResponse.ok(order_id=order_id)

    def set_default_response(self, response: OrderResponse) -> None:
        """Set the default response for all place_order calls."""
        self._default_response = response

    def set_response_for_symbol(self, symbol: str, response: OrderResponse) -> None:
        """Set a specific response for a given symbol."""
        self._responses[symbol] = response

    def get_orders(self) -> list[dict[str, Any]]:
        """Return all recorded orders."""
        return list(self._orders)

    def get_order_count(self) -> int:
        """Return the number of orders placed."""
        return self._order_counter

    def clear(self) -> None:
        """Clear all recorded orders and reset counter."""
        self._orders.clear()
        self._order_counter = 0
