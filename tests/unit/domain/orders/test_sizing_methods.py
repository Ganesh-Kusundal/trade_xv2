"""Sizing helpers — pure math, preserving prior compute_order_quantity."""

from __future__ import annotations

from domain.orders.sizing import (
    SizingMethod,
    compute_atr_quantity,
    compute_order_quantity,
    compute_remaining_quantity,
)


def test_compute_order_quantity_unchanged_behavior():
    # 100_000 * 10% = 10_000; /100 = 100 shares.
    assert compute_order_quantity(equity=100_000, price=100, max_position_pct=10) == 100


def test_compute_order_quantity_returns_zero_on_bad_inputs():
    assert compute_order_quantity(equity=0, price=100, max_position_pct=10) == 0
    assert compute_order_quantity(equity=100_000, price=0, max_position_pct=10) == 0


def test_compute_remaining_quantity_subtracts_existing():
    # budget 10_000; 4_000 held -> 6_000 remaining -> 60 shares at 100.
    qty = compute_remaining_quantity(
        equity=100_000, max_position_pct=10, price=100, existing_notional=4_000
    )
    assert qty == 60


def test_compute_remaining_quantity_no_pyramiding_past_limit():
    # fully utilised budget -> zero remaining room.
    qty = compute_remaining_quantity(
        equity=100_000, max_position_pct=10, price=100, existing_notional=10_000
    )
    assert qty == 0


def test_compute_atr_quantity_scales_by_risk_budget():
    # budget 100_000 * 1% = 1000; risk/share = atr 2 * mult 2 = 4 -> 250.
    qty = compute_atr_quantity(equity=100_000, atr=2, risk_pct=1, atr_multiplier=2)
    assert qty == 250


def test_compute_atr_quantity_zero_on_bad_inputs():
    assert compute_atr_quantity(equity=0, atr=2, risk_pct=1) == 0
    assert compute_atr_quantity(equity=100_000, atr=0, risk_pct=1) == 0


def test_sizing_method_enum_values():
    assert SizingMethod.PCT_EQUITY.value == "PCT_EQUITY"
    assert SizingMethod.ATR.value == "ATR"
    assert SizingMethod.FIXED.value == "FIXED"
