"""Gateway cancel/modify callables for OMS lifecycle (Live FillSource surface)."""

from __future__ import annotations

from collections.abc import Callable

from domain.entities import OrderResponse
from domain.orders.requests import ModifyOrderRequest


def make_gateway_cancel_fn(gateway: object) -> Callable[[str], bool]:
    """Return OMS ``cancel_fn`` delegating to gateway ``cancel_order``."""

    def cancel(order_id: str) -> bool:
        fn = getattr(gateway, "cancel_order", None)
        if fn is None:
            return True
        response = fn(order_id)
        if isinstance(response, OrderResponse):
            return bool(response.success)
        return bool(response)

    return cancel


def make_gateway_modify_fn(gateway: object) -> Callable[[ModifyOrderRequest], OrderResponse | None]:
    """Return OMS ``modify_fn`` delegating to gateway ``modify_order``."""

    def modify(request: ModifyOrderRequest) -> OrderResponse | None:
        fn = getattr(gateway, "modify_order", None)
        if fn is None:
            return None
        changes: dict[str, object] = {}
        if request.quantity is not None:
            changes["quantity"] = request.quantity
        if request.price is not None:
            changes["price"] = request.price
        if request.order_type is not None:
            changes["order_type"] = request.order_type
        if request.product_type is not None:
            changes["product_type"] = request.product_type
        response = fn(request.order_id, **changes)
        if isinstance(response, OrderResponse):
            return response
        return OrderResponse(
            success=bool(response),
            order_id=request.order_id,
            message="" if response else "broker modify failed",
        )

    return modify


def gateway_capabilities(gateway: object) -> object | None:
    """Return broker capabilities when the gateway exposes them."""
    caps = getattr(gateway, "capabilities", None)
    if callable(caps):
        return caps()
    list_caps = getattr(gateway, "list_capabilities", None)
    if callable(list_caps):
        return list_caps()
    return None


__all__ = [
    "gateway_capabilities",
    "make_gateway_cancel_fn",
    "make_gateway_modify_fn",
]
