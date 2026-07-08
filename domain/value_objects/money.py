"""Financial value objects — Money and TickSize.

These are the basic building blocks for price and currency handling
throughout the domain.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP


@dataclass(frozen=True, slots=True)
class Money:
    """Monetary amount with currency — Value Object.

    Immutable and thread-safe.  Arithmetic operations return new instances.
    Only same-currency arithmetic is allowed; cross-currency requires an
    explicit exchange-rate conversion.
    """

    amount: Decimal
    currency: str = "INR"

    def __post_init__(self) -> None:
        # Normalise to avoid Decimal("10.0") != Decimal("10")
        if isinstance(self.amount, float):
            object.__setattr__(self, "amount", Decimal(str(self.amount)))

    def __add__(self, other: Money) -> Money:
        if self.currency != other.currency:
            raise ValueError(
                f"Cannot add {self.currency} and {other.currency}. "
                "Cross-currency requires explicit conversion."
            )
        return Money(amount=self.amount + other.amount, currency=self.currency)

    def __sub__(self, other: Money) -> Money:
        if self.currency != other.currency:
            raise ValueError(
                f"Cannot subtract {other.currency} from {self.currency}. "
                "Cross-currency requires explicit conversion."
            )
        return Money(amount=self.amount - other.amount, currency=self.currency)

    def __mul__(self, factor: int | float | Decimal) -> Money:
        return Money(amount=self.amount * Decimal(str(factor)), currency=self.currency)

    def __neg__(self) -> Money:
        return Money(amount=-self.amount, currency=self.currency)

    def __abs__(self) -> Money:
        return Money(amount=abs(self.amount), currency=self.currency)

    def __lt__(self, other: Money) -> bool:
        if self.currency != other.currency:
            raise ValueError(f"Cannot compare {self.currency} and {other.currency}")
        return self.amount < other.amount

    def __le__(self, other: Money) -> bool:
        if self.currency != other.currency:
            raise ValueError(f"Cannot compare {self.currency} and {other.currency}")
        return self.amount <= other.amount

    def __gt__(self, other: Money) -> bool:
        if self.currency != other.currency:
            raise ValueError(f"Cannot compare {self.currency} and {other.currency}")
        return self.amount > other.amount

    def __ge__(self, other: Money) -> bool:
        if self.currency != other.currency:
            raise ValueError(f"Cannot compare {self.currency} and {other.currency}")
        return self.amount >= other.amount

    def is_zero(self) -> bool:
        """Return True if the amount is exactly zero."""
        return self.amount == Decimal("0")

    def is_positive(self) -> bool:
        """Return True if the amount is positive."""
        return self.amount > Decimal("0")

    def is_negative(self) -> bool:
        """Return True if the amount is negative."""
        return self.amount < Decimal("0")

    def __str__(self) -> str:
        return f"{self.amount} {self.currency}"

    def __repr__(self) -> str:
        return f"Money({self.amount}, {self.currency!r})"


@dataclass(frozen=True, slots=True)
class TickSize:
    """Price tick size — Value Object.

    Encapsulates the minimum price movement for an instrument.
    Provides a ``round_price`` method that snaps any price to the
    nearest valid tick.
    """

    value: Decimal = Decimal("0.05")

    def __post_init__(self) -> None:
        if isinstance(self.value, float):
            object.__setattr__(self, "value", Decimal(str(self.value)))
        if self.value <= Decimal("0"):
            raise ValueError(f"TickSize must be positive, got {self.value}")

    def round_price(self, price: Decimal | float | int) -> Decimal:
        """Round *price* to the nearest valid tick.

        Uses ``ROUND_HALF_UP`` (banker's rounding is NOT used here —
        standard exchange rounding rounds .5 up).
        """
        d = Decimal(str(price))
        return (d / self.value).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * self.value

    def is_valid_price(self, price: Decimal | float | int) -> bool:
        """Return True if *price* falls exactly on a tick boundary."""
        d = Decimal(str(price))
        return (d / self.value) == (d / self.value).quantize(Decimal("1"), rounding=ROUND_HALF_UP)

    def tick_count(self, low: Decimal, high: Decimal) -> int:
        """Number of ticks between *low* and *high* (inclusive)."""
        diff = high - low
        return int((diff / self.value).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    def __str__(self) -> str:
        return f"TickSize({self.value})"
