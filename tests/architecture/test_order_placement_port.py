"""SS-02 ratchet — application boundary uses OrderPlacementPort."""

from __future__ import annotations

from domain.ports.broker_gateway import OrderTransportPort
from domain.ports.order_placement import OrderPlacementPort


def test_order_placement_port_is_order_transport_port() -> None:
    assert OrderPlacementPort is OrderTransportPort


def test_gateway_submit_accepts_order_placement_port() -> None:
    from application.execution.gateway_submit import make_gateway_submit_fn

    class _Gw:
        def place_order(self, symbol, exchange, side, quantity, **kwargs):
            from domain.entities import OrderResponse

            return OrderResponse(success=True, order_id="x1")

    fn = make_gateway_submit_fn(_Gw())
    assert callable(fn)


def test_invoke_place_order_routes_through_port() -> None:
    from domain.orders.requests import OrderRequest
    from domain.ports.order_placement import invoke_place_order
    from domain.types import Side

    seen: dict[str, object] = {}

    class _Gw:
        def place_order(self, symbol, exchange, side, quantity, **kwargs):
            seen.update(symbol=symbol, exchange=exchange, side=side, quantity=quantity, **kwargs)
            from domain.entities import OrderResponse

            return OrderResponse(success=True, order_id="p1")

    request = OrderRequest(
        symbol="RELIANCE",
        exchange="NSE",
        transaction_type=Side.BUY,
        quantity=5,
        order_type="LIMIT",
        price=2500,
    )
    resp = invoke_place_order(_Gw(), request)
    assert resp.success
    assert seen["symbol"] == "RELIANCE"
    assert seen["side"] == "BUY"
