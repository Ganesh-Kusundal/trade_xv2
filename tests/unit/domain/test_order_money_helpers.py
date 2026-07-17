"""TOS-P1-004 — Order/Position use Money and Quantity fields."""

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
    assert isinstance(o.price, Money)
    assert isinstance(o.quantity, Quantity)
    assert o.price.to_decimal() == Decimal("100.5")
    assert o.quantity == 10
    assert o.price_money is o.price
    assert o.avg_price.to_decimal() == Decimal("99.0")
    assert o.remaining_quantity == 10


def test_position_helpers():
    p = Position(symbol="A", exchange="NSE", quantity=5, avg_price=Decimal("10"))
    assert isinstance(p.quantity, Quantity)
    assert isinstance(p.avg_price, Money)
    assert p.quantity == 5
    assert p.avg_price.to_decimal() == Decimal("10")
    p2 = p.with_fill(5, Decimal("12"))
    assert int(p2.quantity) == 10
