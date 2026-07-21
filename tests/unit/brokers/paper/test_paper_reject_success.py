"""Tests that PaperGateway.place_order returns success=False for REJECTED orders."""

from tests.support.order_request_factory import make_order_request as _order_request
from decimal import Decimal
from unittest.mock import patch

from brokers.providers.paper.paper_gateway import PaperGateway
from domain.entities import Order
from domain.enums import OrderStatus, OrderType, ProductType, Side


def _make_order(status: OrderStatus) -> Order:
    return Order(
        order_id="test-001",
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        quantity=1,
        order_type=OrderType.MARKET,
        product_type=ProductType.INTRADAY,
        status=status,
    )


def test_place_order_rejected_returns_success_false():
    gw = PaperGateway(initial_capital=Decimal("100000"))
    with patch.object(gw._orders, "place_order", return_value=_make_order(OrderStatus.REJECTED)):
        resp = gw.place_order(_order_request(symbol="RELIANCE", quantity=1))
    assert resp.success is False
    assert resp.status == OrderStatus.REJECTED


def test_place_order_open_returns_success_true():
    gw = PaperGateway(initial_capital=Decimal("100000"))
    with patch.object(gw._orders, "place_order", return_value=_make_order(OrderStatus.OPEN)):
        resp = gw.place_order(_order_request(symbol="RELIANCE", quantity=1))
    assert resp.success is True


def test_place_order_filled_returns_success_true():
    gw = PaperGateway(initial_capital=Decimal("100000"))
    with patch.object(gw._orders, "place_order", return_value=_make_order(OrderStatus.FILLED)):
        resp = gw.place_order(_order_request(symbol="RELIANCE", quantity=1))
    assert resp.success is True


