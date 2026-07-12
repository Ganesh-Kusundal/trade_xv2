"""ExecutionPlan.from_signal maps a SignalDTO into legs + intents.

Guarantees: actionable BUY/SELL → one leg of the right side; sizing method
selection (FIXED / PCT_EQUITY / ATR); position-aware PCT sizing; slicing
algorithms; and the refusal paths (not actionable / no price).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from domain.enums import OrderType, ProductType, Side
from domain.models.trading import SignalDTO
from domain.orders.execution_plan import (
    ExecutionPlan,
    PlanContext,
    SizingMethod,
    SlicingAlgo,
    SlicingPlan,
)
from domain.orders.intent import OrderIntent
from domain.orders.placement import plan_to_intents


def _signal(**kw) -> SignalDTO:
    base = {
        "symbol": "RELIANCE",
        "exchange": "NSE",
        "side": "BUY",
        "signal_type": "BUY",
        "confidence": Decimal("0.9"),
        "quantity": 0,
        "entry_price": Decimal("100"),
    }
    base.update(kw)
    return SignalDTO(**base)


def _ctx(**kw) -> PlanContext:
    base = {
        "equity": Decimal("100000"),
        "max_position_pct": Decimal("10"),
        "default_order_type": OrderType.LIMIT,
        "default_product_type": ProductType.INTRADAY,
        "default_exchange": "NSE",
    }
    base.update(kw)
    return PlanContext(**base)


def test_actionable_buy_signal_maps_to_single_buy_leg():
    plan = ExecutionPlan.from_signal(_signal(quantity=5), _ctx())
    assert plan.legs
    assert len(plan.legs) == 1
    leg = plan.legs[0]
    assert isinstance(leg, OrderIntent)
    assert leg.side == Side.BUY
    assert leg.quantity == 5
    assert leg.symbol == "RELIANCE"
    assert plan.sizing.method == SizingMethod.FIXED


def test_actionable_sell_signal_maps_to_sell_leg():
    plan = ExecutionPlan.from_signal(_signal(side="SELL", signal_type="SELL", quantity=3), _ctx())
    assert plan.legs[0].side == Side.SELL


def test_pct_equity_sizing_is_position_aware():
    # equity 100_000, 10% -> 10_000 notional; price 100 -> 100 shares.
    plan = ExecutionPlan.from_signal(_signal(entry_price=Decimal("100")), _ctx())
    assert plan.sizing.method == SizingMethod.PCT_EQUITY
    assert plan.sizing.total_qty == 100


def test_pct_equity_subtracts_existing_notional():
    # 10_000 budget, 4_000 already held -> 6_000 remaining -> 60 shares.
    ctx = _ctx(existing_notional=Decimal("4000"), equity=Decimal("100000"))
    plan = ExecutionPlan.from_signal(_signal(entry_price=Decimal("100")), ctx)
    assert plan.sizing.total_qty == 60


def test_atr_sizing_selected_when_atr_present():
    ctx = _ctx(atr=Decimal("2"), atr_risk_pct=Decimal("1"), max_position_pct=Decimal("0"))
    plan = ExecutionPlan.from_signal(_signal(entry_price=Decimal("100")), ctx)
    assert plan.sizing.method == SizingMethod.ATR
    # risk budget = 100_000 * 1% = 1000; risk/share = atr(2)*2 = 4 -> 250 shares.
    assert plan.sizing.total_qty == 250


def test_explicit_quantity_is_absolute_in_orchestrator_policy():
    # Orchestrator leaves explicit quantity uncapped (cap_explicit_quantity=False).
    plan = ExecutionPlan.from_signal(_signal(quantity=7), _ctx())
    assert plan.sizing.total_qty == 7


def test_explicit_quantity_is_capped_when_policy_requires():
    # SignalDTO.to_intent delegates with cap_explicit_quantity=True.
    plan = ExecutionPlan.from_signal(
        _signal(quantity=5000, entry_price=Decimal("100")),
        _ctx(cap_explicit_quantity=True),
    )
    assert plan.sizing.total_qty == 100  # capped by 10% of 100k


def test_eng003_refuses_default_quantity():
    # No explicit qty, no pct, no atr -> refuse (qty 0, no legs).
    plan = ExecutionPlan.from_signal(
        _signal(entry_price=Decimal("100"), quantity=0, position_size_pct=Decimal("0")),
        _ctx(max_position_pct=Decimal("0")),
    )
    assert plan.sizing.total_qty == 0
    assert plan.legs == []


def test_non_actionable_signal_raises():
    with pytest.raises(ValueError, match="not actionable"):
        ExecutionPlan.from_signal(_signal(signal_type="HOLD"), _ctx())


def test_no_usable_price_raises():
    with pytest.raises(ValueError, match="no usable price"):
        ExecutionPlan.from_signal(_signal(price=None, entry_price=None), _ctx())


def test_slicing_none_returns_single_intent():
    plan = ExecutionPlan.from_signal(_signal(quantity=10), _ctx())
    intents = plan_to_intents(plan)
    assert len(intents) == 1
    assert intents[0].quantity == 10


def test_slicing_twap_splits_into_slice_count():
    plan = ExecutionPlan.from_signal(
        _signal(quantity=10),
        _ctx(slicing=SlicingPlan(algo=SlicingAlgo.TWAP, slice_count=4)),
    )
    intents = plan_to_intents(plan)
    assert len(intents) == 4
    # 10 split into 4 equal-ish slices -> 3,3,2,2
    assert [i.quantity for i in intents] == [3, 3, 2, 2]
    assert sum(i.quantity for i in intents) == 10
    # stable idempotent correlation ids
    assert intents[0].correlation_id.endswith(":slice1")


def test_slicing_iceberg_splits_by_disclosed_qty():
    plan = ExecutionPlan.from_signal(
        _signal(quantity=10),
        _ctx(slicing=SlicingPlan(algo=SlicingAlgo.ICEBERG, disclosed_qty=3)),
    )
    intents = plan_to_intents(plan)
    # 10 split into 3,3,3,1
    assert [i.quantity for i in intents] == [3, 3, 3, 1]
