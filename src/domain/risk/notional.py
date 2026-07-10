"""Effective notional for pre-trade risk — pure domain math.

MARKET / zero-price orders must not collapse notional to raw quantity.
F&O uses contract multiplier (lot-aware when quantity is already in lots).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any


def resolve_effective_price(
    order_price: Decimal | float | int | str,
    *,
    ref_price: Decimal | float | int | str | None = None,
) -> Decimal | None:
    """Return a positive price for notional, or None if unavailable."""
    price = Decimal(str(order_price or 0))
    if price > 0:
        return price
    if ref_price is None:
        return None
    ref = Decimal(str(ref_price))
    return ref if ref > 0 else None


def resolve_multiplier(
    multiplier: Decimal | float | int | str | None = None,
    *,
    instrument: Any | None = None,
) -> Decimal:
    """Contract multiplier; defaults to 1 (equity)."""
    if multiplier is not None:
        m = Decimal(str(multiplier))
        return m if m > 0 else Decimal("1")
    if instrument is not None:
        raw = getattr(instrument, "multiplier", None)
        if raw is not None:
            m = Decimal(str(raw))
            if m > 0:
                return m
    return Decimal("1")


def effective_notional(
    quantity: int,
    order_price: Decimal | float | int | str,
    *,
    ref_price: Decimal | float | int | str | None = None,
    multiplier: Decimal | float | int | str | None = None,
    instrument: Any | None = None,
) -> Decimal | None:
    """qty × effective_price × multiplier, or None if no price available.

    Callers should **fail closed** (reject order) when this returns None
    for size/exposure checks — never substitute bare quantity as notional.
    """
    price = resolve_effective_price(order_price, ref_price=ref_price)
    if price is None:
        return None
    mult = resolve_multiplier(multiplier, instrument=instrument)
    return Decimal(str(abs(int(quantity)))) * price * mult


__all__ = [
    "effective_notional",
    "resolve_effective_price",
    "resolve_multiplier",
]
