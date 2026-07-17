"""Order quantity sizing — pure domain math for pre-trade position size.

Used by analytics engines and the trading orchestrator to convert equity +
max-position-% into a whole-share order quantity.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum


def _to_decimal(value: object) -> Decimal:
    """Coerce a numeric scalar or Money value object to Decimal.

    ``Money`` is now a first-class value object in the domain (TOS-P1-004);
    sizing inputs such as ``existing_notional`` can arrive as ``Money``, so we
    unwrap it via ``to_decimal()`` instead of ``str()`` (which yields an
    unparseable ``"1234.56 INR"``).
    """
    if hasattr(value, "to_decimal"):
        return value.to_decimal()
    return Decimal(str(value))


class SizingMethod(str, Enum):
    """How a position size was derived."""

    PCT_EQUITY = "PCT_EQUITY"
    ATR = "ATR"
    FIXED = "FIXED"


def compute_order_quantity(
    *,
    equity: Decimal | int | float,
    price: Decimal | int | float,
    max_position_pct: Decimal | int | float,
) -> int:
    equity_d = _to_decimal(equity)
    price_d = _to_decimal(price)
    pct_d = _to_decimal(max_position_pct)
    if price_d <= 0 or equity_d <= 0 or pct_d <= 0:
        return 0
    max_notional = equity_d * (pct_d / Decimal("100"))
    return max(0, int(max_notional / price_d))


def compute_remaining_quantity(
    *,
    equity: Decimal | int | float,
    max_position_pct: Decimal | int | float,
    price: Decimal | int | float,
    existing_notional: Decimal | int | float = 0,
) -> int:
    """Position-aware size: ``capital * pct`` minus *already-held* notional.

    This is the position-aware counterpart to :func:`compute_order_quantity`.
    Subtracting ``existing_notional`` is what stops a strategy from
    pyramiding past its limit when it re-signals a symbol it already holds.
    """
    equity_d = _to_decimal(equity)
    price_d = _to_decimal(price)
    pct_d = _to_decimal(max_position_pct)
    existing = _to_decimal(existing_notional)
    if price_d <= 0 or equity_d <= 0 or pct_d <= 0:
        return 0
    max_notional = equity_d * (pct_d / Decimal("100"))
    remaining = max(Decimal("0"), max_notional - existing)
    return max(0, int(remaining / price_d))


def compute_atr_quantity(
    *,
    equity: Decimal | int | float,
    atr: Decimal | int | float,
    risk_pct: Decimal | int | float,
    atr_multiplier: Decimal | int | float = 2,
) -> int:
    """Volatility-scaled size: risk budget ÷ risk-per-share.

    The per-trade risk budget is ``equity * risk_pct``. The risk per share is
    ``atr * atr_multiplier`` (the adverse move we are willing to absorb). The
    resulting share count keeps the per-share risk inside the budget.
    """
    equity_d = _to_decimal(equity)
    atr_d = _to_decimal(atr)
    risk_d = _to_decimal(risk_pct)
    mult = _to_decimal(atr_multiplier)
    if atr_d <= 0 or equity_d <= 0 or risk_d <= 0:
        return 0
    risk_budget = equity_d * (risk_d / Decimal("100"))
    risk_per_share = atr_d * mult
    if risk_per_share <= 0:
        return 0
    return max(0, int(risk_budget / risk_per_share))


__all__ = [
    "SizingMethod",
    "compute_atr_quantity",
    "compute_order_quantity",
    "compute_remaining_quantity",
]
