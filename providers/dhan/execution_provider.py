"""Dhan ExecutionProvider — implements the ExecutionProvider port.

Wraps DhanGateway and normalizes its outputs into domain objects.
The user layer never imports this module directly.
"""

from __future__ import annotations

import warnings
from typing import Any

from domain.entities.account import Balance
from domain.entities.order import Order, OrderResponse
from domain.entities.position import Holding, Position
from domain.orders.requests import ModifyOrderRequest, OrderRequest
from domain.ports.protocols import ExecutionProvider


class DhanExecutionProvider(ExecutionProvider):
    """Adapts DhanGateway to the ExecutionProvider port.

    This is the ONLY place where Dhan's gateway meets the domain
    for order execution. The public Instrument API never imports this.

    .. deprecated::
        Phase 9.3 of the Instrument-Centric SDK Redesign. Execution is being
        consolidated into a unified ``DhanBrokerAdapter`` (data + execution).
        Prefer the broker adapter exposed via ``BrokerSession``.
    """

    def __init__(self, gateway: Any) -> None:
        warnings.warn(
            "providers.dhan.execution_provider.DhanExecutionProvider is "
            "deprecated; execution is moving into the unified broker adapter "
            "(brokers.dhan.adapter). See Instrument-Centric SDK Redesign, Phase 9.3.",
            DeprecationWarning,
            stacklevel=2,
        )
        self._gw = gateway

    @property
    def name(self) -> str:
        return "dhan"

    def place_order(self, request: OrderRequest) -> OrderResponse:
        """Place an order via Dhan gateway."""
        try:
            return self._gw.place_order(
                symbol=request.symbol,
                exchange=request.exchange,
                side=request.transaction_type,
                quantity=request.quantity,
                price=request.price,
                order_type=request.order_type,
                product_type=request.product_type,
                trigger_price=getattr(request, "trigger_price", None),
            )
        except Exception as e:
            return OrderResponse(
                order_id="",
                status="REJECTED",
                text=str(e),
            )

    def cancel_order(self, order_id: str) -> OrderResponse:
        """Cancel an order via Dhan gateway."""
        try:
            return self._gw.cancel_order(order_id)
        except Exception as e:
            return OrderResponse(
                order_id=order_id,
                status="REJECTED",
                text=str(e),
            )

    def modify_order(self, request: ModifyOrderRequest) -> OrderResponse:
        """Modify an order via Dhan gateway."""
        try:
            return self._gw.modify_order(
                order_id=request.order_id,
                quantity=request.quantity,
                price=request.price,
                trigger_price=getattr(request, "trigger_price", None),
            )
        except Exception as e:
            return OrderResponse(
                order_id=request.order_id,
                status="REJECTED",
                text=str(e),
            )

    def get_order_book(self) -> list[Order]:
        """Get all orders from Dhan gateway."""
        try:
            return self._gw.get_orderbook()
        except Exception:
            return []

    def get_positions(self) -> list[Position]:
        """Get positions from Dhan gateway."""
        try:
            return self._gw.positions()
        except Exception:
            return []

    def get_holdings(self) -> list[Holding]:
        """Get holdings from Dhan gateway."""
        try:
            return self._gw.holdings()
        except Exception:
            return []

    def get_funds(self) -> Balance:
        """Get fund limits from Dhan gateway."""
        try:
            return self._gw.funds()
        except Exception:
            return Balance()
