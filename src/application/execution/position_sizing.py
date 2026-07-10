"""Backward-compatible re-export — use ``domain.orders.sizing`` instead."""

from domain.orders.sizing import compute_order_quantity

__all__ = ["compute_order_quantity"]
