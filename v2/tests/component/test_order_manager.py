"""OrderManager: PENDING→SUBMITTED→FILLED via Order FSM; illegal rejected."""

from decimal import Decimal
from uuid import uuid4

import pytest

from application.oms.order_manager import OrderManager
from application.oms.trading_cache import TradingCache
from domain.enums import OrderSide, OrderStatus, OrderType, TimeInForce
from domain.value_objects import (
    CorrelationId,
    InstrumentId,
    OrderId,
    Price,
    Quantity,
)


def _manager() -> tuple[OrderManager, TradingCache]:
    cache = TradingCache()
    return OrderManager(cache), cache


def test_pending_submitted_filled_path() -> None:
    om, cache = _manager()
    order = om.create_pending(
        order_id=OrderId(value="o1"),
        instrument_id=InstrumentId.parse("NSE:RELIANCE"),
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Quantity(value=Decimal("10")),
        price=Price(value=Decimal("2500")),
        time_in_force=TimeInForce.DAY,
        correlation_id=CorrelationId(value=uuid4()),
    )
    assert order.status is OrderStatus.PENDING
    assert cache.get_order(OrderId(value="o1")) is order

    om.apply_submitted(OrderId(value="o1"))
    assert cache.get_order(OrderId(value="o1")).status is OrderStatus.SUBMITTED

    om.apply_fill(OrderId(value="o1"), filled_qty=Quantity(value=Decimal("10")))
    filled = cache.get_order(OrderId(value="o1"))
    assert filled.status is OrderStatus.FILLED
    assert filled.filled_quantity.value == Decimal("10")


def test_illegal_transition_via_manager_raises() -> None:
    om, cache = _manager()
    om.create_pending(
        order_id=OrderId(value="o2"),
        instrument_id=InstrumentId.parse("NSE:TCS"),
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Quantity(value=Decimal("5")),
        price=None,
        time_in_force=TimeInForce.DAY,
        correlation_id=CorrelationId(value=uuid4()),
    )
    with pytest.raises(ValueError, match="illegal transition"):
        om.apply_fill(OrderId(value="o2"), filled_qty=Quantity(value=Decimal("5")))
    assert cache.get_order(OrderId(value="o2")).status is OrderStatus.PENDING


def test_cancel_reject_unknown_from_submitted() -> None:
    om, _ = _manager()
    for method, oid, status in (
        (om.apply_cancel, "oc", OrderStatus.CANCELLED),
        (om.apply_reject, "or", OrderStatus.REJECTED),
        (om.apply_unknown, "ou", OrderStatus.UNKNOWN),
    ):
        om.create_pending(
            order_id=OrderId(value=oid),
            instrument_id=InstrumentId.parse("NSE:INFY"),
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            quantity=Quantity(value=Decimal("1")),
            price=Price(value=Decimal("100")),
            time_in_force=TimeInForce.DAY,
            correlation_id=CorrelationId(value=uuid4()),
        )
        om.apply_submitted(OrderId(value=oid))
        method(OrderId(value=oid))
        assert om.get_order(OrderId(value=oid)).status is status
