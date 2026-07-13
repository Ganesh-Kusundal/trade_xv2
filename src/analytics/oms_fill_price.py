"""Resolve the fill price OMS actually booked (slippage applied once in the adapter).

Paper/replay session capital must use this price — not the un-slipped base passed
into ``OmsBacktestAdapter`` — or session equity drifts from the OMS book (F2d).
"""

from __future__ import annotations

from decimal import Decimal

from domain.trading_costs import apply_slippage


def resolve_oms_fill_price(
    oms_adapter: object,
    order_id: str,
    *,
    base_price: Decimal,
    side: str,
    slippage_pct: float,
) -> float:
    """Return OMS booked fill price for ``order_id``, else recompute once via apply_slippage."""
    fills = getattr(oms_adapter, "fills", None) or ()
    for fill in reversed(list(fills)):
        if getattr(fill, "order_id", None) == order_id:
            return float(fill.price)
    return float(apply_slippage(base_price, side=side, slippage_pct=slippage_pct))
