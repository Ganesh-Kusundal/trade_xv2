"""TOS-P6-006 — equity derivation includes commission and slippage."""

from __future__ import annotations

from types import SimpleNamespace

from analytics.replay.orchestrator import UnifiedReplayOrchestrator


def _item(side: str, price: float, qty: int):
    event = SimpleNamespace(
        event_type="TRADE",
        payload={"side": side, "price": price, "quantity": qty},
        symbol="X",
    )
    return SimpleNamespace(event=event)


def test_derive_expected_equity_applies_commission_and_slippage():
    orch = UnifiedReplayOrchestrator.__new__(UnifiedReplayOrchestrator)
    items = [_item("BUY", 100.0, 10), _item("SELL", 110.0, 10)]
    # No costs: buy 1000, sell 1100 → equity 100100
    raw = orch._derive_expected_equity(
        items, initial_capital=100_000.0, commission_per_trade=0.0, slippage_bps=0.0
    )
    assert raw == 100_100.0
    # With costs: 2 * 20 commission + slippage on both legs
    with_costs = orch._derive_expected_equity(
        items, initial_capital=100_000.0, commission_per_trade=20.0, slippage_bps=5.0
    )
    assert with_costs is not None
    assert with_costs < raw
