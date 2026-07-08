"""Position Aggregate Root.

Thin, thread-safe wrapper around the canonical
:class:`~domain.entities.position.Position` value object. Identity is the
``(account_id, instrument_id)`` pair. State transitions (price updates, fills)
replace the enclosed immutable :class:`~domain.entities.position.Position`
under an internal lock.
"""

from __future__ import annotations

import threading
from decimal import Decimal

from domain.entities.position import Position


class PositionAggregate:
    """Position Aggregate Root — owns position identity and state."""

    def __init__(self, position: Position, *, account_id: str) -> None:
        self._account_id = account_id
        self._position = position
        self._lock = threading.RLock()

    # ── Identity (read-only, lock-free) ────────────────────────────

    @property
    def account_id(self) -> str:
        return self._account_id

    @property
    def instrument_id(self) -> str:
        """Canonical instrument id (``exchange:underlying``)."""
        return f"{self._position.exchange}:{self._position.symbol}"

    # ── State (thread-safe read) ───────────────────────────────────

    @property
    def position(self) -> Position:
        """Current canonical position snapshot (immutable)."""
        return self._position

    @property
    def quantity(self) -> int:
        return self._position.quantity

    @property
    def unrealized_pnl(self) -> Decimal:
        return self._position.unrealized_pnl

    @property
    def realized_pnl(self) -> Decimal:
        return self._position.realized_pnl

    # ── Lifecycle transitions ──────────────────────────────────────

    def update_ltp(self, ltp: Decimal) -> None:
        """Refresh the last traded price and recompute unrealized PnL."""
        with self._lock:
            self._position = self._position.with_ltp(ltp)

    def apply_fill(self, quantity: int, price: Decimal) -> None:
        """Apply a signed fill to the position, recomputing avg/realized PnL."""
        with self._lock:
            self._position = self._position.with_fill(quantity, price)

    # ── Equality (by identity) ─────────────────────────────────────

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PositionAggregate):
            return NotImplemented
        return (
            self._account_id == other._account_id
            and self.instrument_id == other.instrument_id
        )

    def __hash__(self) -> int:
        return hash((self._account_id, self.instrument_id))

    def __repr__(self) -> str:
        return (
            f"PositionAggregate(account={self._account_id}, "
            f"instrument={self.instrument_id}, qty={self._position.quantity})"
        )
