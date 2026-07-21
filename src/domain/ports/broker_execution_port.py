"""BrokerExecutionPort — order execution operations for broker adapters.

Narrow ABC that captures the execution surface of a broker. Callers that
only need order placement (OMS, risk managers) should depend on this port
instead of the full :class:`BrokerAdapter`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from domain.entities import Balance, Holding, Order, OrderResponse, Position, Trade
    from domain.orders.requests import OrderRequest


class BrokerExecutionPort(ABC):
    """Order execution operations — the execution surface of a broker.

    This is a focused subset of :class:`BrokerAdapter`. Callers that only need
    order placement (OMS, risk managers) should depend on this port instead of
    the full broker interface.
    """

    @abstractmethod
    def place_order(self, request: OrderRequest) -> OrderResponse:
        """Place an order."""
        ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> OrderResponse:
        """Cancel an order by ID."""
        ...

    @abstractmethod
    def modify_order(self, order_id: str, **changes: object) -> OrderResponse:
        """Modify an existing order."""
        ...

    @abstractmethod
    def get_order(self, order_id: str) -> Order | None:
        """Fetch a single order by ID."""
        ...

    @abstractmethod
    def get_orderbook(self) -> list[Order]:
        """Get all open/recent orders."""
        ...

    @abstractmethod
    def get_trade_book(self) -> list[Trade]:
        """Get today's trades."""
        ...

    @abstractmethod
    def positions(self) -> list[Position]:
        """Get current positions."""
        ...

    @abstractmethod
    def holdings(self) -> list[Holding]:
        """Get current holdings."""
        ...

    @abstractmethod
    def funds(self) -> Balance:
        """Get fund limits / balance."""
        ...
