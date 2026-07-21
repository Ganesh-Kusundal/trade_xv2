"""OrderPlacementPort — single application-boundary seam for broker order I/O (SS-02).

Mirrors :class:`~domain.ports.broker_gateway.OrderTransportPort`; services and
CLI should depend on this name at the application boundary.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from domain.entities import OrderResponse
from domain.orders.requests import OrderRequest
from domain.ports.broker_gateway import OrderTransportPort

OrderPlacementPort = OrderTransportPort


def _enum_value(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def invoke_place_order(port: OrderPlacementPort, request: OrderRequest) -> OrderResponse:
    """Route an :class:`OrderRequest` through :class:`OrderPlacementPort` (SS-02)."""
    return port.place_order(
        symbol=request.symbol,
        exchange=request.exchange,
        side=_enum_value(request.transaction_type),
        quantity=request.quantity,
        price=request.price,
        order_type=_enum_value(request.order_type),
        product_type=_enum_value(request.product_type),
        validity=_enum_value(request.validity),
        trigger_price=request.trigger_price or Decimal("0"),
        correlation_id=request.correlation_id,
        disclosed_quantity=request.disclosed_quantity,
    )


__all__ = ["OrderPlacementPort", "invoke_place_order"]
