"""Futures basis = futures − spot."""

from __future__ import annotations

from decimal import Decimal


def basis(futures: float | Decimal, spot: float | Decimal) -> float | Decimal:
    return futures - spot
