"""SimulationFillPipeline — FillReducer before PortfolioProjector."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from domain import Side
from domain.entities import Trade
from application.services.simulation_orchestrator import SimulationFillPipeline


def test_apply_trade_updates_projector_after_reducer_accepts() -> None:
    pipeline = SimulationFillPipeline()
    ts = datetime(2026, 1, 2, tzinfo=timezone.utc)
    trade = Trade(
        trade_id="t1:open",
        order_id="ord-1",
        symbol="TEST",
        exchange="NSE",
        side=Side.BUY,
        quantity=10,
        price=Decimal("100"),
        trade_value=Decimal("1000"),
        timestamp=ts,
    )
    assert pipeline.apply_trade(trade, order_quantity=10)
    pos = pipeline.projector.get_position("TEST", "NSE")
    assert pos is not None
    assert pos.quantity == 10


def test_duplicate_fill_rejected() -> None:
    pipeline = SimulationFillPipeline()
    ts = datetime(2026, 1, 2, tzinfo=timezone.utc)
    trade = Trade(
        trade_id="dup",
        order_id="ord-1",
        symbol="TEST",
        exchange="NSE",
        side=Side.BUY,
        quantity=10,
        price=Decimal("100"),
        trade_value=Decimal("1000"),
        timestamp=ts,
    )
    assert pipeline.apply_trade(trade, order_quantity=10)
    assert not pipeline.apply_trade(trade, order_quantity=10)
