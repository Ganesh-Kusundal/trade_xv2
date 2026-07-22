"""PricingService — pure calculation service for pricing operations."""

from __future__ import annotations

from decimal import Decimal


class PricingService:
    """Pure calculation helpers for pricing. No I/O."""

    @staticmethod
    def vwap(prices: list[Decimal], quantities: list[Decimal]) -> Decimal:
        if len(prices) != len(quantities) or not prices:
            raise ValueError("prices and quantities must be non-empty and same length")
        total_value = sum(p * q for p, q in zip(prices, quantities))
        total_qty = sum(quantities)
        return total_value / total_qty

    @staticmethod
    def slippage_bps(expected_price: Decimal, fill_price: Decimal) -> Decimal:
        if expected_price == Decimal("0"):
            raise ValueError("expected_price must not be zero")
        diff = fill_price - expected_price
        return (diff / expected_price * Decimal("10000")).quantize(Decimal("1"))
