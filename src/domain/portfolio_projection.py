"""Shared portfolio projection — single fill → position transition logic.

Live OMS (:class:`application.oms.position_manager.PositionManager`),
replay, and paper must apply fills through this reducer before mode-local
read models diverge.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from domain.entities import Position, Trade
from domain.symbols import make_position_key


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
        return float(
            sum(p.realized_pnl.to_decimal() for p in self.positions.values())
        )