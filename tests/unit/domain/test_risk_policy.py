"""Unit tests for domain risk policy objects."""

from __future__ import annotations

from decimal import Decimal

from domain.risk.policy import (
    ConcentrationLimit,
    DailyLossCircuitBreaker,
    GrossExposureLimit,
    KillSwitch,
    OrderNotionalLimit,
    RiskGate,
    RiskResult,
    check_daily_loss_pct,
    check_paper_daily_loss,
)


# ── OrderNotionalLimit ──────────────────────────────────────────────

def test_notional_within_limit():
    assert OrderNotionalLimit(max_notional=Decimal("500000")).check(Decimal("400000")).approved


def test_notional_exceeds_limit():
    r = OrderNotionalLimit(max_notional=Decimal("500000")).check(Decimal("600000"))
    assert not r.approved
    assert "exceeds" in r.reason


def test_notional_at_limit():
    assert OrderNotionalLimit(max_notional=Decimal("500000")).check(Decimal("500000")).approved


# ── ConcentrationLimit ──────────────────────────────────────────────

def test_concentration_within_limit():
    r = ConcentrationLimit(max_pct=Decimal("0.20")).check(Decimal("100000"), Decimal("1000000"))
    assert r.approved


def test_concentration_exceeds_limit():
    r = ConcentrationLimit(max_pct=Decimal("0.20")).check(Decimal("300000"), Decimal("1000000"))
    assert not r.approved
    assert "concentration" in r.reason


def test_concentration_empty_portfolio():
    assert ConcentrationLimit().check(Decimal("100000"), Decimal("0")).approved


# ── GrossExposureLimit ─────────────────────────────────────────────

def test_gross_exposure_within_limit():
    r = GrossExposureLimit(max_pct=Decimal("1.0")).check(Decimal("900000"), Decimal("1000000"))
    assert r.approved


def test_gross_exposure_exceeds_limit():
    r = GrossExposureLimit(max_pct=Decimal("1.0")).check(Decimal("1100000"), Decimal("1000000"))
    assert not r.approved


def test_gross_exposure_zero_capital():
    assert not GrossExposureLimit().check(Decimal("100"), Decimal("0")).approved


# ── DailyLossCircuitBreaker ────────────────────────────────────────

def test_circuit_breaker_within_limit():
    b = DailyLossCircuitBreaker(daily_loss_limit=Decimal("100000"))
    b.record_pnl(Decimal("-50000"))
    assert b.check().approved


def test_circuit_breaker_trips_on_loss():
    b = DailyLossCircuitBreaker(daily_loss_limit=Decimal("100000"))
    b.record_pnl(Decimal("-100001"))
    assert not b.check().approved
    assert "breached" in b.check().reason


def test_circuit_breaker_reset():
    b = DailyLossCircuitBreaker(daily_loss_limit=Decimal("100000"))
    b.record_pnl(Decimal("-200000"))
    assert not b.check().approved
    b.reset()
    assert b.check().approved
    assert b.cumulative_pnl == Decimal("0")


def test_circuit_breaker_positive_pnl_does_not_trip():
    b = DailyLossCircuitBreaker(daily_loss_limit=Decimal("100000"))
    b.record_pnl(Decimal("50000"))
    assert b.check().approved
    assert b.cumulative_pnl == Decimal("50000")


# ── KillSwitch ──────────────────────────────────────────────────────

def test_kill_switch_default_off():
    ks = KillSwitch()
    assert ks.check().approved


def test_kill_switch_activate_rejects():
    ks = KillSwitch()
    ks.activate()
    assert not ks.check().approved
    assert "kill switch" in ks.check().reason


def test_kill_switch_deactivate_resumes():
    ks = KillSwitch()
    ks.activate()
    ks.deactivate()
    assert ks.check().approved


# ── Daily loss pct (OMS / paper bridge) ─────────────────────────────

def test_daily_loss_pct_within_limit():
    assert check_daily_loss_pct(
        Decimal("-1000"), Decimal("100000"), Decimal("2")
    ).approved


def test_daily_loss_pct_breached():
    r = check_daily_loss_pct(Decimal("-2500"), Decimal("100000"), Decimal("2"))
    assert not r.approved
    assert "breached" in r.reason


def test_daily_loss_pct_disabled_when_zero():
    assert check_daily_loss_pct(Decimal("-99999"), Decimal("100000"), Decimal("0")).approved


def test_paper_daily_loss_float_adapter():
    r = check_paper_daily_loss(-2500.0, 100000.0, 2.0)
    assert not r.approved
    assert check_paper_daily_loss(-1000.0, 100000.0, 2.0).approved


# ── RiskGate composition ────────────────────────────────────────────

def test_risk_gate_approves_valid_order():
    gate = RiskGate(
        notional=OrderNotionalLimit(max_notional=Decimal("1000000")),
        concentration=ConcentrationLimit(max_pct=Decimal("0.30")),
        gross_exposure=GrossExposureLimit(max_pct=Decimal("1.0")),
    )
    r = gate.check_order(
        order_notional=Decimal("200000"),
        portfolio_notional=Decimal("1000000"),
        total_exposure=Decimal("900000"),
        capital=Decimal("1000000"),
    )
    assert r.approved


def test_risk_gate_short_circuits_on_notional():
    gate = RiskGate(notional=OrderNotionalLimit(max_notional=Decimal("100")))
    r = gate.check_order(Decimal("200"), Decimal("1000"), Decimal("500"), Decimal("1000"))
    assert not r.approved
    assert "notional" in r.reason
