"""C0.1 — effective notional + position multiplier PnL."""

from __future__ import annotations

from decimal import Decimal

import pytest

from domain.entities.position import Position
from domain.risk.notional import effective_notional, resolve_effective_price


@pytest.mark.unit
def test_effective_notional_uses_limit_price() -> None:
    n = effective_notional(10, Decimal("100"))
    assert n == Decimal("1000")


@pytest.mark.unit
def test_effective_notional_market_uses_ref_price() -> None:
    n = effective_notional(10, Decimal("0"), ref_price=Decimal("250"))
    assert n == Decimal("2500")


@pytest.mark.unit
def test_effective_notional_market_without_ref_is_none() -> None:
    """Must not collapse to bare quantity."""
    assert effective_notional(10, Decimal("0")) is None
    assert resolve_effective_price(0) is None


@pytest.mark.unit
def test_effective_notional_applies_multiplier() -> None:
    n = effective_notional(2, Decimal("100"), multiplier=Decimal("50"))
    assert n == Decimal("10000")


@pytest.mark.unit
def test_position_pnl_scales_with_multiplier() -> None:
    pos = Position(
        symbol="NIFTY",
        exchange="NFO",
        quantity=1,
        avg_price=Decimal("100"),
        ltp=Decimal("110"),
        multiplier=Decimal("50"),
    )
    assert pos.pnl == Decimal("500")  # 1 * 10 * 50
    pos2 = pos.with_ltp(Decimal("120"))
    assert pos2.unrealized_pnl.to_decimal() == Decimal("1000")  # 1 * 20 * 50


@pytest.mark.unit
def test_position_realized_pnl_uses_multiplier() -> None:
    pos = Position(
        symbol="NIFTY",
        exchange="NFO",
        quantity=2,
        avg_price=Decimal("100"),
        ltp=Decimal("100"),
        multiplier=Decimal("15"),
    )
    closed = pos.with_fill(-2, Decimal("110"))
    # closed 2 * 10 * 15 = 300
    assert closed.realized_pnl.to_decimal() == Decimal("300")
    assert closed.quantity == 0
