"""Tier 2-D: typed domain-event wrappers.

Each test asserts a single guarantee about the typed wrappers
(``OrderFilledEvent``, ``QuoteUpdatedEvent``, ``PositionClosedEvent``) and the
``to_typed_event`` dispatcher. These replace raw ``event.payload.get(...)``
access with type-checked accessors.

Run: PYTHONPATH=src python -m pytest tests/unit/domain/events -q
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

from domain.entities.trade import Trade
from domain.events.types import (
    DomainEvent,
    EventType,
    OrderFilledEvent,
    PositionClosedEvent,
    QuoteUpdatedEvent,
    to_typed_event,
)
from domain.types import Side


def _make_trade(trade_id: str = "T-1") -> Trade:
    return Trade(
        trade_id=trade_id,
        order_id="O-1",
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        quantity=10,
        price=Decimal("2500"),
    )


def _raw_event(event_type: str, payload: dict) -> DomainEvent:
    return DomainEvent(
        event_type=event_type,
        timestamp=datetime.now(timezone.utc),
        payload=payload,
        symbol=payload.get("symbol"),
        event_id="evt-x",
        correlation_id="corr-x",
    )


class TestOrderFilledEventFromDomainEvent:
    def test_round_trips_for_trade_filled(self):
        trade = _make_trade()
        event = _raw_event(EventType.TRADE_FILLED.value, {"trade": trade})
        typed = OrderFilledEvent.from_domain_event(event)
        assert typed.trade is trade
        assert typed.event_type == EventType.TRADE_FILLED.value

    def test_round_trips_for_trade(self):
        trade = _make_trade()
        event = _raw_event(EventType.TRADE.value, {"trade": trade})
        typed = OrderFilledEvent.from_domain_event(event)
        assert typed.trade is trade
        assert typed.event_type == EventType.TRADE.value

    def test_round_trips_for_trade_applied(self):
        trade = _make_trade()
        event = _raw_event(EventType.TRADE_APPLIED.value, {"trade": trade})
        typed = OrderFilledEvent.from_domain_event(event)
        assert typed.trade is trade
        assert typed.event_type == EventType.TRADE_APPLIED.value

    def test_accessor_type_is_trade(self):
        trade = _make_trade()
        event = _raw_event(EventType.TRADE_FILLED.value, {"trade": trade})
        typed = OrderFilledEvent.from_domain_event(event)
        assert isinstance(typed.trade, Trade)
        assert typed.trade.trade_id == "T-1"

    def test_delegates_event_metadata(self):
        trade = _make_trade()
        event = _raw_event(EventType.TRADE_FILLED.value, {"trade": trade})
        typed = OrderFilledEvent.from_domain_event(event)
        assert typed.event_id == "evt-x"
        assert typed.correlation_id == "corr-x"

    def test_raises_without_trade(self):
        event = _raw_event(EventType.TRADE_FILLED.value, {})
        try:
            OrderFilledEvent.from_domain_event(event)
        except ValueError as exc:
            assert "must contain Trade" in str(exc)
        else:
            raise AssertionError("expected ValueError")

    def test_raises_on_wrong_type(self):
        event = _raw_event(EventType.TRADE_FILLED.value, {"trade": "nope"})
        try:
            OrderFilledEvent.from_domain_event(event)
        except ValueError as exc:
            assert "must contain Trade" in str(exc)
        else:
            raise AssertionError("expected ValueError")


class TestQuoteUpdatedEventFromDomainEvent:
    def test_round_trips_required_keys(self):
        event = _raw_event(
            EventType.QUOTE_UPDATED.value,
            {"symbol": "RELIANCE", "exchange": "NSE", "ltp": Decimal("2500.5")},
        )
        typed = QuoteUpdatedEvent.from_domain_event(event)
        assert typed.symbol == "RELIANCE"
        assert typed.exchange == "NSE"
        assert typed.ltp == Decimal("2500.5")
        assert typed.event_type == EventType.QUOTE_UPDATED.value

    def test_coerces_optional_numeric_keys(self):
        event = _raw_event(
            EventType.QUOTE_UPDATED.value,
            {
                "symbol": "RELIANCE",
                "exchange": "NSE",
                "ltp": 2500.5,
                "bid": "2499.0",
                "ask": "2501.0",
                "volume": 1000,
            },
        )
        typed = QuoteUpdatedEvent.from_domain_event(event)
        assert typed.ltp == Decimal("2500.5")
        assert typed.bid == Decimal("2499.0")
        assert typed.ask == Decimal("2501.0")
        assert typed.volume == 1000

    def test_optional_keys_default_to_none(self):
        event = _raw_event(
            EventType.QUOTE_UPDATED.value,
            {"symbol": "RELIANCE", "exchange": "NSE", "ltp": Decimal("10")},
        )
        typed = QuoteUpdatedEvent.from_domain_event(event)
        assert typed.bid is None
        assert typed.ask is None
        assert typed.volume is None

    def test_accessor_types_are_correct(self):
        event = _raw_event(
            EventType.QUOTE_UPDATED.value,
            {"symbol": "RELIANCE", "exchange": "NSE", "ltp": Decimal("10")},
        )
        typed = QuoteUpdatedEvent.from_domain_event(event)
        assert isinstance(typed.symbol, str)
        assert isinstance(typed.exchange, str)
        assert isinstance(typed.ltp, Decimal)

    def test_raises_on_missing_required_keys(self):
        event = _raw_event(EventType.QUOTE_UPDATED.value, {"symbol": "RELIANCE"})
        try:
            QuoteUpdatedEvent.from_domain_event(event)
        except ValueError as exc:
            assert "must contain symbol" in str(exc)
        else:
            raise AssertionError("expected ValueError")

    def test_raises_on_non_numeric_ltp(self):
        event = _raw_event(
            EventType.QUOTE_UPDATED.value,
            {"symbol": "RELIANCE", "exchange": "NSE", "ltp": "not-a-price"},
        )
        try:
            QuoteUpdatedEvent.from_domain_event(event)
        except ValueError as exc:
            assert "non-numeric" in str(exc)
        else:
            raise AssertionError("expected ValueError")


class TestPositionClosedEventFromDomainEvent:
    def test_round_trips_required_keys(self):
        event = _raw_event(
            EventType.POSITION_CLOSED.value,
            {"symbol": "TCS", "realized_pnl": Decimal("125.50")},
        )
        typed = PositionClosedEvent.from_domain_event(event)
        assert typed.symbol == "TCS"
        assert typed.realized_pnl == Decimal("125.50")
        assert typed.event_type == EventType.POSITION_CLOSED.value

    def test_coerces_optional_keys(self):
        event = _raw_event(
            EventType.POSITION_CLOSED.value,
            {
                "symbol": "TCS",
                "realized_pnl": "-50.0",
                "quantity": 25,
                "avg_price": "2000.25",
            },
        )
        typed = PositionClosedEvent.from_domain_event(event)
        assert typed.realized_pnl == Decimal("-50.0")
        assert typed.quantity == 25
        assert typed.avg_price == Decimal("2000.25")

    def test_accessor_types_are_correct(self):
        event = _raw_event(
            EventType.POSITION_CLOSED.value,
            {"symbol": "TCS", "realized_pnl": Decimal("1")},
        )
        typed = PositionClosedEvent.from_domain_event(event)
        assert isinstance(typed.symbol, str)
        assert isinstance(typed.realized_pnl, Decimal)

    def test_raises_on_missing_symbol(self):
        event = _raw_event(EventType.POSITION_CLOSED.value, {"realized_pnl": Decimal("1")})
        try:
            PositionClosedEvent.from_domain_event(event)
        except ValueError as exc:
            assert "must contain symbol" in str(exc)
        else:
            raise AssertionError("expected ValueError")


class TestToTypedEventDispatch:
    def test_dispatches_trade_filled_to_order_filled(self):
        trade = _make_trade()
        event = _raw_event(EventType.TRADE_FILLED.value, {"trade": trade})
        result = to_typed_event(event)
        assert isinstance(result, OrderFilledEvent)
        assert result.trade is trade

    def test_dispatches_trade_to_order_filled(self):
        trade = _make_trade()
        event = _raw_event(EventType.TRADE.value, {"trade": trade})
        result = to_typed_event(event)
        assert isinstance(result, OrderFilledEvent)

    def test_dispatches_trade_applied_to_order_filled(self):
        trade = _make_trade()
        event = _raw_event(EventType.TRADE_APPLIED.value, {"trade": trade})
        result = to_typed_event(event)
        assert isinstance(result, OrderFilledEvent)

    def test_dispatches_quote_updated(self):
        event = _raw_event(
            EventType.QUOTE_UPDATED.value,
            {"symbol": "RELIANCE", "exchange": "NSE", "ltp": Decimal("10")},
        )
        result = to_typed_event(event)
        assert isinstance(result, QuoteUpdatedEvent)

    def test_dispatches_position_closed(self):
        event = _raw_event(
            EventType.POSITION_CLOSED.value,
            {"symbol": "TCS", "realized_pnl": Decimal("1")},
        )
        result = to_typed_event(event)
        assert isinstance(result, PositionClosedEvent)

    def test_returns_original_for_unknown_type(self):
        event = _raw_event("SOME_FUTURE_EVENT", {"foo": "bar"})
        result = to_typed_event(event)
        assert result is event

    def test_returns_original_when_payload_invalid(self):
        # QUOTE_UPDATED whose payload fails validation -> fall back to raw.
        event = _raw_event(EventType.QUOTE_UPDATED.value, {"symbol": "RELIANCE"})
        result = to_typed_event(event)
        assert result is event

    def test_unknown_type_with_raw_dict_payload(self):
        # A raw dict payload (not a DomainEvent) of an unknown type — must not
        # crash; to_typed_event only intercepts by event_type.
        fake = MagicMock()
        fake.event_type = "TOTALLY_UNKNOWN"
        result = to_typed_event(fake)
        assert result is fake
