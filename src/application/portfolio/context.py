"""First-class, typed portfolio context.

This is the application-layer owner of *portfolio state mutation*. Position
mutation is no longer scattered: any code that wants to apply a fill or update
the cash balance goes through :class:`PortfolioContext`, which operates
exclusively on the canonical domain value objects (``Position``, ``Trade``,
``Balance``).

The low-level arithmetic (average-price updates, realized P&L) is delegated to
the domain value object (``Position.with_fill``), so there is a single source
of truth for the math — this context only owns *state* (which positions exist
and what the current balance is).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal

from domain.entities import Balance, Position, Trade


@dataclass
class PortfolioContext:
    """Typed owner of portfolio state mutation in the application layer.

    Parameters
    ----------
    positions:
        Optional seed positions (e.g. hydrated from the OMS / a snapshot).
    balance:
        Optional starting :class:`~domain.entities.account.Balance`.
    """

    positions: dict[tuple[str, str], Position] = field(default_factory=dict)
    balance: Balance = field(default_factory=Balance)

    def __post_init__(self) -> None:
        # Normalise a positional seed list to the internal keyed store.
        if not isinstance(self.positions, dict):  # pragma: no cover - defensive
            self.positions = {(p.exchange, p.symbol): p for p in self.positions}
        # Re-key defensively in case a dict was passed with wrong key shape.
        self.positions = {(p.exchange, p.symbol): p for p in self.positions.values()}

    # ── Mutation ─────────────────────────────────────────────────────────

    def apply_trade(self, trade: Trade) -> Position:
        """Apply a trade to the portfolio, returning the updated position.

        This is the single, typed entry point for position mutation in the
        portfolio context. It mutates only this context's state and delegates
        the P&L math to :meth:`Position.with_fill`.

        Args:
            trade: A canonical :class:`~domain.entities.trade.Trade` (uses
                ``symbol``, ``exchange``, signed ``quantity`` and ``price``).

        Returns:
            The updated :class:`~domain.entities.position.Position`.
        """
        key = (trade.exchange, trade.symbol)
        current = self.positions.get(key, Position(symbol=trade.symbol, exchange=trade.exchange))
        # Signed fill qty for Position.with_fill (BUY +, SELL -)
        qty = int(trade.quantity)
        side_raw = getattr(trade.side, "value", trade.side)
        side = str(side_raw).upper().replace("SIDE.", "")
        signed = qty if side in ("BUY", "B") else -abs(qty)
        updated = current.with_fill(signed, trade.price)
        self.positions[key] = updated
        return updated

    def apply_balance(self, balance: Balance) -> None:
        """Replace the current account balance with ``balance``."""
        self.balance = balance

    # ── Reads ────────────────────────────────────────────────────────────

    def get_positions(self) -> list[Position]:
        """Return a snapshot of all positions."""
        return list(self.positions.values())

    def get_position(self, symbol: str, exchange: str) -> Position | None:
        """Return a single position by symbol/exchange, if present."""
        return self.positions.get((exchange, symbol))

    def total_unrealized_pnl(self) -> Decimal:
        """Sum of unrealized P&L across all positions."""
        return sum((p.unrealized_pnl for p in self.positions.values()), Decimal("0"))

    def total_realized_pnl(self) -> Decimal:
        """Sum of realized P&L across all positions."""
        return sum((p.realized_pnl for p in self.positions.values()), Decimal("0"))

    @classmethod
    def from_positions(
        cls, positions: Sequence[Position], balance: Balance | None = None
    ) -> PortfolioContext:
        """Build a context from a sequence of seeded positions."""
        ctx = cls(balance=balance or Balance())
        ctx.positions = {(p.exchange, p.symbol): p for p in positions}
        return ctx
