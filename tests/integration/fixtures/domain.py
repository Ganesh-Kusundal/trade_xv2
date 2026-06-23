"""Shared domain object factories for integration tests.

Provides reusable factories for creating domain entities (Order, Trade, Position, Balance)
in a consistent manner across all integration tests.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from brokers.common.core.domain import (
    Balance,
    DepthLevel,
    Holding,
    MarketDepth,
    Order,
    OrderStatus,
    OrderType,
    Position,
    ProductType,
    Quote,
    Side,
    Trade,
)


def make_order(
    order_id: str = "TEST-ORD-001",
    symbol: str = "RELIANCE",
    exchange: str = "NSE",
    side: Side = Side.BUY,
    order_type: OrderType = OrderType.LIMIT,
    quantity: int = 10,
    filled_quantity: int = 0,
    price: Decimal = Decimal("2550.00"),
    status: OrderStatus = OrderStatus.OPEN,
    product_type: ProductType = ProductType.INTRADAY,
    avg_price: Decimal | None = None,
    timestamp: datetime | None = None,
) -> Order:
    """Create an Order instance with sensible defaults.

    Args:
        order_id: Unique order identifier
        symbol: Trading symbol
        exchange: Exchange name (NSE, BSE, NFO, etc.)
        side: BUY or SELL
        order_type: MARKET, LIMIT, SL, SL-M
        quantity: Order quantity
        filled_quantity: Already filled quantity
        price: Limit price (ignored for MARKET orders)
        status: Current order status
        product_type: INTRADAY, DELIVERY, MARGIN, etc.
        avg_price: Average fill price (auto-calculated if None)
        timestamp: Order timestamp (defaults to now UTC)

    Returns:
        Configured Order instance
    """
    return Order(
        order_id=order_id,
        symbol=symbol,
        exchange=exchange,
        side=side,
        order_type=order_type,
        quantity=quantity,
        filled_quantity=filled_quantity,
        price=price,
        status=status,
        product_type=product_type,
        avg_price=avg_price or price,
        timestamp=timestamp or datetime.now(timezone.utc),
    )


def make_trade(
    trade_id: str = "TEST-TRD-001",
    order_id: str = "TEST-ORD-001",
    symbol: str = "RELIANCE",
    exchange: str = "NSE",
    side: Side = Side.BUY,
    quantity: int = 10,
    price: Decimal = Decimal("2550.00"),
    timestamp: datetime | None = None,
) -> Trade:
    """Create a Trade instance with sensible defaults.

    Args:
        trade_id: Unique trade identifier
        order_id: Associated order ID
        symbol: Trading symbol
        exchange: Exchange name
        side: BUY or SELL
        quantity: Trade quantity
        price: Trade price
        timestamp: Trade timestamp (defaults to now UTC)

    Returns:
        Configured Trade instance
    """
    return Trade(
        trade_id=trade_id,
        order_id=order_id,
        symbol=symbol,
        exchange=exchange,
        side=side,
        quantity=quantity,
        price=price,
        timestamp=timestamp or datetime.now(timezone.utc),
    )


def make_position(
    symbol: str = "RELIANCE",
    exchange: str = "NSE",
    quantity: int = 10,
    avg_price: Decimal = Decimal("2550.00"),
    ltp: Decimal = Decimal("2565.50"),
    unrealized_pnl: Decimal | None = None,
    realized_pnl: Decimal = Decimal("0.00"),
    product_type: ProductType = ProductType.INTRADAY,
) -> Position:
    """Create a Position instance with sensible defaults.

    Args:
        symbol: Trading symbol
        exchange: Exchange name
        quantity: Net position quantity
        avg_price: Average entry price
        ltp: Last traded price
        unrealized_pnl: Auto-calculated if None
        realized_pnl: Realized P&L from closed positions
        product_type: Position product type

    Returns:
        Configured Position instance
    """
    if unrealized_pnl is None:
        unrealized_pnl = (ltp - avg_price) * quantity

    return Position(
        symbol=symbol,
        exchange=exchange,
        quantity=quantity,
        avg_price=avg_price,
        ltp=ltp,
        unrealized_pnl=unrealized_pnl,
        realized_pnl=realized_pnl,
        product_type=product_type,
    )


def make_balance(
    available_balance: Decimal = Decimal("100000.00"),
    used_margin: Decimal = Decimal("0.00"),
    total_balance: Decimal | None = None,
) -> Balance:
    """Create a Balance instance with sensible defaults.

    Args:
        available_balance: Available funds for trading
        used_margin: Margin currently in use
        total_balance: Auto-calculated if None (available + used)

    Returns:
        Configured Balance instance
    """
    if total_balance is None:
        total_balance = available_balance + used_margin

    return Balance(
        available_balance=available_balance,
        used_margin=used_margin,
        total_balance=total_balance,
    )


def make_quote(
    symbol: str = "RELIANCE",
    exchange: str = "NSE",
    ltp: Decimal = Decimal("2550.00"),
    open: Decimal = Decimal("2540.00"),
    high: Decimal = Decimal("2560.00"),
    low: Decimal = Decimal("2535.00"),
    close: Decimal = Decimal("2545.00"),
    volume: int = 500000,
) -> Quote:
    """Create a Quote instance with sensible defaults.

    Args:
        symbol: Trading symbol
        exchange: Exchange name
        ltp: Last traded price
        open: Day open price
        high: Day high price
        low: Day low price
        close: Previous close price
        volume: Traded volume

    Returns:
        Configured Quote instance
    """
    return Quote(
        symbol=symbol,
        exchange=exchange,
        ltp=ltp,
        open=open,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


def make_market_depth(
    symbol: str = "RELIANCE",
    exchange: str = "NSE",
    bids: list[DepthLevel] | None = None,
    asks: list[DepthLevel] | None = None,
) -> MarketDepth:
    """Create a MarketDepth instance with sensible defaults.

    Args:
        symbol: Trading symbol
        exchange: Exchange name
        bids: List of bid depth levels (defaults to 5 levels)
        asks: List of ask depth levels (defaults to 5 levels)

    Returns:
        Configured MarketDepth instance
    """
    if bids is None:
        bids = [
            DepthLevel(price=Decimal("2550.00"), quantity=100, orders=5),
            DepthLevel(price=Decimal("2549.50"), quantity=200, orders=8),
            DepthLevel(price=Decimal("2549.00"), quantity=150, orders=6),
            DepthLevel(price=Decimal("2548.50"), quantity=300, orders=10),
            DepthLevel(price=Decimal("2548.00"), quantity=250, orders=7),
        ]

    if asks is None:
        asks = [
            DepthLevel(price=Decimal("2550.50"), quantity=120, orders=6),
            DepthLevel(price=Decimal("2551.00"), quantity=180, orders=9),
            DepthLevel(price=Decimal("2551.50"), quantity=160, orders=7),
            DepthLevel(price=Decimal("2552.00"), quantity=280, orders=11),
            DepthLevel(price=Decimal("2552.50"), quantity=220, orders=8),
        ]

    return MarketDepth(
        symbol=symbol,
        exchange=exchange,
        bids=bids,
        asks=asks,
    )


def make_holding(
    symbol: str = "INFY",
    exchange: str = "NSE",
    quantity: int = 20,
    available_quantity: int | None = None,
    avg_price: Decimal = Decimal("1420.00"),
    ltp: Decimal = Decimal("1435.00"),
    pnl: Decimal | None = None,
) -> Holding:
    """Create a Holding instance with sensible defaults.

    Args:
        symbol: Trading symbol
        exchange: Exchange name
        quantity: Total holding quantity
        available_quantity: T+1 available quantity (defaults to quantity)
        avg_price: Average purchase price
        ltp: Last traded price
        pnl: Auto-calculated if None

    Returns:
        Configured Holding instance
    """
    if available_quantity is None:
        available_quantity = quantity

    if pnl is None:
        pnl = (ltp - avg_price) * quantity

    return Holding(
        symbol=symbol,
        exchange=exchange,
        quantity=quantity,
        available_quantity=available_quantity,
        avg_price=avg_price,
        ltp=ltp,
        pnl=pnl,
    )
