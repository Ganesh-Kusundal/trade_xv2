"""Order Aggregate Root.

Thin, thread-safe wrapper around the canonical :class:`~domain.entities.order.Order`
value object. The aggregate owns identity (``order_id``) and lifecycle state
(:class:`~domain.entities.order.Order` is itself immutable; transitions return
new instances that replace the aggregate's internal snapshot under a lock).

Design mirrors :class:`~domain.aggregates.instrument.InstrumentAggregate`:
composition over inheritance, atomic state replacement via an internal lock,
immutable enclosed value objects.
"""

from __future__ import annotations

import threading
from datetime import datetime
from typing import TYPE_CHECKING

from domain.entities.order import Order
from domain.entities.order_lifecycle import ORDER_STATUS_TRANSITIONS
from domain.entities.trade import Trade
from domain.types import OrderStatus

if TYPE_CHECKING:
    from domain.exceptions import TradeXV2Error


class OrderAggregate:
    """Order Aggregate Root — owns order identity, state, and its trades."""

    def __init__(self, order: Order) -> None:
        self._order = order
        self._trades: list[Trade] = []
        self._lock = threading.RLock()

    # ── Identity (read-only, lock-free) ────────────────────────────

    @property
    def order_id(self) -> str:
        return self._order.order_id

    # ── State (thread-safe read) ───────────────────────────────────

    @property
    def order(self) -> Order:
        """Current canonical order snapshot (immutable)."""
        return self._order

    @property
    def status(self) -> OrderStatus:
        return self._order.status

    @property
    def trades(self) -> tuple[Trade, ...]:
        """All fills recorded against this order (immutable view)."""
        with self._lock:
            return tuple(self._trades)

    @property
    def filled_quantity(self) -> int:
        return self._order.filled_quantity

    @property
    def is_complete(self) -> bool:
        return self._order.is_complete

    # ── Lifecycle transitions ──────────────────────────────────────

    def apply_status(self, status: OrderStatus) -> None:
        """Transition the order to a new status, enforcing the lifecycle table."""
        with self._lock:
            current = self._order.status
            allowed = ORDER_STATUS_TRANSITIONS.get(current, frozenset())
            if status not in allowed and status != current:
                raise ValueError(
                    f"Illegal order transition: {current!s} -> {status!s}"
                )
            self._order = self._order.with_status(status)

    def apply_fill(self, filled_quantity: int, avg_price: object) -> None:
        """Apply a fill update to the enclosed order."""
        from decimal import Decimal

        price = avg_price if isinstance(avg_price, Decimal) else Decimal(str(avg_price))
        with self._lock:
            self._order = self._order.with_fill(filled_quantity, price)

    def add_trade(self, trade: Trade) -> None:
        """Record a fill as a Trade within this aggregate boundary."""
        with self._lock:
            self._trades.append(trade)

    # ── Equality (by identity) ─────────────────────────────────────

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, OrderAggregate):
            return NotImplemented
        return self.order_id == other.order_id

    def __hash__(self) -> int:
        return hash(self.order_id)

    def __repr__(self) -> str:
        return f"OrderAggregate({self.order_id}, status={self.status!s})"
