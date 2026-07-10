"""Order quantity sizing — pure domain math for pre-trade position size.

Used by analytics engines and the trading orchestrator to convert equity +
max-position-% into a whole-share order quantity.
"""

from __future__ import annotations

from decimal import Decimal


def compute_order_quantity(
    *,
    equity: Decimal | int | float,
    price: Decimal | int | float,
    max_position_pct: Decimal | int | float,
) -> int:
    equity_d = Decimal(str(equity))
    price_d = Decimal(str(price))
    pct_d = Decimal(str(max_position_pct))
    if price_d <= 0 or equity_d <= 0 or pct_d <= 0:
        return 0
    max_notional = equity_d * (pct_d / Decimal("100"))
    return max(0, int(max_notional / price_d))


__all__ = ["compute_order_quantity"]
