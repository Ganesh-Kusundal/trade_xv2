"""OMS modify_order integration via OmsService."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from cli.services.oms_service import OmsService
from domain.entities import OrderResponse


def test_modify_order_routes_through_gateway_with_oms_context() -> None:
    gw = MagicMock()
    gw.modify_order.return_value = OrderResponse.ok(order_id="ORD-1", message="ok")
    ctx = MagicMock()
    svc = OmsService(gateway=gw, trading_context=ctx)
    assert svc.modify_order("ORD-1", price=Decimal("100")) is True
    gw.modify_order.assert_called_once_with("ORD-1", price=Decimal("100"))
