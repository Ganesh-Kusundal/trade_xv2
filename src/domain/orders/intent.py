"""OrderIntent — domain command before risk / OMS / exchange.

Institutional spine::

    Session.buy(...) → OrderIntent → OrderServicePort (OMS + Risk)
        → ExecutionProvider → Exchange

The intent is pure: no broker IDs, no transport fields, no side effects.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal

from domain.enums import OrderType, ProductType, Side, Validity


def _new_correlation_id() -> str:
    return f"intent:{uuid.uuid4().hex}"


@dataclass(frozen=True, slots=True)
class OrderIntent:
    """User/strategy desire to trade — not yet an admitted Order.

    ``correlation_id`` is required for OMS idempotency. When omitted at
    construction time, a unique id is generated.

    Distinct from durable ledger :class:`domain.execution_contracts.OrderIntent`
    (``PersistedOrderIntent``).
    """

    symbol: str
    exchange: str
    side: Side
    quantity: int
    price: Decimal = Decimal("0")
    order_type: OrderType = OrderType.LIMIT
    product_type: ProductType = ProductType.INTRADAY
    trigger_price: Decimal | None = None
    validity: Validity = Validity.DAY
    correlation_id: str = field(default_factory=_new_correlation_id)
    tag: str | None = None

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError(f"quantity must be positive, got {self.quantity}")
        if not self.symbol:
            raise ValueError("symbol is required")
        if not (self.correlation_id or "").strip():
            object.__setattr__(self, "correlation_id", _new_correlation_id())

