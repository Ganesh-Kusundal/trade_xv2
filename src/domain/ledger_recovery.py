"""Rebuild portfolio projections from durable fill ledger."""

from __future__ import annotations

from domain.entities import Trade
from domain.execution_contracts import LedgerFillRecord
from domain.portfolio_projection import PortfolioProjector
from domain.ports.execution_ledger import ExecutionLedgerPort
from domain.simulation_fill_pipeline import SimulationFillPipeline


def rebuild_projector_from_fills(
    fills: list[LedgerFillRecord],
) -> PortfolioProjector:
    """Replay chronological fills through FillReducer + PortfolioProjector."""
    pipeline = SimulationFillPipeline()
    for record in sorted(fills, key=lambda f: (f.event_time, f.fill_id)):
        trade = Trade(
            trade_id=record.fill_id,
            order_id=record.order_id,
            symbol=record.symbol,
            exchange=record.exchange,
            side=record.side,
            quantity=record.quantity,
            price=record.price,
            trade_value=record.price * record.quantity,
            timestamp=record.event_time,
        )
        pipeline.apply_trade(trade, order_quantity=record.order_quantity)
    return pipeline.projector


def rebuild_projector_from_ledger(ledger: ExecutionLedgerPort) -> PortfolioProjector:
    """Rebuild positions from all fills stored in the execution ledger."""
    return rebuild_projector_from_fills(ledger.list_fills())