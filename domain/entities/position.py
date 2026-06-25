"""Position and Holding domain entities — includes PositionState machine."""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from enum import Enum

from domain.enums import ProductType


@dataclass(slots=True, frozen=True)
class Position:
    """Canonical position — returned by every broker adapter."""

    symbol: str
    exchange: str
    quantity: int = 0
    avg_price: Decimal = Decimal("0")
    ltp: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    product_type: ProductType = ProductType.INTRADAY
    correlation_id: str | None = None

    @property
    def pnl(self) -> Decimal:
        if self.quantity > 0:
            return Decimal(str(self.quantity)) * (self.ltp - self.avg_price)
        elif self.quantity < 0:
            return Decimal(str(abs(self.quantity))) * (self.avg_price - self.ltp)
        return Decimal("0")

    def with_ltp(self, ltp: Decimal) -> Position:
        """Return a new Position with the last traded price updated."""
        unrealized = (
            Decimal(str(self.quantity)) * (ltp - self.avg_price)
            if self.quantity != 0
            else Decimal("0")
        )
        return replace(self, ltp=ltp, unrealized_pnl=unrealized)

    def with_fill(self, quantity: int, price: Decimal) -> Position:
        """Return a new Position after applying a signed fill."""
        old_qty = self.quantity
        old_avg = self.avg_price
        delta = quantity
        new_qty = old_qty + delta

        if old_qty == 0:
            new_avg = price
            new_realized = self.realized_pnl
        elif (old_qty > 0 and delta < 0) or (old_qty < 0 and delta > 0):
            closed = min(abs(old_qty), abs(delta))
            pnl_factor = Decimal("1") if old_qty > 0 else Decimal("-1")
            new_realized = self.realized_pnl + Decimal(str(closed)) * (price - old_avg) * pnl_factor
            if new_qty == 0:
                new_avg = Decimal("0")
            elif abs(delta) > abs(old_qty):
                new_avg = price
            else:
                new_avg = old_avg
        else:
            new_realized = self.realized_pnl
            new_avg = (Decimal(str(old_qty)) * old_avg + Decimal(str(delta)) * price) / Decimal(
                str(new_qty)
            )

        unrealized = Decimal(str(new_qty)) * (price - new_avg) if new_qty != 0 else Decimal("0")
        return replace(
            self,
            quantity=new_qty,
            avg_price=new_avg,
            ltp=price,
            unrealized_pnl=unrealized,
            realized_pnl=new_realized,
        )


@dataclass(slots=True, frozen=True)
class Holding:
    """Canonical holding — returned by every broker adapter."""

    symbol: str
    exchange: str
    quantity: int = 0
    available_quantity: int = 0
    avg_price: Decimal = Decimal("0")
    ltp: Decimal = Decimal("0")
    pnl: Decimal = Decimal("0")
    correlation_id: str | None = None


# ---------------------------------------------------------------------------
# Position State Machine (migrated from domain/positions.py)
# ---------------------------------------------------------------------------


class PositionState(str, Enum):
    """Position lifecycle states.

    Tracks the lifecycle of a position from flat through open, reducing,
    closed, or reversed states. Used by PositionManager to enforce valid
    state transitions and prevent illegal position updates.

    Transitions:
    - FLAT → OPEN (buy/sell creates position)
    - FLAT → REVERSED (sell after buy or vice versa in same session)
    - OPEN → REDUCING (partial exit)
    - OPEN → REVERSED (full exit + reverse)
    - OPEN → CLOSED (full exit)
    - REDUCING → FLAT (complete exit)
    - REDUCING → OPEN (add to position)
    - REDUCING → REVERSED (full exit + reverse)
    - REVERSED → FLAT (complete exit)
    - REVERSED → OPEN (reverse back)
    - REVERSED → REDUCING (reduce reversed position)
    - CLOSED → FLAT (reset for new session)
    """

    FLAT = "FLAT"
    OPEN = "OPEN"
    REDUCING = "REDUCING"
    CLOSED = "CLOSED"
    REVERSED = "REVERSED"

    @property
    def is_active(self) -> bool:
        """True if position has non-zero quantity."""
        return self in (PositionState.OPEN, PositionState.REDUCING, PositionState.REVERSED)

    @property
    def is_terminal(self) -> bool:
        """True if position is closed or flat (no active exposure)."""
        return self in (PositionState.FLAT, PositionState.CLOSED)


# Position state machine transition table
# Used by PositionManager to validate position updates
POSITION_STATE_TRANSITIONS: dict[PositionState, frozenset[PositionState]] = {
    PositionState.FLAT: frozenset(
        {
            PositionState.OPEN,
            PositionState.REVERSED,
        }
    ),
    PositionState.OPEN: frozenset(
        {
            PositionState.OPEN,  # Add to position
            PositionState.REDUCING,
            PositionState.CLOSED,
            PositionState.REVERSED,
        }
    ),
    PositionState.REDUCING: frozenset(
        {
            PositionState.FLAT,
            PositionState.OPEN,
            PositionState.REVERSED,
            PositionState.CLOSED,
        }
    ),
    PositionState.CLOSED: frozenset(
        {
            PositionState.FLAT,  # Reset for new session
        }
    ),
    PositionState.REVERSED: frozenset(
        {
            PositionState.FLAT,
            PositionState.OPEN,
            PositionState.REDUCING,
            PositionState.CLOSED,
        }
    ),
}
