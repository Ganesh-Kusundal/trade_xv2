"""Shared types for the TradingContext package."""

from __future__ import annotations

from dataclasses import dataclass as _dataclass


@_dataclass(frozen=True)
class CancellationResult:
    """Typed result for cancel_all_open_orders."""

    orders_cancelled: int = 0
    orders_failed: int = 0
    failed_order_ids: tuple[str, ...] = ()

    def __getitem__(self, key: str) -> int | tuple[str, ...]:
        try:
            return getattr(self, key)
        except AttributeError:
            raise KeyError(key) from None
