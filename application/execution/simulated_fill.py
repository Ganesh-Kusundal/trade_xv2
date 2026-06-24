"""Shared simulated fill logic for paper, replay, and backtest modes."""

from __future__ import annotations

import itertools
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable

from domain import Order, OrderStatus, ProductType, Side, Trade
from application.oms.order_manager import OmsOrderCommand


def apply_slippage(price: Decimal, *, side: Side | str, slippage_pct: float = 0.0) -> Decimal:
    """Apply per-side slippage. Buy = price up, Sell = price down."""
    if slippage_pct == 0:
        return price
    side_val = side.value if isinstance(side, Side) else str(side).upper()
    factor = (1 + slippage_pct / 100) if side_val == "BUY" else (1 - slippage_pct / 100)
    return (price * Decimal(str(factor))).quantize(Decimal("0.0001"))


def make_simulated_submit_fn(
    command: OmsOrderCommand,
    *,
    timestamp: datetime | None = None,
    order_id_prefix: str = "sim",
) -> Callable[[OmsOrderCommand], Order]:
    """Build a submit_fn that returns an OPEN order for OMS processing."""

    def _submit(req: OmsOrderCommand) -> Order:
        oid = f"{order_id_prefix}-{uuid.uuid4().hex[:12]}"
        return Order(
            order_id=oid,
            symbol=req.symbol,
            exchange=req.exchange,
            side=req.side,
            order_type=req.order_type,
            quantity=req.quantity,
            filled_quantity=0,
            price=req.price,
            product_type=req.product_type,
            status=OrderStatus.OPEN,
            timestamp=timestamp,
            correlation_id=req.correlation_id,
        )

    return _submit


_backtest_seq = itertools.count(1)


def build_backtest_correlation_id(
    symbol: str,
    side: Side | str,
    *,
    prefix: str = "bt",
) -> str:
    """Build a unique correlation ID for backtest orders.

    Uses a monotonic counter (``itertools.count`` — atomic, no GIL reliance)
    plus UUID fragment to guarantee uniqueness even when called rapidly.
    """
    seq = next(_backtest_seq)
    side_val = side.value if isinstance(side, Side) else str(side).upper()
    return f"{prefix}:{seq}:{uuid.uuid4().hex[:8]}:{symbol}:{side_val}"


def record_simulated_trade(
    order_manager: Any,
    *,
    order_id: str,
    symbol: str,
    exchange: str,
    side: Side,
    quantity: int,
    price: Decimal,
    timestamp: datetime,
    product_type: ProductType = ProductType.INTRADAY,
) -> Trade | None:
    """Record a fill through OrderManager.record_trade."""
    trade = Trade(
        trade_id=f"{order_id}:{quantity}",
        order_id=order_id,
        symbol=symbol,
        exchange=exchange,
        side=side,
        quantity=quantity,
        price=price,
        trade_value=price * Decimal(str(quantity)),
        timestamp=timestamp,
        product_type=product_type,
    )
    if order_manager.record_trade(trade):
        return trade
    return None
