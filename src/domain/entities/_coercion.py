"""Shared coercion helpers for entity value objects."""

from __future__ import annotations

from decimal import Decimal

from domain.primitives import Money, Quantity


def _as_money(value: Money | Decimal | int | float | str | None) -> Money:
    if value is None:
        return Money(0)
    if isinstance(value, Money):
        return value
    return Money(value)


def _as_quantity(value: Quantity | Decimal | int | float | str | None) -> Quantity:
    if value is None:
        return Quantity(0)
    if isinstance(value, Quantity):
        return value
    return Quantity(value)
