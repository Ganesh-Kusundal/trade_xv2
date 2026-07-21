"""Config-gated paper simulation knobs (env-driven, default off/neutral)."""

from __future__ import annotations

import os
from decimal import Decimal

from domain import Side


def _env_decimal(name: str, default: str) -> Decimal:
    try:
        return Decimal(os.getenv(name, default))
    except Exception:
        return Decimal(default)


def paper_slippage_bps() -> Decimal:
    """Slippage in basis points applied against the trader on market fills."""
    return _env_decimal("TRADEX_PAPER_SLIPPAGE_BPS", "0")


def paper_partial_fill_ratio() -> Decimal:
    """Fraction of order quantity filled per tick (1.0 = full fill)."""
    ratio = _env_decimal("TRADEX_PAPER_PARTIAL_FILL_RATIO", "1")
    if ratio <= 0:
        return Decimal("1")
    if ratio > 1:
        return Decimal("1")
    return ratio


def paper_fill_outside_hours() -> bool:
    """When True (default), paper fills are allowed outside exchange hours."""
    return os.getenv("TRADEX_PAPER_FILL_OUTSIDE_HOURS", "true").lower() not in ("0", "false", "no")


def apply_slippage(price: Decimal, side: Side) -> Decimal:
    """Worsen fill price by configured bps (BUY pays more, SELL receives less)."""
    bps = paper_slippage_bps()
    if bps <= 0 or price <= 0:
        return price
    adj = price * bps / Decimal("10000")
    return price + adj if side == Side.BUY else max(Decimal("0"), price - adj)


def partial_fill_quantity(quantity: int) -> int:
    ratio = paper_partial_fill_ratio()
    if ratio >= 1:
        return quantity
    filled = int(Decimal(quantity) * ratio)
    return max(1, min(quantity, filled))
