"""ExecutionManager — coordinates order placement through the OMS spine.

Thin coordinator over the composition-root ``Session`` buy/sell. Risk → intent
→ OMS → ExecutionProvider all live in the session; this just forwards.

M6: Every buy/sell delegates through :func:`brokers.services._session.check_live_actionable`
so Spine A (BrokerSession → ExecutionManager → Session) shares the same
production-readiness gate as Spine B (brokers/services/orders.py).
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from domain.instruments.instrument import Instrument
    from domain.universe import Session


class ExecutionManager:
    """Coordinates order submission for a session's instruments."""

    def __init__(self, session: Session, *, broker_id: str = "paper") -> None:
        self._session = session
        self._broker_id = broker_id

    def buy(
        self,
        instrument: Instrument,
        quantity: int,
        price: Decimal | None = None,
        order_type: str = "LIMIT",
        product_type: str = "INTRADAY",
    ) -> Any:
        from brokers.services._session import check_live_actionable

        check_live_actionable(self._broker_id)
        return self._session.buy(
            instrument, quantity, price, order_type=order_type, product_type=product_type
        )

    def sell(
        self,
        instrument: Instrument,
        quantity: int,
        price: Decimal | None = None,
        order_type: str = "LIMIT",
        product_type: str = "INTRADAY",
    ) -> Any:
        from brokers.services._session import check_live_actionable

        check_live_actionable(self._broker_id)
        return self._session.sell(
            instrument, quantity, price, order_type=order_type, product_type=product_type
        )

    def orders(self) -> list[Any]:
        return self._session.orders()
