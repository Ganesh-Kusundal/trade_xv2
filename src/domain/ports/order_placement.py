"""OrderPlacementPort — single application-boundary seam for broker order I/O (SS-02).

Mirrors :class:`~domain.ports.broker_gateway.OrderTransportPort`; services and
CLI should depend on this name at the application boundary.
"""

from __future__ import annotations

from domain.entities import OrderResponse
from domain.orders.requests import OrderRequest
from domain.ports.broker_gateway import OrderTransportPort

OrderPlacementPort = OrderTransportPort


def invoke_place_order(port: OrderPlacementPort, request: OrderRequest) -> OrderResponse:
    """Route an :class:`OrderRequest` through :class:`OrderPlacementPort` (SS-02)."""
    return port.place_order(request)


__all__ = ["OrderPlacementPort", "invoke_place_order"]
