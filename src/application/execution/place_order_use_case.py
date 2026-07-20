"""Place order use case — risk → validation → OMS → events (REF-6).

Canonical application entry for order placement. Prefer this (directly or via
``ExecutionService`` / ``tradex.Session``) from UI and API layers instead of
calling ``OrderManager.place_order`` or broker gateways bare.
"""

from __future__ import annotations

from application.execution.spine import place_order_spine
from application.oms.order_command_mapper import order_request_to_oms_command
from application.oms.order_manager import OmsOrderCommand, OrderManager, OrderResult
from domain.orders.requests import OrderRequest
from domain.ports import EventPublisher
from domain.ports.execution_target import ExecutionTarget


class PlaceOrderUseCase:
    """Single entry point for order placement with risk and event publishing.

    UI/API should route here (or through ``ExecutionService.place_order`` which
    delegates here in live mode) so risk, idempotency, and event publish stay
    on one spine.
    """

    def __init__(
        self,
        order_manager: OrderManager,
        *,
        execution_target: ExecutionTarget,
        event_publisher: EventPublisher | None = None,
    ) -> None:
        if execution_target is None:
            raise TypeError("execution_target is required")
        self._oms = order_manager
        self._events = event_publisher
        self._target = execution_target

    def execute(self, request: OrderRequest | OmsOrderCommand) -> OrderResult:
        if isinstance(request, OmsOrderCommand):
            command = request
        else:
            command = order_request_to_oms_command(request)
        result = place_order_spine(self._oms, command, self._target)
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
