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

    last_kwargs: dict | None = None

    def place_order(
        self,
        symbol: str,
        exchange: str = "NSE",
        side: str = "BUY",
        quantity: int = 1,
        price: Decimal = Decimal("0"),
        order_type: str = "MARKET",
        product_type: str = "INTRADAY",
        validity: str = "DAY",
        trigger_price: Decimal = Decimal("0"),
        correlation_id: str | None = None,
        disclosed_quantity: int = 0,
    ) -> "OrderResponse":
        from domain.entities import OrderResponse

        _FakeGateway.last_kwargs = {
            "symbol": symbol,
            "exchange": exchange,
            "disclosed_quantity": disclosed_quantity,
        }
        return OrderResponse(
            success=True,
            order_id="PAPER-1",
            message="ok",
            status="PLACED",
        )


def test_invoke_place_order_disclosed_quantity_no_type_error():
    """invoke_place_order(disclosed_quantity=5) must not raise TypeError."""
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
    assert _FakeGateway.last_kwargs is not None
    assert _FakeGateway.last_kwargs["disclosed_quantity"] == 5
    assert _FakeGateway.last_kwargs["symbol"] == "RELIANCE"


@pytest.mark.parametrize(
    "cls_path,cls_name",
    [
        ("brokers.paper.paper_gateway", "PaperGateway"),
        ("brokers.dhan.wire", "DhanWireAdapter"),
        ("brokers.upstox.wire", "UpstoxWireAdapter"),
    ],
)
def test_place_order_signature_accepts_disclosed_quantity(cls_path: str, cls_name: str):
    """Every gateway place_order signature must accept disclosed_quantity kwarg."""
    mod = __import__(cls_path, fromlist=[cls_name])
    cls = getattr(mod, cls_name)
    sig = inspect.signature(cls.place_order)
    assert "disclosed_quantity" in sig.parameters, (
        f"{cls_name}.place_order is missing 'disclosed_quantity' parameter"
    )
    param = sig.parameters["disclosed_quantity"]
    assert param.default == 0, (
        f"{cls_name}.place_order discosed_quantity default should be 0, got {param.default}"
    )
