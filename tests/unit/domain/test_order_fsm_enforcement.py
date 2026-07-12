import pytest
from datetime import datetime, timezone
from decimal import Decimal

from domain.entities.order import Order
from domain.enums import OrderStatus
from domain.state_machine import IllegalTransitionError
from domain.types import Side, OrderType, ProductType, Validity


def _make_order(status: OrderStatus) -> Order:
    return Order(
        order_id="test-1", symbol="RELIANCE", exchange="NSE",
        side=Side.BUY, order_type=OrderType.LIMIT, quantity=10,
        price=2500.0, trigger_price=0.0, product_type=ProductType.CNC,
        validity=Validity.DAY, status=status, timestamp=datetime.now(timezone.utc),
    )


def test_legal_transition_open_to_filled():
    order = _make_order(OrderStatus.OPEN)
    result = order.with_status(OrderStatus.FILLED)
    assert result.status == OrderStatus.FILLED


def test_legal_transition_open_to_partially_filled():
    order = _make_order(OrderStatus.OPEN)
    result = order.with_status(OrderStatus.PARTIALLY_FILLED)
    assert result.status == OrderStatus.PARTIALLY_FILLED


def test_legal_transition_open_to_cancelled():
    order = _make_order(OrderStatus.OPEN)
    result = order.with_status(OrderStatus.CANCELLED)
    assert result.status == OrderStatus.CANCELLED


def test_illegal_transition_filled_to_open_raises():
    order = _make_order(OrderStatus.FILLED)
    with pytest.raises(IllegalTransitionError):
        order.with_status(OrderStatus.OPEN)


def test_illegal_transition_cancelled_to_filled_raises():
    order = _make_order(OrderStatus.CANCELLED)
    with pytest.raises(IllegalTransitionError):
        order.with_status(OrderStatus.FILLED)


def test_illegal_transition_rejected_to_open_raises():
    order = _make_order(OrderStatus.REJECTED)
    with pytest.raises(IllegalTransitionError):
        order.with_status(OrderStatus.OPEN)


def test_same_status_is_legal():
    order = _make_order(OrderStatus.OPEN)
    result = order.with_status(OrderStatus.OPEN)
    assert result.status == OrderStatus.OPEN


def test_unknown_can_transition_to_open():
    order = _make_order(OrderStatus.UNKNOWN)
    result = order.with_status(OrderStatus.OPEN)
    assert result.status == OrderStatus.OPEN
