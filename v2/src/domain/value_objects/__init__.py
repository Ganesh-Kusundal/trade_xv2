"""Frozen value objects — Decimal for money/price/qty, UUID for CorrelationId."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True, slots=True)
class InstrumentId:
    value: str


@dataclass(frozen=True, slots=True)
class OrderId:
    value: str


@dataclass(frozen=True, slots=True)
class AccountId:
    value: str


@dataclass(frozen=True, slots=True)
class StrategyId:
    value: str


@dataclass(frozen=True, slots=True)
class ComponentId:
    value: str


@dataclass(frozen=True, slots=True)
class CorrelationId:
    value: UUID


@dataclass(frozen=True, slots=True)
class TimeFrame:
    value: str


@dataclass(frozen=True, slots=True)
class Timestamp:
    """Nanosecond UTC precision timestamp."""
    value: int


@dataclass(frozen=True, slots=True)
class Price:
    value: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.value, Decimal):
            raise TypeError("Price.value must be Decimal")

    def __mul__(self, other: Quantity | Decimal) -> Decimal:
        if isinstance(other, Quantity):
            return self.value * other.value
        return self.value * other


@dataclass(frozen=True, slots=True)
class Quantity:
    value: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.value, Decimal):
            raise TypeError("Quantity.value must be Decimal")

    def __mul__(self, other: Price | Decimal) -> Decimal:
        if isinstance(other, Price):
            return other.value * self.value
        return self.value * other


@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Decimal):
            raise TypeError("Money.amount must be Decimal")

    def _check_currency(self, other: Money) -> None:
        if self.currency != other.currency:
            raise ValueError(f"currency mismatch: {self.currency} vs {other.currency}")

    def __add__(self, other: Money) -> Money:
        self._check_currency(other)
        return Money(amount=self.amount + other.amount, currency=self.currency)

    def __sub__(self, other: Money) -> Money:
        self._check_currency(other)
        return Money(amount=self.amount - other.amount, currency=self.currency)

    def __mul__(self, factor: Decimal) -> Money:
        return Money(amount=self.amount * factor, currency=self.currency)
