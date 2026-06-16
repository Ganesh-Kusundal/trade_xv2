"""Pure PnL calculator — deterministic, stateless, thread-safe.

Computes portfolio-level realized and unrealized PnL from a list of
positions. Used by the portfolio manager, risk manager, and daily PnL
reset scheduler.

Design principle: **pure function** — no side effects, no mutable state,
no I/O. Given the same inputs, it always returns the same outputs.

Usage::

    from brokers.common.core.pnl_calculator import PnLCalculator, PnLSnapshot

    snapshot = PnLCalculator.compute(positions)
    print(snapshot.total_unrealized, snapshot.total_realized)
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from brokers.common.core.domain import Position


@dataclass(frozen=True)
class PnLSnapshot:
    """Immutable snapshot of portfolio PnL at a point in time."""

    total_unrealized: Decimal = Decimal("0")
    total_realized: Decimal = Decimal("0")
    total_pnl: Decimal = Decimal("0")
    position_count: int = 0
    long_count: int = 0
    short_count: int = 0
    flat_count: int = 0

    @property
    def is_profitable(self) -> bool:
        """True if total PnL is positive."""
        return self.total_pnl > Decimal("0")

    @property
    def is_loss(self) -> bool:
        """True if total PnL is negative."""
        return self.total_pnl < Decimal("0")


class PnLCalculator:
    """Pure PnL computation — no state, no side effects.

    All methods are static. This class is a namespace, not an
    instantiable object.
    """

    def __init__(self) -> None:
        raise TypeError("PnLCalculator is not instantiable — use static methods")

    @staticmethod
    def compute(positions: list[Position]) -> PnLSnapshot:
        """Compute portfolio-level PnL from a list of positions.

        Parameters
        ----------
        positions:
            List of Position objects (may be empty).

        Returns
        -------
        PnLSnapshot with total_unrealized, total_realized, and total_pnl.
        """
        total_unrealized = Decimal("0")
        total_realized = Decimal("0")
        long_count = 0
        short_count = 0
        flat_count = 0

        for pos in positions:
            # Use the pnl property (computed from ltp/avg_price) rather than
            # the stored unrealized_pnl field, which may be stale.
            total_unrealized += pos.pnl
            total_realized += pos.realized_pnl

            if pos.quantity > 0:
                long_count += 1
            elif pos.quantity < 0:
                short_count += 1
            else:
                flat_count += 1

        total_pnl = total_unrealized + total_realized

        return PnLSnapshot(
            total_unrealized=total_unrealized,
            total_realized=total_realized,
            total_pnl=total_pnl,
            position_count=len(positions),
            long_count=long_count,
            short_count=short_count,
            flat_count=flat_count,
        )

    @staticmethod
    def compute_unrealized(position: Position) -> Decimal:
        """Compute unrealized PnL for a single position.

        Delegates to ``position.pnl`` (which uses ``position.ltp``).
        """
        return position.pnl

    @staticmethod
    def compute_realized(position: Position) -> Decimal:
        """Extract realized PnL from a single position."""
        return position.realized_pnl

    @staticmethod
    def compute_daily_pnl(positions: list[Position]) -> Decimal:
        """Compute total daily PnL (realized + unrealized) for a portfolio.

        This is the value the risk manager uses for daily loss checks.
        """
        snapshot = PnLCalculator.compute(positions)
        return snapshot.total_pnl
