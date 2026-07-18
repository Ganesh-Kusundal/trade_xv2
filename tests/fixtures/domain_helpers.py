"""Shared test fixture helpers for OMS tests.

Canonical factory functions for creating Order, Position, and Trade objects
in tests.  Each function accepts keyword arguments with sensible defaults
and returns a domain entity ready for use in test assertions.

Usage::

    from tests.fixtures.domain_helpers import make_order, make_trade, make_position

    order = make_order(symbol="RELIANCE", side="BUY", qty=100, price="2500")
    trade = make_trade(order=order, quantity=50, price="2505")
    position = make_position(symbol="RELIANCE", quantity=100, avg_price="2500")
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from domain import Order, OrderStatus, OrderType, ProductType, Side, Trade, Validity
from domain.entities import Position


def make_order(
    *,
    symbol: str = "RELIANCE",
    exchange: str = "NSE",
    side: Side | str = Side.BUY,
    quantity: int = 10,
    filled_quantity: int = 0,
    price: Decimal | float | str = Decimal("2500"),
    order_type: OrderType | str = OrderType.LIMIT,
    product_type: ProductType | str = ProductType.INTRADAY,
    status: OrderStatus | str = OrderStatus.OPEN,
    order_id: str = "",
    trigger_price: Decimal | float | str = Decimal("0"),
    validity: Validity | str = Validity.DAY,
    correlation_id: str = "",
    avg_price: Decimal | float | str = Decimal("0"),
    timestamp: datetime | None = None,
) -> Order:
    """Create an Order with sensible defaults for testing.

    All fields can be overridden via keyword arguments.
    """
    if isinstance(side, str):
        side = Side(side)
    if isinstance(order_type, str):
        order_type = OrderType(order_type)
    if isinstance(product_type, str):
        product_type = ProductType(product_type)
    if isinstance(status, str):
        status = OrderStatus(status)
    if isinstance(validity, str):
        validity = Validity(validity)

    return Order(
        order_id=order_id,
        symbol=symbol,
        exchange=exchange,
        side=side,
        order_type=order_type,
        quantity=quantity,
        filled_quantity=filled_quantity,
        price=Decimal(str(price)) if not isinstance(price, Decimal) else price,
        trigger_price=Decimal(str(trigger_price)) if not isinstance(trigger_price, Decimal) else trigger_price,
        product_type=product_type,
        status=status,
        validity=validity,
        correlation_id=correlation_id,
        avg_price=Decimal(str(avg_price)) if not isinstance(avg_price, Decimal) else avg_price,
        timestamp=timestamp or datetime.now(timezone.utc),
    )


def make_trade(
    *,
    trade_id: str = "",
    order_id: str = "",
    symbol: str = "RELIANCE",
    exchange: str = "NSE",
    side: Side | str = Side.BUY,
    quantity: int = 10,
    price: Decimal | float | str = Decimal("2505"),
    timestamp: str | None = None,
) -> Trade:
    """Create a Trade with sensible defaults for testing."""
    if isinstance(side, str):
        side = Side(side)

    return Trade(
        trade_id=trade_id or f"T-{order_id or '001'}",
        order_id=order_id,
        symbol=symbol,
        exchange=exchange,
        side=side,
        quantity=quantity,
        price=Decimal(str(price)) if not isinstance(price, Decimal) else price,
        timestamp=timestamp,
    )


def make_position(
    *,
    symbol: str = "RELIANCE",
    exchange: str = "NSE",
    quantity: int = 100,
    avg_price: Decimal | float | str = Decimal("2500"),
    ltp: Decimal | float | str = Decimal("2500"),
    unrealized_pnl: Decimal | float | str = Decimal("0"),
    realized_pnl: Decimal | float | str = Decimal("0"),
    product_type: ProductType | str = ProductType.INTRADAY,
) -> Position:
    """Create a Position with sensible defaults for testing."""
    if isinstance(product_type, str):
        product_type = ProductType(product_type)

    return Position(
        symbol=symbol,
        exchange=exchange,
        quantity=quantity,
        avg_price=Decimal(str(avg_price)) if not isinstance(avg_price, Decimal) else avg_price,
        ltp=Decimal(str(ltp)) if not isinstance(ltp, Decimal) else ltp,
        unrealized_pnl=Decimal(str(unrealized_pnl)) if not isinstance(unrealized_pnl, Decimal) else unrealized_pnl,
        realized_pnl=Decimal(str(realized_pnl)) if not isinstance(realized_pnl, Decimal) else realized_pnl,
        product_type=product_type,
    )
