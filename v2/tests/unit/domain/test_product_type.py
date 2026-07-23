"""ProductType — broker-agnostic order product vocabulary."""

from __future__ import annotations

import uuid
from decimal import Decimal

from domain.commands import PlaceOrderCommand
from domain.enums import OrderSide, OrderType, ProductType, TimeInForce
from domain.value_objects import CorrelationId, InstrumentId, Price, Quantity


def test_product_type_values() -> None:
    assert ProductType.INTRADAY == "INTRADAY"
    assert ProductType.DELIVERY == "DELIVERY"
    assert ProductType.MARGIN == "MARGIN"
    assert ProductType.MTF == "MTF"
    assert ProductType.COVER_ORDER == "COVER_ORDER"


def test_place_order_command_accepts_product_type() -> None:
    cmd = PlaceOrderCommand(
        instrument_id=InstrumentId.equity("NSE", "RELIANCE"),
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Quantity(value=Decimal("1")),
        price=None,
        time_in_force=TimeInForce.DAY,
        correlation_id=CorrelationId(value=uuid.uuid4()),
        product_type=ProductType.DELIVERY,
    )
    assert cmd.product_type == ProductType.DELIVERY


def test_place_order_command_product_type_defaults_none() -> None:
    cmd = PlaceOrderCommand(
        instrument_id=InstrumentId.equity("NSE", "RELIANCE"),
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Quantity(value=Decimal("1")),
        price=None,
        time_in_force=TimeInForce.DAY,
        correlation_id=CorrelationId(value=uuid.uuid4()),
    )
    assert cmd.product_type is None
