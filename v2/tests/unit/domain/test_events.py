"""Domain events are immutable (frozen)."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from domain.enums import OrderSide, RiskLevel
from domain.events import (
    DomainEvent,
    OrderCancelled,
    OrderFilled,
    OrderPlaced,
    OrderRejected,
    PositionChanged,
    RiskBreached,
)
from domain.value_objects import (
    ComponentId,
    CorrelationId,
    InstrumentId,
    Money,
    OrderId,
    Price,
    Quantity,
)


def test_message_base_is_frozen() -> None:
    evt = DomainEvent(
        timestamp=datetime.now(UTC),
        correlation_id=uuid4(),
        source=ComponentId(value="oms"),
    )
    with pytest.raises(Exception):
        evt.timestamp = datetime.now(UTC)  # type: ignore[misc]


def test_order_events_immutable() -> None:
    cid = CorrelationId(value=uuid4())
    placed = OrderPlaced(
        timestamp=datetime.now(UTC),
        correlation_id=cid.value,
        source=None,
        order_id=OrderId(value="o1"),
        instrument_id=InstrumentId.parse("NSE:RELIANCE"),
        side=OrderSide.BUY,
        quantity=Quantity(value=Decimal("10")),
    )
    filled = OrderFilled(
        timestamp=datetime.now(UTC),
        correlation_id=cid.value,
        source=None,
        order_id=OrderId(value="o1"),
        instrument_id=InstrumentId.parse("NSE:RELIANCE"),
        side=OrderSide.BUY,
        filled_qty=Quantity(value=Decimal("10")),
        avg_price=Price(value=Decimal("2500")),
    )
    cancelled = OrderCancelled(
        timestamp=datetime.now(UTC),
        correlation_id=None,
        source=None,
        order_id=OrderId(value="o1"),
        reason="user",
    )
    rejected = OrderRejected(
        timestamp=datetime.now(UTC),
        correlation_id=None,
        source=None,
        order_id=OrderId(value="o1"),
        reason="risk",
        venue_code="RISK",
    )
    for evt in (placed, filled, cancelled, rejected):
        with pytest.raises(Exception):
            evt.order_id = OrderId(value="x")  # type: ignore[misc]


def test_portfolio_and_risk_events_immutable() -> None:
    pos = PositionChanged(
        timestamp=datetime.now(UTC),
        correlation_id=None,
        source=None,
        instrument_id=InstrumentId.parse("NSE:RELIANCE"),
        quantity=Quantity(value=Decimal("10")),
        avg_price=Price(value=Decimal("2500")),
        realized_pnl=Money(amount=Decimal("0"), currency="INR"),
        unrealized_pnl=Money(amount=Decimal("100"), currency="INR"),
    )
    risk = RiskBreached(
        timestamp=datetime.now(UTC),
        correlation_id=uuid4(),
        source=None,
        level=RiskLevel.CRITICAL,
        reason="max_loss",
        instrument_id=InstrumentId.parse("NSE:RELIANCE"),
    )
    with pytest.raises(Exception):
        pos.quantity = Quantity(value=Decimal("0"))  # type: ignore[misc]
    with pytest.raises(Exception):
        risk.level = RiskLevel.INFO  # type: ignore[misc]
