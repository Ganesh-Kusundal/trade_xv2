"""Shared order validation logic for all broker adapters.

Centralizes lot-size and tick-alignment checks that were previously
duplicated across brokers/providers/dhan/execution/order_validator.py and
brokers/providers/upstox/orders/order_command_adapter.py.
"""

from __future__ import annotations

from decimal import Decimal

from domain.constants.market import DEFAULT_TICK_SIZE


def validate_lot_size(quantity: int, lot_size: int, symbol: str, exchange: str) -> str | None:
    """Check that quantity is a multiple of lot_size.

    Returns an error message string if invalid, None if valid.
    """
    if lot_size > 1 and quantity % lot_size != 0:
        return (
            f"Quantity {quantity} is not a multiple of lot size {lot_size} "
            f"for {symbol} on {exchange}"
        )
    return None


def validate_tick_alignment(
    price: Decimal,
    tick_size: Decimal | float | None,
    symbol: str,
) -> str | None:
    """Check that price aligns to tick_size.

    Returns an error message string if invalid, None if valid.
    """
    if price is None or price <= 0:
        return None

    tick = Decimal(str(tick_size)) if tick_size is not None else DEFAULT_TICK_SIZE
    if tick <= 0:
        return None

    from domain.value_objects.price import is_tick_aligned

    if not is_tick_aligned(price, tick):
        return f"Price {price} is not aligned to tick size {tick} for {symbol}"
    return None
