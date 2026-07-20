"""OrderServicePort — application spine for order admission + lifecycle.

Domain Session / Instrument depend on this protocol, never on OrderManager
or brokers. The application layer implements it by wiring Risk → OMS →
ExecutionProvider for place / cancel / modify.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from domain.orders.intent import OrderIntent
    from domain.orders.requests import ModifyOrderRequest
    from domain.ports.protocols import OrderResult


@runtime_checkable
class OrderServicePort(Protocol):
    """Admit and manage orders via OMS (never bare ExecutionProvider).

    Implementations must run pre-trade risk (when configured) and OMS
    lifecycle before any broker transport call.
    """

    def place(self, intent: OrderIntent) -> OrderResult:
        """Admit *intent* and return a domain :class:`OrderResult`."""
        ...

    def cancel(self, order_id: str) -> OrderResult:
        """Cancel an open order by id (OMS book + broker transport)."""
        ...

    def modify(self, request: ModifyOrderRequest) -> OrderResult:
        """Modify quantity/price of an open order via OMS."""
        ...
