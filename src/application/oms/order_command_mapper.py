"""Canonical OrderIntent / OrderRequest → OmsOrderCommand mapping.

Constitution P1: one mapper for all application-layer command conversion.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from application.oms.order_manager import OmsOrderCommand
from domain import Side
from domain.orders.intent import OrderIntent
from domain.orders.requests import OrderRequest


def order_intent_to_oms_command(intent: OrderIntent) -> OmsOrderCommand:
    """Map a domain :class:`OrderIntent` to an :class:`OmsOrderCommand`."""
    return OmsOrderCommand(
        symbol=intent.symbol,
        exchange=intent.exchange,
        side=intent.side,
        quantity=intent.quantity,
        price=intent.price,
        order_type=intent.order_type,
        product_type=intent.product_type,
        correlation_id=intent.correlation_id,
    )


def order_request_to_oms_command(request: OrderRequest) -> OmsOrderCommand:
    """Map a domain :class:`OrderRequest` to an :class:`OmsOrderCommand`."""
    side = request.transaction_type
    if not isinstance(side, Side):
        side = Side(str(side).upper())
    raw_price = request.price
    try:
        price = Decimal(str(raw_price)) if raw_price is not None else Decimal("0")
    except Exception:
        price = Decimal("0")
    return OmsOrderCommand(
        symbol=request.symbol,
        exchange=request.exchange,
        side=side,
        quantity=int(request.quantity),
        price=price,
        order_type=request.order_type,
        product_type=request.product_type,
        correlation_id=request.correlation_id or str(uuid.uuid4()),
    )


__all__ = ["order_intent_to_oms_command", "order_request_to_oms_command"]
