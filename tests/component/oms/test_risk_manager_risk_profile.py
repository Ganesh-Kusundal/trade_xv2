"""Tests for RiskManager.get_risk_profile() — the RiskViewPort implementation.

Proves the domain.portfolio.risk_profile.RiskProfile snapshot RiskManager
produces matches its own live config/daily_pnl/capital state, and that
reading it never mutates anything (additive, read-only per the blueprint).
"""

from __future__ import annotations

from decimal import Decimal

from application.oms import PositionManager, RiskConfig, RiskManager
from domain.portfolio.risk_profile import RiskProfile


def _make_risk_manager(capital: Decimal = Decimal("1000000")) -> RiskManager:
    return RiskManager(
        position_manager=PositionManager(),
        config=RiskConfig(
            max_daily_loss_pct=Decimal("2"),
            max_position_pct=Decimal("10"),
            max_gross_exposure_pct=Decimal("50"),
        ),
        capital_fn=lambda: capital,
    )


def test_get_risk_profile_returns_a_real_risk_profile():
    rm = _make_risk_manager()
    profile = rm.get_risk_profile()
    assert isinstance(profile, RiskProfile)


def test_get_risk_profile_matches_config():
    rm = _make_risk_manager()
    profile = rm.get_risk_profile()
    assert profile.max_daily_loss_pct == Decimal("2")
    assert profile.max_position_pct == Decimal("10")
    assert profile.max_gross_exposure_pct == Decimal("50")
    assert profile.kill_switch is False


def test_get_risk_profile_reflects_kill_switch_state():
    rm = _make_risk_manager()
    rm.set_kill_switch(True)
    profile = rm.get_risk_profile()
    assert profile.kill_switch is True


def test_get_risk_profile_reflects_daily_pnl_and_capital():
    rm = _make_risk_manager(capital=Decimal("500000"))
    rm.update_daily_pnl(Decimal("-3000"))
    profile = rm.get_risk_profile()
    assert profile.daily_pnl == Decimal("-3000")
    assert profile.capital == Decimal("500000")
    # loss budget = 500,000 * 2% = 10,000; a 3,000 loss consumes 30% -> headroom 0.7
    assert profile.headroom_pct() == Decimal("0.7")


def test_get_risk_profile_does_not_mutate_state():
    rm = _make_risk_manager()
    rm.update_daily_pnl(Decimal("-1000"))
    before = rm.daily_pnl
    rm.get_risk_profile()
    rm.get_risk_profile()
    after = rm.daily_pnl
    assert before == after


# ── RISK_LIMIT_BREACHED event wiring ──────────────────────────────────────


def test_risk_limit_breached_fires_when_threshold_crossed():
    events: list[tuple[str, dict]] = []
    rm = RiskManager(
        position_manager=PositionManager(),
        config=RiskConfig(max_daily_loss_pct=Decimal("2")),
        capital_fn=lambda: Decimal("1000000"),
        on_risk_event=lambda event_type, payload: events.append((event_type, payload)),
    )
    # loss budget = 1,000,000 * 2% = 20,000; threshold is 80% of that = 16,000
    rm.update_daily_pnl(Decimal("-10000"))  # below threshold, no event
    assert events == []
    rm.update_daily_pnl(Decimal("-17000"))  # crosses 80% -> fires
    assert len(events) == 1
    assert events[0][0] == "RISK_LIMIT_BREACHED"
    assert events[0][1]["rule"] == "max_daily_loss_pct"


def test_risk_limit_breached_is_edge_triggered_not_spammed():
    events: list[tuple[str, dict]] = []
    rm = RiskManager(
        position_manager=PositionManager(),
        config=RiskConfig(max_daily_loss_pct=Decimal("2")),
        capital_fn=lambda: Decimal("1000000"),
        on_risk_event=lambda event_type, payload: events.append((event_type, payload)),
    )
    rm.update_daily_pnl(Decimal("-17000"))  # first breach -> fires
    rm.update_daily_pnl(Decimal("-18000"))  # still breached -> must NOT fire again
    rm.update_daily_pnl(Decimal("-19000"))  # still breached -> must NOT fire again
    assert len(events) == 1


def test_risk_limit_breached_fires_again_after_recovery():
    events: list[tuple[str, dict]] = []
    rm = RiskManager(
        position_manager=PositionManager(),
        config=RiskConfig(max_daily_loss_pct=Decimal("2")),
        capital_fn=lambda: Decimal("1000000"),
        on_risk_event=lambda event_type, payload: events.append((event_type, payload)),
    )
    rm.update_daily_pnl(Decimal("-17000"))  # breach 1
    rm.update_daily_pnl(Decimal("-5000"))  # recovers below threshold
    rm.update_daily_pnl(Decimal("-18000"))  # breach 2
    assert len(events) == 2


def test_no_event_hook_means_no_crash():
    """Default on_risk_event=None must be a safe no-op, not a crash."""
    rm = RiskManager(
        position_manager=PositionManager(),
        config=RiskConfig(max_daily_loss_pct=Decimal("2")),
        capital_fn=lambda: Decimal("1000000"),
    )
    rm.update_daily_pnl(Decimal("-50000"))  # would breach if wired; must not raise
