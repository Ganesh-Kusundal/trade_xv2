"""P0.3: invoke_place_order must accept disclosed_quantity without TypeError."""

from __future__ import annotations

import inspect
from decimal import Decimal

import pytest

from domain.enums import OrderType, ProductType, Side, Validity
from domain.orders.requests import OrderRequest
from domain.ports.order_placement import invoke_place_order


class _FakeGateway:
    """Records the last place_order call and returns a success OrderResponse."""

    last_request: OrderRequest | None = None

    def place_order(self, request: OrderRequest) -> "OrderResponse":
        from domain.entities import OrderResponse

        _FakeGateway.last_request = request
        return OrderResponse(
            success=True,
            order_id="PAPER-1",
            message="ok",
            status="PLACED",
        )


def test_invoke_place_order_disclosed_quantity_no_type_error():
    """invoke_place_order forwards OrderRequest including disclosed_quantity."""
    gateway = _FakeGateway()
    request = OrderRequest(
        symbol="RELIANCE",
        exchange="NSE",
        transaction_type=Side.BUY,
        quantity=10,
        price=Decimal("2500"),
        order_type=OrderType.LIMIT,
        product_type=ProductType.INTRADAY,
        validity=Validity.DAY,
        disclosed_quantity=5,
    )
    response = invoke_place_order(gateway, request)  # must not raise

    assert response.success is True
    assert _FakeGateway.last_request is not None
    assert _FakeGateway.last_request.disclosed_quantity == 5
    assert _FakeGateway.last_request.symbol == "RELIANCE"


@pytest.mark.parametrize(
    "cls_path,cls_name",
    [
        ("brokers.providers.paper.paper_gateway", "PaperGateway"),
        ("brokers.providers.dhan.wire", "DhanWireAdapter"),
        ("brokers.providers.upstox.wire", "UpstoxWireAdapter"),
    ],
)
def test_place_order_accepts_order_request_with_disclosed_quantity(
    cls_path: str, cls_name: str
):
    """Every gateway place_order takes OrderRequest (disclosed_quantity on request)."""
    mod = __import__(cls_path, fromlist=[cls_name])
    cls = getattr(mod, cls_name)
    sig = inspect.signature(cls.place_order)
    params = list(sig.parameters)
    assert params[0] == "self"
    assert params[1] == "request", (
        f"{cls_name}.place_order must take OrderRequest as 'request', got {params}"
    )
    # Field lives on OrderRequest, not as a place_order kwarg.
    assert "disclosed_quantity" in OrderRequest.__dataclass_fields__
