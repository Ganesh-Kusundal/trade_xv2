"""Portfolio — rich aggregate owning positions and computing portfolio-level PnL.

Previously ``domain/trading/portfolio.py`` held a mutable dict of positions
with zero behavior. This module replaces it with an aggregate that computes
unrealized / realized / total PnL, gross exposure, per-symbol concentration,
and provides the ``pnl()`` method the refactoring directive demands on
``Portfolio.positions``.

    portfolio = Portfolio()
    portfolio.add_position(Position(symbol="RELIANCE", quantity=10, avg_price=Decimal("2500")))
    portfolio.total_pnl      # Money
    portfolio.gross_exposure  # Money
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from domain.entities.position import Position
from domain.primitives import Money


@dataclass
class Portfolio:
    """Aggregate root: owns a collection of Positions and computes portfolio-level PnL.

    Positions are keyed by ``symbol:exchange`` and replaced atomically on update.
    """

    _positions: dict[str, Position] = field(default_factory=dict)

    @staticmethod
    def _key(position: Position) -> str:
        return f"{position.symbol}:{position.exchange}"

    # ── Mutation (Tell, Don't Ask) ──────────────────────────────────

    def add_position(self, position: Position) -> None:
        """Insert or replace a position."""
        self._positions[self._key(position)] = position

    def remove_position(self, symbol: str, exchange: str) -> None:
        """Remove a position by symbol:exchange (no-op if absent)."""
        self._positions.pop(f"{symbol}:{exchange}", None)

    def update_ltp(self, symbol: str, exchange: str, ltp: Decimal) -> None:
        """Update last-traded price for a position (returns immutable Position)."""
        key = f"{symbol}:{exchange}"
        pos = self._positions.get(key)
        if pos is not None:
            self._positions[key] = pos.with_ltp(ltp)

    # ── Queries ──────────────────────────────────────────────────────

    @property
    def positions(self) -> dict[str, Position]:
        """All positions keyed by ``symbol:exchange`` (read-only copy)."""
        return dict(self._positions)

    @property
    def position_count(self) -> int:
        return len(self._positions)

    @property
    def unrealized_pnl(self) -> Money:
        return sum((p.unrealized_pnl for p in self._positions.values()), Money(0))

    @property
    def realized_pnl(self) -> Money:
        return sum((p.realized_pnl for p in self._positions.values()), Money(0))

    @property
    def total_pnl(self) -> Money:
        return self.unrealized_pnl + self.realized_pnl

    @property
    def gross_exposure(self) -> Money:
        """Sum of absolute notional across all positions."""
        return sum(
            (abs(p.avg_price * Decimal(str(p.quantity))) for p in self._positions.values()),
            Money(0),
        )

    def symbol_exposure(self, symbol: str, exchange: str) -> Money:
        """Absolute notional for one symbol."""
        pos = self._positions.get(f"{symbol}:{exchange}")
        if pos is None:
            return Decimal("0")
        return abs(pos.avg_price * Decimal(str(pos.quantity)))

    def concentration(self, symbol: str, exchange: str) -> Decimal:
        """Fraction of gross exposure occupied by one symbol (0..1)."""
        gross = self.gross_exposure
        if gross <= 0:
            return Decimal("0")
        return self.symbol_exposure(symbol, exchange) / gross

    def pnl(self) -> Money:
        """Total portfolio PnL (unrealized + realized)."""
        return self.total_pnl

    def __repr__(self) -> str:
        return (
            f"Portfolio(positions={self.position_count}, "
            f"unrealized={self.unrealized_pnl}, realized={self.realized_pnl})"
        )
