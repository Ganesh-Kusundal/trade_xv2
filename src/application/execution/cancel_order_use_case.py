"""Cancel order use case (REF-6)."""

from __future__ import annotations

from collections.abc import Callable

from application.oms.order_manager import OrderManager, OrderResult
from domain.ports import EventPublisher
from application.observability import trace_operation


class CancelOrderUseCase:
    """Single entry point for order cancellation."""

    def __init__(
        self,
        order_manager: OrderManager,
        *,
        event_publisher: EventPublisher | None = None,
        cancel_fn: Callable[[str], bool] | None = None,
    ) -> None:
        self._oms = order_manager
        self._events = event_publisher
        self._cancel_fn = cancel_fn

    @trace_operation("cancel_order")
    def execute(self, order_id: str) -> OrderResult:
        result = self._oms.cancel_order(order_id, cancel_fn=self._cancel_fn)
        if self._events is not None and result.success:
            self._events.publish("ORDER_CANCELLED", {"order_id": order_id})
        return result


__all__ = ["CancelOrderUseCase"]
