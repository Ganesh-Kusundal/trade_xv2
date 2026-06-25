"""Place order use case — risk → validation → OMS → events (REF-6)."""

from __future__ import annotations

from collections.abc import Callable

from application.oms.order_manager import OmsOrderCommand, OrderManager, OrderResult
from domain import Order, Side
from domain.ports import EventPublisher
from domain.requests import OrderRequest


class PlaceOrderUseCase:
    """Single entry point for order placement with risk and event publishing."""

    def __init__(
        self,
        order_manager: OrderManager,
        *,
        event_publisher: EventPublisher | None = None,
        submit_fn: Callable[[OmsOrderCommand], Order] | None = None,
    ) -> None:
        self._oms = order_manager
        self._events = event_publisher
        self._submit_fn = submit_fn

    def execute(self, request: OrderRequest) -> OrderResult:
        command = OmsOrderCommand(
            symbol=request.symbol,
            exchange=request.exchange,
            side=(
                request.transaction_type
                if isinstance(request.transaction_type, Side)
                else Side(str(request.transaction_type).upper())
            ),
            order_type=request.order_type,
            quantity=int(request.quantity),
            price=request.price,
            product_type=request.product_type,
            correlation_id=request.correlation_id or "",
        )
        result = self._oms.place_order(command, submit_fn=self._submit_fn)
        if self._events is not None and result.success and result.order is not None:
            self._events.publish(
                "ORDER_PLACED",
                {
                    "order_id": result.order.order_id,
                    "symbol": result.order.symbol,
                    "side": str(result.order.side),
                    "quantity": result.order.quantity,
                },
            )
        return result


__all__ = ["PlaceOrderUseCase"]
