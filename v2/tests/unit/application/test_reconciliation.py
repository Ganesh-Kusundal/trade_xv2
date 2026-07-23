"""ReconciliationEngine tests — pure compare functions, no I/O."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from application.reconciliation.engine import DriftItem, ReconciliationEngine
from domain.entities import Account, Order, Position
from domain.enums import (
    DriftSeverity,
    OrderSide,
    OrderStatus,
    OrderType,
    TimeInForce,
)
from domain.value_objects import (
    AccountId,
    CorrelationId,
    InstrumentId,
    Money,
    OrderId,
    Price,
    Quantity,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

instrument = InstrumentId.parse("NSE:RELIANCE")


def _order(
    order_id: str = "o1",
    qty: str = "100",
    price: str = "100",
    status: OrderStatus = OrderStatus.FILLED,
    filled_qty: str | None = None,
) -> Order:
    return Order(
        order_id=OrderId(value=order_id),
        instrument_id=instrument,
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Quantity(value=Decimal(qty)),
        price=Price(value=Decimal(price)),
        time_in_force=TimeInForce.DAY,
        status=status,
        correlation_id=CorrelationId(value=uuid4()),
        filled_quantity=Quantity(value=Decimal(filled_qty or qty)),
    )


def _position(
    inst: str = "NSE:RELIANCE",
    qty: str = "10",
    avg_price: str = "100",
) -> Position:
    zero = Money(amount=Decimal("0"), currency="INR")
    return Position(
        instrument_id=InstrumentId.parse(inst),
        quantity=Quantity(value=Decimal(qty)),
        avg_price=Price(value=Decimal(avg_price)),
        realized_pnl=zero,
        unrealized_pnl=zero,
    )


def _account(
    aid: str = "acc1",
    balance: str = "100000",
    equity: str = "100000",
    margin: str = "0",
) -> Account:
    return Account(
        account_id=AccountId(value=aid),
        balance=Money(amount=Decimal(balance), currency="INR"),
        margin=Money(amount=Decimal(margin), currency="INR"),
        equity=Money(amount=Decimal(equity), currency="INR"),
    )


# ---------------------------------------------------------------------------
# compare_orders
# ---------------------------------------------------------------------------


class TestCompareOrdersMissing:
    def test_missing_broker_order_is_high(self) -> None:
        """Local has an order that broker does not → HIGH."""
        engine = ReconciliationEngine()
        local = [_order("o1")]
        broker: list[Order] = []

        drifts = engine.compare_orders(local, broker)

        assert len(drifts) == 1
        d = drifts[0]
        assert d.severity is DriftSeverity.HIGH
        assert "missing broker" in d.reason
        assert d.local is not None
        assert d.remote is None

    def test_missing_local_order_is_high(self) -> None:
        """Broker has an order that local does not → HIGH."""
        engine = ReconciliationEngine()
        local: list[Order] = []
        broker = [_order("o1")]

        drifts = engine.compare_orders(local, broker)

        assert len(drifts) == 1
        d = drifts[0]
        assert d.severity is DriftSeverity.HIGH
        assert "missing local" in d.reason
        assert d.local is None
        assert d.remote is not None


class TestCompareOrdersMismatch:
    def test_quantity_mismatch_is_high(self) -> None:
        engine = ReconciliationEngine()
        local = [_order("o1", qty="100")]
        broker = [_order("o1", qty="200")]

        drifts = engine.compare_orders(local, broker)

        assert any(d.severity is DriftSeverity.HIGH and "quantity" in d.reason for d in drifts)

    def test_filled_quantity_mismatch_is_high(self) -> None:
        engine = ReconciliationEngine()
        local = [_order("o1", filled_qty="100")]
        broker = [_order("o1", filled_qty="50")]

        drifts = engine.compare_orders(local, broker)

        assert any(
            d.severity is DriftSeverity.HIGH and "filled_quantity" in d.reason for d in drifts
        )

    def test_price_drift_is_medium(self) -> None:
        engine = ReconciliationEngine()
        local = [_order("o1", price="100")]
        broker = [_order("o1", price="101")]

        drifts = engine.compare_orders(local, broker, price_tolerance=Decimal("0.01"))

        assert any(d.severity is DriftSeverity.MEDIUM and "price drift" in d.reason for d in drifts)

    def test_status_lag_is_low(self) -> None:
        engine = ReconciliationEngine()
        local = [_order("o1", status=OrderStatus.SUBMITTED)]
        broker = [_order("o1", status=OrderStatus.FILLED)]

        drifts = engine.compare_orders(local, broker)

        assert any(d.severity is DriftSeverity.LOW and "status" in d.reason for d in drifts)

    def test_multiple_orders_detected(self) -> None:
        engine = ReconciliationEngine()
        local = [_order("o1"), _order("o2")]
        broker = [_order("o1", qty="999"), _order("o3")]

        drifts = engine.compare_orders(local, broker)

        # o1 qty mismatch + o2 missing from broker + o3 missing from local
        assert len(drifts) >= 3


class TestCompareOrdersNoDrift:
    def test_identical_orders_no_drift(self) -> None:
        engine = ReconciliationEngine()
        local = [_order("o1"), _order("o2")]
        broker = [_order("o1"), _order("o2")]

        drifts = engine.compare_orders(local, broker)

        assert drifts == []


# ---------------------------------------------------------------------------
# compare_positions
# ---------------------------------------------------------------------------


class TestComparePositions:
    def test_quantity_mismatch_is_high(self) -> None:
        engine = ReconciliationEngine()
        local = [_position(qty="10")]
        broker = [_position(qty="25")]

        drifts = engine.compare_positions(local, broker)

        assert any(d.severity is DriftSeverity.HIGH and "quantity" in d.reason for d in drifts)

    def test_avg_price_drift_is_medium(self) -> None:
        engine = ReconciliationEngine()
        local = [_position(avg_price="100")]
        broker = [_position(avg_price="101")]

        drifts = engine.compare_positions(local, broker, price_tolerance=Decimal("0.01"))

        assert any(d.severity is DriftSeverity.MEDIUM for d in drifts)

    def test_missing_local_position_is_high(self) -> None:
        engine = ReconciliationEngine()
        local: list[Position] = []
        broker = [_position()]

        drifts = engine.compare_positions(local, broker)

        assert len(drifts) == 1
        assert drifts[0].severity is DriftSeverity.HIGH
        assert "missing local" in drifts[0].reason

    def test_missing_broker_position_is_high(self) -> None:
        engine = ReconciliationEngine()
        local = [_position()]
        broker: list[Position] = []

        drifts = engine.compare_positions(local, broker)

        assert len(drifts) == 1
        assert drifts[0].severity is DriftSeverity.HIGH
        assert "missing broker" in drifts[0].reason

    def test_identical_positions_no_drift(self) -> None:
        engine = ReconciliationEngine()
        local = [_position()]
        broker = [_position()]

        assert engine.compare_positions(local, broker) == []


# ---------------------------------------------------------------------------
# compare_funds
# ---------------------------------------------------------------------------


class TestCompareFunds:
    def test_balance_mismatch_is_high(self) -> None:
        engine = ReconciliationEngine()
        local = _account(balance="100000")
        broker = _account(balance="99000")

        drifts = engine.compare_funds(local, broker)

        assert len(drifts) == 1
        assert drifts[0].severity is DriftSeverity.HIGH
        assert "balance" in drifts[0].reason

    def test_equity_drift_is_medium(self) -> None:
        engine = ReconciliationEngine()
        local = _account(balance="100000", equity="100000")
        broker = _account(balance="100000", equity="99500")

        drifts = engine.compare_funds(local, broker)

        assert any(d.severity is DriftSeverity.MEDIUM and "equity" in d.reason for d in drifts)

    def test_identical_funds_no_drift(self) -> None:
        engine = ReconciliationEngine()
        local = _account()
        broker = _account()

        assert engine.compare_funds(local, broker) == []


# ---------------------------------------------------------------------------
# DriftItem structure
# ---------------------------------------------------------------------------


class TestDriftItem:
    def test_drift_item_fields(self) -> None:
        engine = ReconciliationEngine()
        drifts = engine.compare_orders([_order("o1")], [])

        d = drifts[0]
        assert isinstance(d, DriftItem)
        assert isinstance(d.severity, DriftSeverity)
        assert isinstance(d.reason, str)
        assert len(d.reason) > 0
