"""TOS-P1-004 — Order/Position Money and Quantity helper properties."""

from __future__ import annotations

from decimal import Decimal

from domain import Order, OrderType, Position, ProductType, Side
from domain.primitives import Money, Quantity


def test_order_price_money_and_quantity_vo():
    o = Order(
        order_id="1",
        symbol="A",
        exchange="NSE",
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        quantity=10,
        price=Decimal("100.5"),
        avg_price=Decimal("99.0"),
        product_type=ProductType.INTRADAY,
    )
    assert isinstance(o.price_money, Money)
    assert o.price_money.amount == Decimal("100.5")
    assert isinstance(o.quantity_vo, Quantity)
    assert o.quantity_vo.magnitude == 10
    assert o.avg_price_money.amount == Decimal("99.0")


def test_position_helpers():
    p = Position(symbol="A", exchange="NSE", quantity=5, avg_price=Decimal("10"))
    assert p.quantity_vo.magnitude == 5
    assert p.avg_price_money.amount == Decimal("10")
