"""Tests for SignalDTO.to_intent() — the Signal -> risk-sized OrderIntent step."""

from __future__ import annotations

from decimal import Decimal

import pytest

from domain.entities.position import Position
from domain.models.trading import SignalDTO
from domain.orders.intent import OrderIntent
from domain.portfolio.account_view import AccountView
from domain.portfolio.risk_profile import RiskProfile
from domain.types import Side


def _risk_profile(
    capital: Decimal = Decimal("1000000"),
    max_position_pct: Decimal = Decimal("10"),
) -> RiskProfile:
    return RiskProfile(
        max_daily_loss_pct=Decimal("2"),
        max_position_pct=max_position_pct,
        max_gross_exposure_pct=Decimal("50"),
        kill_switch=False,
        daily_pnl=Decimal("0"),
        capital=capital,
    )


def _signal(
    side: str = "BUY",
    signal_type: str = "BUY",
    confidence: Decimal = Decimal("0.9"),
    price: Decimal | None = Decimal("100"),
    quantity: int = 0,
) -> SignalDTO:
    return SignalDTO(
        symbol="RELIANCE",
        exchange="NSE",
        side=side,
        signal_type=signal_type,
        confidence=confidence,
        price=price,
        quantity=quantity,
    )


def test_to_intent_returns_order_intent():
    signal = _signal()
    intent = signal.to_intent(_risk_profile(), AccountView())
    assert isinstance(intent, OrderIntent)
    assert intent.symbol == "RELIANCE"
    assert intent.exchange == "NSE"
    assert intent.side == Side.BUY
    assert intent.price == Decimal("100")


def test_to_intent_sizes_from_capital_and_max_position_pct():
    # capital=1,000,000, max_position_pct=10% -> budget=100,000; price=100 -> qty=1000
    signal = _signal(price=Decimal("100"))
    intent = signal.to_intent(_risk_profile(capital=Decimal("1000000"), max_position_pct=Decimal("10")), AccountView())
    assert intent.quantity == 1000


def test_to_intent_uses_entry_price_when_price_unset():
    signal = SignalDTO(
        symbol="RELIANCE", exchange="NSE", side="BUY", signal_type="BUY",
        confidence=Decimal("0.9"), price=None, entry_price=Decimal("50"),
    )
    intent = signal.to_intent(_risk_profile(), AccountView())
    assert intent.price == Decimal("50")


def test_to_intent_explicit_quantity_is_a_ceiling_not_a_replacement():
    # risk allows 1000; signal explicitly asks for only 10 -> gets 10, not 1000.
    signal = _signal(price=Decimal("100"), quantity=10)
    intent = signal.to_intent(_risk_profile(), AccountView())
    assert intent.quantity == 10


def test_to_intent_explicit_quantity_larger_than_risk_allows_is_capped():
    # risk allows 1000; signal asks for 5000 -> capped at 1000.
    signal = _signal(price=Decimal("100"), quantity=5000)
    intent = signal.to_intent(_risk_profile(), AccountView())
    assert intent.quantity == 1000


def test_to_intent_reduces_budget_by_existing_position_pyramiding_guard():
    """The core reason `account` is a parameter: re-signaling on a symbol
    already held must not size a fresh max-position order from zero."""
    account = AccountView()
    # Already hold 800 shares at avg 100 -> existing notional = 80,000.
    account.portfolio.add_position(
        Position(symbol="RELIANCE", exchange="NSE", quantity=800, avg_price=Decimal("100"))
    )
    # Budget is 100,000 (10% of 1,000,000); 80,000 already used -> only
    # 20,000 remaining -> at price=100, that's 200 shares, not 1000.
    signal = _signal(price=Decimal("100"))
    intent = signal.to_intent(_risk_profile(), account)
    assert intent.quantity == 200


def test_to_intent_raises_when_no_remaining_room():
    account = AccountView()
    # Already at the full budget (100,000 at 10% of 1,000,000 capital).
    account.portfolio.add_position(
        Position(symbol="RELIANCE", exchange="NSE", quantity=1000, avg_price=Decimal("100"))
    )
    signal = _signal(price=Decimal("100"))
    with pytest.raises(ValueError, match="No remaining position room"):
        signal.to_intent(_risk_profile(), account)


def test_to_intent_raises_when_not_actionable():
    signal = _signal(signal_type="HOLD")
    with pytest.raises(ValueError, match="not actionable"):
        signal.to_intent(_risk_profile(), AccountView())


def test_to_intent_raises_when_no_price_available():
    signal = SignalDTO(
        symbol="RELIANCE", exchange="NSE", side="BUY", signal_type="BUY",
        confidence=Decimal("0.9"), price=None, entry_price=None,
    )
    with pytest.raises(ValueError, match="no usable price"):
        signal.to_intent(_risk_profile(), AccountView())


def test_to_intent_sell_side():
    signal = _signal(side="SELL", signal_type="SELL")
    intent = signal.to_intent(_risk_profile(), AccountView())
    assert intent.side == Side.SELL
