"""Unit tests for RiskProfile — public, read-only risk headroom view."""

from __future__ import annotations

from decimal import Decimal

from domain.portfolio.risk_profile import RiskProfile


def _profile(daily_pnl: Decimal, capital: Decimal = Decimal("1000000")) -> RiskProfile:
    return RiskProfile(
        max_daily_loss_pct=Decimal("2"),
        max_position_pct=Decimal("10"),
        max_gross_exposure_pct=Decimal("50"),
        kill_switch=False,
        daily_pnl=daily_pnl,
        capital=capital,
    )


def test_headroom_is_full_when_no_loss_today():
    profile = _profile(daily_pnl=Decimal("0"))
    assert profile.headroom_pct() == Decimal("1")


def test_headroom_is_full_when_daily_pnl_positive():
    profile = _profile(daily_pnl=Decimal("5000"))
    assert profile.headroom_pct() == Decimal("1")


def test_headroom_partially_consumed_by_a_loss():
    # capital=1,000,000, max_daily_loss_pct=2% -> loss budget = 20,000
    # a loss of 10,000 consumes half the budget -> headroom = 0.5
    profile = _profile(daily_pnl=Decimal("-10000"))
    assert profile.headroom_pct() == Decimal("0.5")


def test_headroom_is_zero_at_the_limit():
    # loss budget = 20,000; a loss of exactly 20,000 consumes it all
    profile = _profile(daily_pnl=Decimal("-20000"))
    assert profile.headroom_pct() == Decimal("0")


def test_headroom_does_not_go_negative_past_the_limit():
    # a loss larger than the budget must clamp at 0, not go negative
    profile = _profile(daily_pnl=Decimal("-50000"))
    assert profile.headroom_pct() == Decimal("0")


def test_headroom_is_zero_when_capital_is_zero():
    profile = _profile(daily_pnl=Decimal("-100"), capital=Decimal("0"))
    assert profile.headroom_pct() == Decimal("0")


def test_kill_switch_field_is_carried_through():
    profile = RiskProfile(
        max_daily_loss_pct=Decimal("2"),
        max_position_pct=Decimal("10"),
        max_gross_exposure_pct=Decimal("50"),
        kill_switch=True,
        daily_pnl=Decimal("0"),
        capital=Decimal("1000000"),
    )
    assert profile.kill_switch is True


def test_is_frozen():
    profile = _profile(daily_pnl=Decimal("0"))
    try:
        profile.kill_switch = True  # type: ignore[misc]
        assert False, "RiskProfile must be immutable"
    except AttributeError:
        pass
