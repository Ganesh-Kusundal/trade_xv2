"""Simulation orchestration — fill pipeline, position meta, portfolio projection.

Canonical location for simulation orchestration logic (REF-10). This
consolidates the use-cases previously scattered across:
- domain/simulation_fill_pipeline.py (SimulationFillPipeline)
- domain/simulation_position_meta.py (PositionMeta)
- domain/portfolio_projection.py (project_trade, PortfolioProjector)

Domain modules re-export these names as backward-compat shims; new code
should import from here. Live OMS
(:class:`application.oms.position_manager.PositionManager`), replay, and
paper must apply fills through :class:`PortfolioProjector` before
mode-local read models diverge.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from domain.entities import Position, Trade
from domain.fill_reducer import FillReducer
from domain.symbols import make_position_key

# ---------------------------------------------------------------------------
# Portfolio projection
# ---------------------------------------------------------------------------


def project_trade(current: Position, trade: Trade) -> Position:
    """Apply one trade to a position snapshot (pure, deterministic)."""
    qty = int(trade.quantity)
    delta = qty if trade.side.value == "BUY" else -qty
    return current.with_fill(delta, trade.price)


@dataclass
class PortfolioProjector:
    """In-memory position book driven by :func:`project_trade`."""

    positions: dict[str, Position] = field(default_factory=dict)

    def apply_trade(self, trade: Trade) -> Position:
        key = make_position_key(trade.symbol, trade.exchange)
        current = self.positions.get(
            key,
            Position(symbol=trade.symbol, exchange=trade.exchange),
        )
        updated = project_trade(current, trade)
        self.positions[key] = updated
        return updated

    def get_position(self, symbol: str, exchange: str) -> Position | None:
        return self.positions.get(make_position_key(symbol, exchange))

    def get_positions(self) -> list[Position]:
        return list(self.positions.values())

    def mark_ltp(self, symbol: str, exchange: str, ltp: Decimal) -> None:
        """Update mark price for open-position MTM without changing qty/avg."""
        key = make_position_key(symbol, exchange)
        pos = self.positions.get(key)
        if pos is not None and int(pos.quantity) != 0:
            self.positions[key] = pos.with_ltp(Decimal(str(ltp)))

    def total_realized_pnl(self) -> float:
        return float(sum(p.realized_pnl.to_decimal() for p in self.positions.values()))


# ---------------------------------------------------------------------------
# Simulation fill pipeline
# ---------------------------------------------------------------------------


@dataclass
class SimulationFillPipeline:
    """Apply simulated fills through the shared reducer before projection."""

    reducer: FillReducer = field(default_factory=FillReducer)
    projector: PortfolioProjector = field(default_factory=PortfolioProjector)
    _filled_by_order: dict[str, int] = field(default_factory=dict)

    def apply_trade(self, trade: Trade, *, order_quantity: int | None = None) -> bool:
        if trade.quantity <= 0:
            return False
        order_id = trade.order_id or f"sim-{trade.trade_id}"
        oq = order_quantity if order_quantity is not None else trade.quantity
        prior = self._filled_by_order.get(order_id, 0)
        fill = FillReducer.fill_from_trade(
            str(trade.trade_id),
            order_id,
            trade.quantity,
            prior,
            trade.price,
        )
        result = self.reducer.apply(
            fill,
            order_quantity=oq,
            prior_cumulative=prior,
        )
        if not result.accepted:
            return False
        self._filled_by_order[order_id] = prior + trade.quantity
        self.projector.apply_trade(trade)
        return True


# ---------------------------------------------------------------------------
# Simulation-only position metadata
# ---------------------------------------------------------------------------


@dataclass
class PositionMeta:
    """Per-symbol exit rules and audit fields; qty/avg live in PortfolioProjector."""

    entry_time: datetime
    stop_loss: float | None = None
    target: float | None = None
    strategy: str = ""

    @property
    def take_profit(self) -> float | None:
        return self.target

    def with_take_profit(self, value: float | None) -> PositionMeta:
        return PositionMeta(
            entry_time=self.entry_time,
            stop_loss=self.stop_loss,
            target=value,
            strategy=self.strategy,
        )


__all__ = [
    "PortfolioProjector",
    "PositionMeta",
    "SimulationFillPipeline",
    "project_trade",
]
