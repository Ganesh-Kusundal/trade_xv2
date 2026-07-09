"""Shared order placement helpers — single intent builder for Session and Instrument.

KD-4 / KD-9: Instrument uses OrderServicePort only; Session may keep EP legacy.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from domain.enums import OrderType, ProductType, Side
from domain.orders.intent import OrderIntent

if TYPE_CHECKING:
    from domain.instruments.instrument import Instrument
    from domain.ports.order_service import OrderServicePort
    from domain.ports.protocols import OrderResult


def build_order_intent(
    instrument: "Instrument",
    side: Side,
    quantity: int,
    *,
    price: Decimal | None = None,
    order_type: OrderType = OrderType.LIMIT,
    product_type: ProductType = ProductType.INTRADAY,
    trigger_price: Decimal | None = None,
    correlation_id: str | None = None,
) -> OrderIntent:
    """Build a domain :class:`OrderIntent` from an instrument + order params."""
    kwargs: dict = {
        "symbol": instrument.symbol,
        "exchange": instrument.exchange,
        "side": side,
        "quantity": quantity,
        "price": price if price is not None else Decimal("0"),
        "order_type": order_type,
        "product_type": product_type,
        "trigger_price": trigger_price,
    }
    if correlation_id is not None:
        kwargs["correlation_id"] = correlation_id
    return OrderIntent(**kwargs)


def place_via_order_service(
    order_service: "OrderServicePort",
    intent: OrderIntent,
) -> "OrderResult":
    """Submit intent through OMS (risk + book + execution)."""
    return order_service.place(intent)
