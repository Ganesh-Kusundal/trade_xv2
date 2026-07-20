"""P2-analytics: single Trade/Position for simulation."""

from datetime import datetime
from decimal import Decimal

from analytics.paper.models import PaperTrade
from analytics.replay.models import SimulatedTrade
from analytics.shared.trade_types import SimPosition, SimTrade
from domain.enums import Side


def test_sim_trade_construction():
    trade = SimTrade(
        trade_id="t1",
        symbol="RELIANCE",
        side=Side.BUY,
        quantity=100,
        price=Decimal("2500"),
    )
    assert trade.trade_id == "t1"
    assert trade.price == Decimal("2500")


def test_sim_position_construction():
    pos = SimPosition(
        symbol="RELIANCE",
        side=Side.BUY,
        quantity=100,
        avg_price=Decimal("2500"),
    )
    assert pos.symbol == "RELIANCE"
    assert pos.avg_price == Decimal("2500")


def test_replay_and_paper_share_domain_conversion():
    """Zero-parity (D7/D12): replay and paper emit identical domain trades.

    Both ``SimulatedTrade`` and ``PaperTrade`` must route through the single
    ``sim_trade_to_domain`` helper, so the trade→domain mapping is defined
    exactly once and cannot drift between engines.
    """
    # Patch the shared helper to prove both engines call it.
    calls = []
    import analytics.shared.trade_types as tt

    real = tt.sim_trade_to_domain

    def _spy(**kwargs):
        calls.append(kwargs)
        return real(**kwargs)

    tt.sim_trade_to_domain = _spy
    try:
        sim = SimulatedTrade(
            symbol="RELIANCE", side="BUY", entry_price=2500.0, quantity=10, pnl=Decimal("100")
        )
        sim.to_domain_trade()
        paper = PaperTrade(
            symbol="RELIANCE",
            side=Side.BUY,
            entry_price=2500.0,
            exit_price=2600.0,
            quantity=10,
            entry_time=datetime(2026, 1, 1),
            exit_time=datetime(2026, 1, 2),
            pnl=100.0,
            pnl_pct=4.0,
            commission=0.0,
            slippage_cost=0.0,
            strategy="s",
        )
        paper.to_domain_trade()
    finally:
        tt.sim_trade_to_domain = real

    assert len(calls) == 2, "both engines must use the shared conversion helper"
    # Same symbol/side/quantity mapping shape.
    assert calls[0]["symbol"] == calls[1]["symbol"] == "RELIANCE"
    assert calls[0]["side"] == calls[1]["side"] == "BUY"
