"""Domain entities — frozen dataclasses with Order FSM."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from domain.enums import (
    AssetClass,
    ExchangeId,
    InstrumentType,
    OrderSide,
    OrderStatus,
    OrderType,
    TimeInForce,
)
from domain.entities import Order, Position, Trade, Instrument, Quote, Bar
from domain.value_objects import (
    AccountId,
    CorrelationId,
    InstrumentId,
    Money,
    OrderId,
    Price,
    Quantity,
    TimeFrame,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


def _position() -> Position:
    return Position(
        instrument_id=InstrumentId.parse("NSE:RELIANCE"),
        quantity=Quantity(value=Decimal("10")),
        avg_price=Price(value=Decimal("2500")),
        realized_pnl=Money(amount=Decimal("500"), currency="INR"),
        unrealized_pnl=Money(amount=Decimal("200"), currency="INR"),
    )


def _trade() -> Trade:
    return Trade(
        trade_id="t1",
        order_id=OrderId(value="o1"),
        instrument_id=InstrumentId.parse("NSE:RELIANCE"),
        price=Price(value=Decimal("2500")),
        quantity=Quantity(value=Decimal("10")),
        side=OrderSide.BUY,
        timestamp=datetime(2025, 1, 1, 10, 0, 0),
    )


def _instrument() -> Instrument:
    return Instrument(
        instrument_id=InstrumentId.parse("NSE:RELIANCE"),
        symbol="RELIANCE",
        exchange=ExchangeId.NSE,
        asset_class=AssetClass.EQUITY,
        currency="INR",
        instrument_type=InstrumentType.EQUITY,
    )


def _instrument_option() -> Instrument:
    return Instrument(
        instrument_id=InstrumentId.parse("NSE:RELIANCE2500CE"),
        symbol="RELIANCE2500CE",
        exchange=ExchangeId.NSE,
        asset_class=AssetClass.DERIVATIVE,
        currency="INR",
        instrument_type=InstrumentType.OPTION,
        underlying_id=InstrumentId.parse("NSE:RELIANCE"),
        strike=Decimal("2500"),
        expiry=datetime(2025, 12, 31),
        option_type="CALL",
    )


# ---------------------------------------------------------------------------
# Order — frozen
# ---------------------------------------------------------------------------

class TestOrderFrozen:
    def test_order_is_frozen(self) -> None:
        order = _order()
        with pytest.raises(FrozenInstanceError):
            order.status = OrderStatus.SUBMITTED  # type: ignore[misc]

    def test_order_cannot_mutate_any_field(self) -> None:
        order = _order()
        with pytest.raises(FrozenInstanceError):
            order.order_id = OrderId(value="o2")  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Order FSM — valid transitions
# ---------------------------------------------------------------------------

class TestOrderFSMValid:
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
    def test_legal_transitions(self, start: OrderStatus, end: OrderStatus) -> None:
        order = _order(start)
        new_order = order.transition_to(end)
        assert new_order.status == end
        assert order.status == start  # original unchanged (frozen)

    def test_transition_returns_new_instance(self) -> None:
        order = _order()
        new_order = order.transition_to(OrderStatus.SUBMITTED)
        assert new_order is not order
        assert order.status == OrderStatus.PENDING
        assert new_order.status == OrderStatus.SUBMITTED


# ---------------------------------------------------------------------------
# Order FSM — illegal transitions
# ---------------------------------------------------------------------------

class TestOrderFSMIllegal:
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
    def test_illegal_transitions_raise(self, start: OrderStatus, end: OrderStatus) -> None:
        order = _order(start)
        with pytest.raises(ValueError, match="illegal transition"):
            order.transition_to(end)
        assert order.status == start  # unchanged

    def test_terminal_states_have_no_outgoing(self) -> None:
        for terminal in (OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED, OrderStatus.UNKNOWN):
            order = _order(terminal)
            for target in OrderStatus:
                if target != terminal:
                    with pytest.raises(ValueError):
                        order.transition_to(target)


# ---------------------------------------------------------------------------
# Position — frozen
# ---------------------------------------------------------------------------

class TestPositionFrozen:
    def test_position_is_frozen(self) -> None:
        pos = _position()
        with pytest.raises(FrozenInstanceError):
            pos.quantity = Quantity(value=Decimal("20"))  # type: ignore[misc]

    def test_position_fields(self) -> None:
        pos = _position()
        assert pos.instrument_id == InstrumentId.parse("NSE:RELIANCE")
        assert pos.quantity == Quantity(value=Decimal("10"))
        assert pos.avg_price == Price(value=Decimal("2500"))


# ---------------------------------------------------------------------------
# Trade — frozen
# ---------------------------------------------------------------------------

class TestTradeFrozen:
    def test_trade_is_frozen(self) -> None:
        t = _trade()
        with pytest.raises(FrozenInstanceError):
            t.price = Price(value=Decimal("2600"))  # type: ignore[misc]

    def test_trade_fields(self) -> None:
        t = _trade()
        assert t.trade_id == "t1"
        assert t.side == OrderSide.BUY


# ---------------------------------------------------------------------------
# Instrument — frozen
# ---------------------------------------------------------------------------

class TestInstrumentFrozen:
    def test_instrument_is_frozen(self) -> None:
        inst = _instrument()
        with pytest.raises(FrozenInstanceError):
            inst.symbol = "OTHER"  # type: ignore[misc]

    def test_equity_instrument(self) -> None:
        inst = _instrument()
        assert inst.underlying_id is None
        assert inst.strike is None
        assert inst.expiry is None
        assert inst.option_type is None

    def test_option_instrument(self) -> None:
        inst = _instrument_option()
        assert inst.underlying_id == InstrumentId.parse("NSE:RELIANCE")
        assert inst.strike == Decimal("2500")
        assert inst.expiry == datetime(2025, 12, 31)
        assert inst.option_type == "CALL"
        assert inst.instrument_type == InstrumentType.OPTION
        assert inst.asset_class == AssetClass.DERIVATIVE
