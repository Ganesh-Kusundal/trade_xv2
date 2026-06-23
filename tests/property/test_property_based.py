"""Property-based tests using Hypothesis for edge case discovery.

These tests verify that financial calculations, order parsing, and status
mapping hold their invariants across a wide range of inputs.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

import hypothesis.strategies as st
import pandas as pd
import pytest
from hypothesis import given, settings, strategies as st

from domain import OrderStatus, Side, OrderType
from brokers.common.status_mapper import StatusMapperRegistry
from domain.entities import Order, Position, Trade

# Order limits (inline since not in constants yet)
MAX_ORDER_QUANTITY = 1000000
MAX_ORDER_VALUE = Decimal("100000000")


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Valid decimal price values (avoiding extremely large/small numbers)
price_strategy = st.decimals(
    min_value=Decimal("0.01"),
    max_value=Decimal("1000000"),
    places=2,
    allow_nan=False,
    allow_infinity=False,
)

# Valid quantities
quantity_strategy = st.integers(min_value=1, max_value=MAX_ORDER_QUANTITY)

# Valid order IDs
order_id_strategy = st.text(min_size=1, max_size=50, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-")

# Valid symbols
symbol_strategy = st.text(min_size=1, max_size=20, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.")


# ---------------------------------------------------------------------------
# Property: Order Creation Invariants
# ---------------------------------------------------------------------------


@given(
    order_id=order_id_strategy,
    symbol=symbol_strategy,
    quantity=quantity_strategy,
    price=price_strategy,
)
@settings(max_examples=100)
def test_order_creation_invariants(order_id: str, symbol: str, quantity: int, price: Decimal) -> None:
    """Orders maintain invariants regardless of input."""
    order = Order(
        order_id=order_id,
        symbol=symbol,
        exchange="NSE",
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        quantity=quantity,
        price=price,
    )

    # Invariant: remaining_quantity is always >= 0
    assert order.remaining_quantity >= 0

    # Invariant: remaining_quantity <= quantity
    assert order.remaining_quantity <= order.quantity

    # Invariant: price is non-negative
    assert order.price >= Decimal("0")

    # Invariant: quantity is positive
    assert order.quantity > 0


@given(
    filled_qty=st.integers(min_value=0, max_value=1000),
    total_qty=st.integers(min_value=1, max_value=1000),
)
def test_order_fill_invariants(filled_qty: int, total_qty: int) -> None:
    """Fill operations maintain order state invariants."""
    order = Order(
        order_id="TEST-001",
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        quantity=total_qty,
        price=Decimal("1000"),
    )

    # Apply fill
    actual_fill = min(filled_qty, total_qty)  # Can't fill more than total
    filled_order = order.with_fill(actual_fill, Decimal("1000"))

    # Invariant: filled_quantity <= quantity
    assert filled_order.filled_quantity <= filled_order.quantity

    # Invariant: remaining_quantity = quantity - filled_quantity
    assert filled_order.remaining_quantity == filled_order.quantity - filled_order.filled_quantity


# ---------------------------------------------------------------------------
# Property: Position PnL Calculations
# ---------------------------------------------------------------------------


@given(
    quantity=st.integers(min_value=-1000, max_value=1000).filter(lambda q: q != 0),
    avg_price=price_strategy,
    ltp=price_strategy,
)
def test_position_pnl_symmetry(quantity: int, avg_price: Decimal, ltp: Decimal) -> None:
    """PnL calculation is symmetric for long/short positions."""
    position = Position(
        symbol="RELIANCE",
        exchange="NSE",
        quantity=quantity,
        avg_price=avg_price,
    )

    # Update with LTP
    updated = position.with_ltp(ltp)

    # Invariant: PnL sign matches position direction
    if quantity > 0:  # Long: profit when price goes up
        if ltp > avg_price:
            assert updated.unrealized_pnl >= 0
        else:
            assert updated.unrealized_pnl <= 0
    else:  # Short: profit when price goes down
        if ltp < avg_price:
            assert updated.unrealized_pnl >= 0
        else:
            assert updated.unrealized_pnl <= 0


@given(
    qty1=quantity_strategy,
    qty2=quantity_strategy,
    price1=price_strategy,
    price2=price_strategy,
)
def test_position_averaging_invariant(qty1: int, qty2: int, price1: Decimal, price2: Decimal) -> None:
    """Multiple fills produce correct average price."""
    position = Position(symbol="RELIANCE", exchange="NSE")

    # Apply two fills in same direction
    pos1 = position.with_fill(qty1, price1)
    pos2 = pos1.with_fill(qty2, price2)

    # Total quantity
    total_qty = qty1 + qty2

    if total_qty > 0:
        # Invariant: average price should be between the two fill prices
        min_price = min(price1, price2)
        max_price = max(price1, price2)
        assert min_price <= pos2.avg_price <= max_price


# ---------------------------------------------------------------------------
# Property: Status Mapping
# ---------------------------------------------------------------------------


@given(
    status_str=st.one_of(
        st.just("OPEN"),
        st.just("COMPLETE"),
        st.just("CANCELLED"),
        st.just("REJECTED"),
        st.just("PARTIALLY_FILLED"),
        st.just("PENDING"),  # Dhan-specific
        st.just("TRANSIT"),  # Dhan-specific
        st.just("OPEN_ORDER"),  # Upstox-specific
        st.just("MODIFIED"),  # Upstox-specific
    )
)
def test_status_mapping_always_returns_valid_status(status_str: str) -> None:
    """Status mapper never raises for known broker status strings."""
    # Should always return a valid OrderStatus
    status = StatusMapperRegistry.normalize(status_str)
    assert isinstance(status, OrderStatus)
    assert status in OrderStatus


# ---------------------------------------------------------------------------
# Property: Trade Value Calculation
# ---------------------------------------------------------------------------


@given(
    quantity=quantity_strategy,
    price=price_strategy,
)
def test_trade_value_positive(quantity: int, price: Decimal) -> None:
    """Trade value is always non-negative."""
    trade = Trade(
        trade_id="T-001",
        order_id="O-001",
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        quantity=quantity,
        price=price,
    )

    # Invariant: trade value is positive
    assert trade.value >= Decimal("0")

    # Invariant: trade value = price * quantity (approximately)
    expected_value = price * quantity
    assert trade.value == expected_value or trade.trade_value == expected_value


# ---------------------------------------------------------------------------
# Property: Scanner Score Bounds
# ---------------------------------------------------------------------------


@given(
    rsi=st.floats(min_value=0.0, max_value=100.0),
    roc=st.floats(min_value=-50.0, max_value=50.0),
    trend=st.sampled_from(["up", "down", "neutral"]),
    volume=st.floats(min_value=0.0, max_value=10.0),
    momentum=st.floats(min_value=-20.0, max_value=20.0),
)
def test_scanner_score_bounds(
    rsi: float,
    roc: float,
    trend: str,
    volume: float,
    momentum: float,
) -> None:
    """Scanner composite scores are always in [0, 100] range."""
    from analytics.scanner.scanners import MomentumScanner

    # Create a single-row DataFrame
    df = pd.DataFrame({
        "symbol": ["TEST"],
        "rsi": [rsi],
        "roc": [roc],
        "trend": [trend],
        "relative_volume": [volume],
        "momentum": [momentum],
    })

    scanner = MomentumScanner(top_n=10)
    scored = scanner._score(df)

    # Invariant: all score columns in [0, 100]
    for col in ["score_rsi", "score_roc", "score_trend", "score_volume", "score_momentum", "composite_score"]:
        if col in scored.columns:
            val = scored[col].iloc[0]
            assert 0.0 <= val <= 100.0, f"{col} = {val} out of bounds"
