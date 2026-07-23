"""Order FSM: legal transitions succeed; illegal raise."""

from decimal import Decimal
from uuid import uuid4

import pytest

from domain.enums import OrderSide, OrderStatus, OrderType, TimeInForce
from domain.entities import Order
from domain.value_objects import CorrelationId, InstrumentId, OrderId, Price, Quantity


def _order(status: OrderStatus = OrderStatus.PENDING) -> Order:
    return Order(
        order_id=OrderId(value="o1"),
        instrument_id=InstrumentId.parse("NSE:RELIANCE"),
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Quantity(value=Decimal("10")),
        price=Price(value=Decimal("2500")),
        time_in_force=TimeInForce.DAY,
        status=status,
        correlation_id=CorrelationId(value=uuid4()),
    )


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (OrderStatus.PENDING, OrderStatus.SUBMITTED),
        (OrderStatus.SUBMITTED, OrderStatus.PARTIALLY_FILLED),
        (OrderStatus.SUBMITTED, OrderStatus.FILLED),
        (OrderStatus.SUBMITTED, OrderStatus.CANCELLED),
        (OrderStatus.SUBMITTED, OrderStatus.REJECTED),
        (OrderStatus.SUBMITTED, OrderStatus.UNKNOWN),
        (OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED),
        (OrderStatus.PARTIALLY_FILLED, OrderStatus.CANCELLED),
        (OrderStatus.PARTIALLY_FILLED, OrderStatus.UNKNOWN),
    ],
)
def test_legal_transitions(start: OrderStatus, end: OrderStatus) -> None:
    order = _order(start)
    new_order = order.transition_to(end)
    assert new_order.status == end
    assert order.status == start


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (OrderStatus.PENDING, OrderStatus.FILLED),
        (OrderStatus.PENDING, OrderStatus.CANCELLED),
        (OrderStatus.PENDING, OrderStatus.REJECTED),
        (OrderStatus.FILLED, OrderStatus.CANCELLED),
        (OrderStatus.CANCELLED, OrderStatus.SUBMITTED),
        (OrderStatus.REJECTED, OrderStatus.PENDING),
        (OrderStatus.UNKNOWN, OrderStatus.FILLED),
        (OrderStatus.FILLED, OrderStatus.PARTIALLY_FILLED),
    ],
)
def test_illegal_transitions_raise(start: OrderStatus, end: OrderStatus) -> None:
    order = _order(start)
    with pytest.raises(ValueError):
        order.transition_to(end)
    assert order.status == start
