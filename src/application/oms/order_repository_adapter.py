"""OMS-backed order repository adapter (REF-15)."""

from __future__ import annotations

from collections.abc import Callable

from application.oms.order_manager import OmsOrderCommand, OrderManager, OrderResult
from domain import Order, OrderResponse, OrderStatus, OrderType, ProductType, Side
from domain.orders.requests import OrderRequest


def _request_to_command(request: OrderRequest) -> OmsOrderCommand:
    return OmsOrderCommand(
        symbol=request.symbol,
        exchange=request.exchange,
        side=(
            request.transaction_type
            if isinstance(request.transaction_type, Side)
            else Side(str(request.transaction_type).upper())
        ),
        order_type=(
            request.order_type
            if isinstance(request.order_type, OrderType)
            else OrderType(str(request.order_type).upper())
        ),
        quantity=int(request.quantity),
        price=request.price,
        product_type=(
            request.product_type
            if isinstance(request.product_type, ProductType)
            else ProductType(str(request.product_type).upper())
        ),
        correlation_id=request.correlation_id or "",
    )


def _result_to_response(result: OrderResult) -> OrderResponse:
    order = result.order
    if order is None:
        return OrderResponse(success=result.success, message=result.error or "")
    return OrderResponse(
        success=result.success,
        order_id=order.order_id,
        message=result.error or "",
        status=order.status,
    )


def request_to_command(request: OrderRequest) -> OmsOrderCommand:
    return _request_to_command(request)


class OrderManagerRepository:
    """Adapts :class:`OrderManager` to :class:`OrderRepository`."""

    def __init__(
        self,
        order_manager: OrderManager,
        *,
        submit_fn: Callable[[OmsOrderCommand], Order] | None = None,
        cancel_fn: Callable[[str], bool] | None = None,
    ) -> None:
        self._oms = order_manager
        self._submit_fn = submit_fn
        self._cancel_fn = cancel_fn

    def get_orders(
        self,
        *,
        symbol: str | None = None,
        status: OrderStatus | None = None,
    ) -> list[Order]:
        return self._oms.get_orders(symbol=symbol, status=status)

    def get_order(self, order_id: str) -> Order | None:
        return self._oms.get_order(order_id)

    def place_order(self, request: OrderRequest) -> OrderResponse:
        result = self._oms.place_order(_request_to_command(request), submit_fn=self._submit_fn)
        return _result_to_response(result)

    def cancel_order(self, order_id: str) -> OrderResponse:
        result = self._oms.cancel_order(order_id, cancel_fn=self._cancel_fn)
        return _result_to_response(result)

    def place_command(
        self,
        command: OmsOrderCommand,
        *,
        submit_fn: Callable[[OmsOrderCommand], Order] | None = None,
    ) -> OrderResult:
        """Advanced placement with optional per-call submit_fn."""
        return self._oms.place_order(command, submit_fn=submit_fn or self._submit_fn)

    def cancel_with_fn(
        self,
        order_id: str,
        *,
        cancel_fn: Callable[[str], bool] | None = None,
    ) -> OrderResult:
        return self._oms.cancel_order(order_id, cancel_fn=cancel_fn or self._cancel_fn)


__all__ = ["OrderManagerRepository", "request_to_command"]
