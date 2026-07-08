"""Execution — aggregate that owns the fills for an order.

Closes the gap where ``Execution`` was a missing concept: an order's fills are
collected here as immutable :class:`~domain.entities.trade.Trade` value objects,
and the aggregate computes running averages, notional, and remaining quantity.
Thread-safe; the trade list is replaced atomically under a lock.
"""

from __future__ import annotations

import threading
from decimal import Decimal
from typing import TYPE_CHECKING

from domain.entities.trade import Trade
from domain.events.types import EventType

if TYPE_CHECKING:
    from domain.events.bus import DomainEventBus
    from domain.instruments.instrument_id import InstrumentId
    from domain.types import Side


class Execution:
    """Aggregate root for the fills against a single order."""

    def __init__(
        self,
        order_id: str,
        instrument_id: "InstrumentId",
        side: "Side",
        order_quantity: int,
        *,
        event_bus: "DomainEventBus | None" = None,
    ) -> None:
        self._order_id = order_id
        self._instrument_id = instrument_id
        self._side = side
        self._order_quantity = order_quantity
        self._trades: list[Trade] = []
        self._lock = threading.RLock()
        self._event_bus = event_bus

    # ── Identity (read-only) ────────────────────────────────────────

    @property
    def order_id(self) -> str:
        return self._order_id

    @property
    def instrument_id(self) -> "InstrumentId":
        return self._instrument_id

    @property
    def side(self) -> "Side":
        return self._side

    @property
    def order_quantity(self) -> int:
        return self._order_quantity

    # ── Fills ────────────────────────────────────────────────────────

    @property
    def trades(self) -> tuple[Trade, ...]:
        with self._lock:
            return tuple(self._trades)

    @property
    def filled_quantity(self) -> int:
        with self._lock:
            return sum(t.quantity for t in self._trades)

    @property
    def remaining_quantity(self) -> int:
        return max(0, self._order_quantity - self.filled_quantity)

    @property
    def avg_price(self) -> Decimal:
        with self._lock:
            if not self._trades:
                return Decimal("0")
            total_value = sum(t.value for t in self._trades)
            total_qty = sum(t.quantity for t in self._trades)
        return total_value / Decimal(total_qty) if total_qty else Decimal("0")

    @property
    def notional(self) -> Decimal:
        with self._lock:
            return sum(t.value for t in self._trades)

    @property
    def is_complete(self) -> bool:
        return self.filled_quantity >= self._order_quantity

    def apply_trade(self, trade: Trade) -> None:
        """Record a fill. Emits TRADE_APPLIED so downstream aggregates update."""
        with self._lock:
            self._trades.append(trade)
        if self._event_bus is not None:
            self._event_bus.publish(
                EventType.TRADE_APPLIED,
                {
                    "order_id": self._order_id,
                    "trade": trade,
                    "filled_quantity": self.filled_quantity,
                    "avg_price": str(self.avg_price),
                },
            )

    def __repr__(self) -> str:
        return (
            f"Execution(order={self._order_id}, "
            f"filled={self.filled_quantity}/{self._order_quantity}, "
            f"avg={self.avg_price})"
        )
