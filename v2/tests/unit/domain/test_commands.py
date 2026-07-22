"""Commands: PlaceOrderCommand requires correlation_id."""

from decimal import Decimal
from uuid import uuid4

import pytest

from domain.commands import CancelOrderCommand, ModifyOrderCommand, PlaceOrderCommand
from domain.enums import OrderSide, OrderType, TimeInForce
from domain.value_objects import CorrelationId, InstrumentId, OrderId, Price, Quantity


def test_place_order_requires_correlation_id() -> None:
    with pytest.raises((TypeError, ValueError)):
        PlaceOrderCommand(  # type: ignore[call-arg]
            instrument_id=InstrumentId(value="NSE:RELIANCE"),
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Quantity(value=Decimal("1")),
            price=None,
            time_in_force=TimeInForce.DAY,
        )


def test_place_order_rejects_none_correlation_id() -> None:
    with pytest.raises((TypeError, ValueError)):
        PlaceOrderCommand(
            instrument_id=InstrumentId(value="NSE:RELIANCE"),
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Quantity(value=Decimal("1")),
            price=Price(value=Decimal("100")),
            time_in_force=TimeInForce.DAY,
            correlation_id=None,  # type: ignore[arg-type]
        )


def test_place_order_with_correlation_id() -> None:
    cmd = PlaceOrderCommand(
        instrument_id=InstrumentId(value="NSE:RELIANCE"),
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Quantity(value=Decimal("10")),
        price=Price(value=Decimal("2500")),
        time_in_force=TimeInForce.DAY,
        correlation_id=CorrelationId(value=uuid4()),
    )
    with pytest.raises(Exception):
        cmd.quantity = Quantity(value=Decimal("1"))  # type: ignore[misc]


def test_cancel_and_modify_frozen() -> None:
    cancel = CancelOrderCommand(order_id=OrderId(value="o1"), reason="user")
    modify = ModifyOrderCommand(
        order_id=OrderId(value="o1"),
        new_quantity=Quantity(value=Decimal("5")),
        new_price=Price(value=Decimal("2490")),
    )
    with pytest.raises(Exception):
        cancel.reason = "x"  # type: ignore[misc]
    with pytest.raises(Exception):
        modify.new_price = Price(value=Decimal("1"))  # type: ignore[misc]
