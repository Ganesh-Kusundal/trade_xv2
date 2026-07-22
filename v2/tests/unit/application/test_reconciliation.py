"""ReconciliationEngine: qty mismatch → DriftSeverity.HIGH."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from application.reconciliation.engine import DriftItem, ReconciliationEngine
from domain.entities import Order, Position
from domain.enums import DriftSeverity, OrderSide, OrderStatus, OrderType, TimeInForce
from domain.value_objects import CorrelationId, InstrumentId, Money, OrderId, Price, Quantity


def _order(qty: str, order_id: str = "o1") -> Order:
    return Order(
        order_id=OrderId(value=order_id),
        instrument_id=InstrumentId(value="NSE:RELIANCE"),
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Quantity(value=Decimal(qty)),
        price=Price(value=Decimal("100")),
        time_in_force=TimeInForce.DAY,
        status=OrderStatus.FILLED,
        correlation_id=CorrelationId(value=uuid4()),
        filled_quantity=Quantity(value=Decimal(qty)),
    )


def _position(qty: str) -> Position:
    zero = Money(amount=Decimal("0"), currency="INR")
    return Position(
        instrument_id=InstrumentId(value="NSE:RELIANCE"),
        quantity=Quantity(value=Decimal(qty)),
        avg_price=Price(value=Decimal("100")),
        realized_pnl=zero,
        unrealized_pnl=zero,
    )


def test_order_qty_mismatch_is_high_drift() -> None:
    engine = ReconciliationEngine()
    drifts = engine.compare_orders([_order("100")], [_order("200")])
    assert drifts
    assert any(d.severity is DriftSeverity.HIGH for d in drifts)
    assert all(isinstance(d, DriftItem) for d in drifts)


def test_position_qty_mismatch_is_high_drift() -> None:
    engine = ReconciliationEngine()
    drifts = engine.compare_positions([_position("10")], [_position("25")])
    assert any(d.severity is DriftSeverity.HIGH for d in drifts)
