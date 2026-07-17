"""Minimal fill reducer — validates FillEvent invariants before state mutation.

Per execution-contract.md, the reducer rejects duplicate fill IDs, impossible
cumulative decreases, and overfills relative to order quantity.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class FillEvent:
    """Canonical fill event accepted by the execution ledger reducer."""

    fill_id: str
    order_id: str
    quantity: int
    cumulative_quantity: int
    price: Decimal
    fees: Decimal = Decimal("0")
    taxes: Decimal | None = None
    multiplier: Decimal | None = None
    currency: str | None = None
    event_time: datetime | None = None
    received_time: datetime | None = None
    broker_sequence: int | None = None
    fill_status: str | None = None
    source: str | None = None

    def __post_init__(self) -> None:
        if not self.fill_id or not str(self.fill_id).strip():
            raise ValueError("fill_id is required")
        if not self.order_id or not str(self.order_id).strip():
            raise ValueError("order_id is required")
        if self.quantity < 0:
            raise ValueError("fill quantity cannot be negative")
        if self.cumulative_quantity < 0:
            raise ValueError("cumulative_quantity cannot be negative")


@dataclass(frozen=True, slots=True)
class FillReduceResult:
    """Outcome of applying a fill through the reducer."""

    accepted: bool
    reason: str = ""


class FillReducer:
    """Stateful reducer enforcing fill ordering and idempotency invariants."""

    def __init__(self) -> None:
        self._seen_fill_ids: set[str] = set()
        self._cumulative_by_order: dict[str, int] = {}

    def validate(
        self,
        fill: FillEvent,
        *,
        order_quantity: int,
        prior_cumulative: int = 0,
    ) -> FillReduceResult:
        """Check a fill against reducer invariants WITHOUT mutating state.

        Used by the OMS recorder, which must validate a fill *before* applying
        it to order state yet only *commit* the fill id after the durable ledger
        mark succeeds (so a crash during marking leaves the reducer clean for
        replay — see Defect R6 / apply-before-mark).
        """
        if fill.fill_id in self._seen_fill_ids:
            return FillReduceResult(False, f"duplicate fill_id {fill.fill_id}")

        baseline = max(prior_cumulative, self._cumulative_by_order.get(fill.order_id, 0))
        if fill.cumulative_quantity < baseline:
            return FillReduceResult(
                False,
                f"cumulative quantity {fill.cumulative_quantity} decreased from {baseline}",
            )

        if fill.cumulative_quantity > order_quantity:
            return FillReduceResult(
                False,
                f"cumulative quantity {fill.cumulative_quantity} exceeds order quantity {order_quantity}",
            )

        return FillReduceResult(True)

    def commit(self, fill: FillEvent) -> None:
        """Record a *validated* fill as seen (mutates reducer state).

        Call this only after the fill has been durably marked processed, so a
        crash before marking never poisons the reducer for a later replay.
        """
        self._seen_fill_ids.add(fill.fill_id)
        self._cumulative_by_order[fill.order_id] = fill.cumulative_quantity

    def apply(
        self,
        fill: FillEvent,
        *,
        order_quantity: int,
        prior_cumulative: int = 0,
    ) -> FillReduceResult:
        """Validate and accept a fill, or reject with a reason."""
        result = self.validate(
            fill,
            order_quantity=order_quantity,
            prior_cumulative=prior_cumulative,
        )
        if result.accepted:
            self.commit(fill)
        return result

    @staticmethod
    def fill_from_trade(
        trade_id: str,
        order_id: str,
        quantity: int,
        prior_filled: int,
        price: Decimal,
        fees: Decimal = Decimal("0"),
    ) -> FillEvent:
        """Build a FillEvent from incremental trade fields and prior fill state."""
        return FillEvent(
            fill_id=trade_id,
            order_id=order_id,
            quantity=quantity,
            cumulative_quantity=prior_filled + quantity,
            price=price,
            fees=fees,
        )