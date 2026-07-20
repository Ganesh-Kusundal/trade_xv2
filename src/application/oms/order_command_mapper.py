"""Canonical OrderIntent / OrderRequest → OmsOrderCommand mapping.

Constitution P1: one mapper for all application-layer command conversion.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from application.oms.order_manager import OmsOrderCommand
from domain import OrderType, ProductType, Side
from domain.models.trading import SignalDTO
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


def position_to_close_command(
    pos: Any,
    *,
    correlation_id: str | None = None,
) -> OmsOrderCommand:
    """Map an open position to a market square-off command."""
    opposite_side = Side.SELL if pos.quantity > 0 else Side.BUY
    product_type = getattr(pos, "product_type", None) or ProductType.INTRADAY
    cid = correlation_id or f"so-{pos.symbol}-{uuid.uuid4().hex[:8]}"
    return OmsOrderCommand(
        symbol=pos.symbol,
        exchange=pos.exchange,
        side=opposite_side,
        order_type=OrderType.MARKET,
        product_type=product_type,
        quantity=abs(int(pos.quantity)),
        price=Decimal("0"),
        correlation_id=cid,
    )


def backtest_market_command(
    *,
    symbol: str,
    exchange: str,
    side: Side,
    quantity: int,
    price: Decimal,
    correlation_id: str,
    product_type: ProductType = ProductType.INTRADAY,
) -> OmsOrderCommand:
    """Map a backtest bar fill to an OMS market command."""
    return OmsOrderCommand(
        symbol=symbol,
        exchange=exchange,
        side=side,
        quantity=quantity,
        price=price,
        order_type=OrderType.MARKET,
        product_type=product_type,
        correlation_id=correlation_id,
    )


def cli_place_to_oms_command(
    *,
    symbol: str,
    exchange: str,
    side: Side,
    quantity: int,
    price: Decimal,
    order_type: OrderType,
    product_type: ProductType = ProductType.INTRADAY,
    correlation_id: str | None = None,
) -> OmsOrderCommand:
    """Map CLI/API place-order parameters to an OmsOrderCommand."""
    return OmsOrderCommand(
        symbol=symbol,
        exchange=exchange,
        side=side,
        quantity=quantity,
        price=price,
        order_type=order_type,
        product_type=product_type,
        correlation_id=correlation_id or f"cli:{uuid.uuid4().hex[:12]}",
    )


def empty_plan_oms_command(
    signal: SignalDTO,
    *,
    exchange: str,
    order_type: OrderType,
    product_type: ProductType,
    correlation_id: str,
) -> OmsOrderCommand:
    """Placeholder command when plan produced no intents (qty=0, rejected at OMS)."""
    side = Side.BUY if signal.signal_type in ("BUY", "STRONG_BUY") else Side.SELL
    return OmsOrderCommand(
        symbol=signal.symbol,
        exchange=exchange,
        side=side,
        quantity=0,
        price=Decimal(str(signal.entry_price or signal.price or 0)),
        order_type=order_type,
        product_type=product_type,
        correlation_id=correlation_id,
    )


__all__ = [
    "backtest_market_command",
    "cli_place_to_oms_command",
    "empty_plan_oms_command",
    "order_intent_to_oms_command",
    "order_request_to_oms_command",
    "position_to_close_command",
]
