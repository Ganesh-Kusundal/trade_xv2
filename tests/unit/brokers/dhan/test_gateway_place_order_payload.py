"""DhanWireAdapter.place_order must pass BrokerOrderPayload to OrdersAdapter."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from brokers.dhan.wire import DhanWireAdapter
from domain.entities.order import OrderResponse
from domain.enums import OrderStatus, OrderType, Side
from domain.models.dtos import BrokerOrderPayload


def test_place_order_builds_broker_order_payload() -> None:
    conn = MagicMock()
    conn.orders.place_order.return_value = OrderResponse(
        success=True, order_id="SBX-1", status=OrderStatus.OPEN
    )
    gw = DhanWireAdapter(conn)

    result = gw.place_order(
        symbol="RELIANCE",
        exchange="NSE",
        side="BUY",
        quantity=1,
        order_type="LIMIT",
        product_type="INTRADAY",
        price=Decimal("1000"),
        correlation_id="corr123",
    )

    assert result.success is True
    assert result.order_id == "SBX-1"
    payload = conn.orders.place_order.call_args.args[0]
    assert isinstance(payload, BrokerOrderPayload)
    assert payload.symbol == "RELIANCE"
    assert payload.transaction_type == Side.BUY
    assert payload.order_type == OrderType.LIMIT
    assert payload.price == Decimal("1000")
    assert payload.correlation_id == "corr123"
