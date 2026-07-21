"""invoke_place_order passes disclosed_quantity through to the port."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from domain import OrderResponse
from domain.orders.requests import OrderRequest
from domain.ports.order_placement import invoke_place_order


def test_invoke_place_order_forwards_disclosed_quantity():
    port = MagicMock()
    port.place_order.return_value = OrderResponse.ok(order_id="1")

    req = OrderRequest(
        symbol="RELIANCE",
        exchange="NSE",
        transaction_type="BUY",
        quantity=100,
        order_type="LIMIT",
        product_type="INTRADAY",
        validity="DAY",
        price=Decimal("2500"),
        disclosed_quantity=25,
    )
    invoke_place_order(port, req)

    port.place_order.assert_called_once()
    assert port.place_order.call_args.kwargs["disclosed_quantity"] == 25
