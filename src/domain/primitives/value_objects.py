"""Pure domain value objects: Money, Quantity, Clock.

These are the foundational, identity-less primitives for the domain. They are
immutable, type-safe, and free of infrastructure concerns.

IMPORTANT — time is never obtained here
----------------------------------------
This module NEVER calls the wall clock directly. Obtaining the current time
would make domain logic non-deterministic and untestable. Instead, time is
obtained only through an injected :class:`Clock` whose ``now`` callable is
provided by the runtime (see ``runtime.time_service``). The concrete clock
implementations (real clock, fake/test clock) live in ``runtime.time_service``
and are *injected* — they are never imported into this module for "current
time".

That invariant is enforced by the test suite (a grep test asserts this file
contains no direct call to the wall clock).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Union

Number = Union[int, float, Decimal, str]


class DomainValueError(ValueError):
    """Raised when a value object fails construction/validation."""


def _to_decimal(value: Any, name: str) -> Decimal:
    """Coerce a numeric input to Decimal, raising ``DomainValueError`` on failure."""
    try:
        if isinstance(value, float):
            # Avoid binary float artefacts; str() round-trips faithfully.
            return Decimal(str(value))
        return Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise DomainValueError(f"{name} must be a finite number, got {value!r}") from exc


def _require_finite(amount: Decimal, name: str) -> None:
    if not amount.is_finite():
        raise DomainValueError(f"{name} must be finite, got {amount!r}")


@dataclass(frozen=True, slots=True)
class Money:
    """Monetary amount with an explicit currency — immutable Value Object.

    Only same-currency arithmetic is permitted; cross-currency operations must
    go through an explicit exchange-rate conversion. Construction normalises
    float inputs via ``str()`` and upper-cases/trims the currency code.
    """

    amount: Decimal
    currency: str = "INR"

    def __post_init__(self) -> None:
        amount = _to_decimal(self.amount, "amount")
        _require_finite(amount, "amount")
        currency = str(self.currency).strip().upper()
        if not currency:
            raise DomainValueError("currency must be a non-empty string")
        object.__setattr__(self, "amount", amount)
        object.__setattr__(self, "currency", currency)

    def to_decimal(self) -> Decimal:
        """Wire/legacy Decimal view of the amount."""
        return self.amount

    def __float__(self) -> float:
        return float(self.amount)

    def __bool__(self) -> bool:
        return self.amount != 0

    # Allow Decimal(money) / numeric coercion paths used by older call sites.
    def __decimal__(self) -> Decimal:  # pragma: no cover - not a real protocol
        return self.amount

    # -- arithmetic (same currency only; Decimal/number interoperable) --------
    def __add__(self, other: object) -> "Money":
        if isinstance(other, Money):
            if other.currency != self.currency:
                raise DomainValueError(
                    f"cannot add {self.currency!r} and {other.currency!r}; currencies differ"
                )
            return Money(self.amount + other.amount, self.currency)
        if isinstance(other, (int, float, Decimal, str)):
            return Money(self.amount + _to_decimal(other, "addend"), self.currency)
        return NotImplemented

    def __radd__(self, other: object) -> "Money":
        return self.__add__(other)

    def __sub__(self, other: object) -> "Money":
        if isinstance(other, Money):
            if other.currency != self.currency:
                raise DomainValueError(
                    f"cannot subtract {other.currency!r} from {self.currency!r}; currencies differ"
                )
            return Money(self.amount - other.amount, self.currency)
        if isinstance(other, (int, float, Decimal, str)):
            return Money(self.amount - _to_decimal(other, "subtrahend"), self.currency)
        return NotImplemented

    def __rsub__(self, other: object) -> "Money":
        if isinstance(other, (int, float, Decimal, str)):
            return Money(_to_decimal(other, "minuend") - self.amount, self.currency)
        return NotImplemented

    def __neg__(self) -> "Money":
        return Money(-self.amount, self.currency)

    def __mul__(self, other: object) -> "Money":
        if isinstance(other, Quantity):
            return Money(self.amount * other.magnitude, self.currency)
        if not isinstance(other, (int, float, Decimal, str)):
            return NotImplemented
        factor = _to_decimal(other, "multiplier")
        _require_finite(factor, "multiplier")
        return Money(self.amount * factor, self.currency)

    def __rmul__(self, other: object) -> "Money":
        return self.__mul__(other)

    def __truediv__(self, other: object) -> "Money | Decimal":
        if isinstance(other, Money):
            if other.currency != self.currency:
                raise DomainValueError("cannot divide different currencies")
            if other.amount == 0:
                raise DomainValueError("cannot divide Money by zero")
            return self.amount / other.amount  # ratio as Decimal
        if isinstance(other, (int, float, Decimal, str)):
            factor = _to_decimal(other, "divisor")
            _require_finite(factor, "divisor")
            if factor == 0:
                raise DomainValueError("cannot divide Money by zero")
            return Money(self.amount / factor, self.currency)
        return NotImplemented

    # -- ordering (Money or numeric) -----------------------------------------
    def _cmp_amount(self, other: object) -> Decimal:
        if isinstance(other, Money):
            if other.currency != self.currency:
                raise DomainValueError(
                    f"cannot compare {self.currency!r} and {other.currency!r}; currencies differ"
                )
            return self.amount - other.amount
        if isinstance(other, (int, float, Decimal, str)):
            return self.amount - _to_decimal(other, "other")
        raise TypeError(f"cannot compare Money with {type(other).__name__}")

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Money):
            return self.currency == other.currency and self.amount == other.amount
        if isinstance(other, (int, float, Decimal, str)):
            try:
                return self.amount == _to_decimal(other, "other")
            except DomainValueError:
                return False
        return NotImplemented

    def __hash__(self) -> int:
        return hash((self.amount, self.currency))

    def __lt__(self, other: object) -> bool:
        return self._cmp_amount(other) < 0

    def __le__(self, other: object) -> bool:
        return self._cmp_amount(other) <= 0

    def __gt__(self, other: object) -> bool:
        return self._cmp_amount(other) > 0

    def __ge__(self, other: object) -> bool:
        return self._cmp_amount(other) >= 0

    # -- predicates / helpers ------------------------------------------------
    def is_zero(self) -> bool:
        return self.amount == 0

    def is_positive(self) -> bool:
        return self.amount > 0

    def is_negative(self) -> bool:
        return self.amount < 0

    def abs(self) -> "Money":
        return Money(abs(self.amount), self.currency)

    def __abs__(self) -> "Money":
        return self.abs()

    def scale(self, factor: Number) -> "Money":
        return self * factor

    def __str__(self) -> str:
        return f"{self.amount:.2f} {self.currency}"

    def __repr__(self) -> str:
        return f"Money({self.amount!s}, {self.currency!r})"

    # Decimal(str(money)) often used for legacy coercion
    def __format__(self, spec: str) -> str:
        if spec:
            return format(self.amount, spec)
        return str(self)


@dataclass(frozen=True, slots=True)
class Quantity:
    """A magnitude with an optional unit/instrument context — immutable Value Object.

    ``unit`` names the instrument or measurement context (e.g. ``"NSE:INFY"``,
    ``"SHARES"``, ``"LOTS"``). Addition/subtraction require identical units;
    multiplication/division by a scalar is always allowed. ``notional`` prices
    the quantity against a per-unit :class:`Money`.
    """

    magnitude: Decimal
    unit: str = ""

    def __post_init__(self) -> None:
        magnitude = _to_decimal(self.magnitude, "magnitude")
        _require_finite(magnitude, "magnitude")
        unit = str(self.unit)
        object.__setattr__(self, "magnitude", magnitude)
        object.__setattr__(self, "unit", unit)

    def to_int(self) -> int:
        """Whole-share / lot view (truncates toward zero)."""
        return int(self.magnitude)

    def to_decimal(self) -> Decimal:
        return self.magnitude

    def __int__(self) -> int:
        return self.to_int()

    def __index__(self) -> int:
        return self.to_int()

    def __float__(self) -> float:
        return float(self.magnitude)

    def __bool__(self) -> bool:
        return self.magnitude != 0

    # -- arithmetic (same unit only for add/sub; int interoperable) ----------
    def __add__(self, other: object) -> "Quantity":
        if isinstance(other, Quantity):
            if other.unit != self.unit:
                raise DomainValueError(
                    f"cannot add unit {self.unit!r} and {other.unit!r}; units differ"
                )
            return Quantity(self.magnitude + other.magnitude, self.unit)
        if isinstance(other, (int, float, Decimal, str)):
            return Quantity(self.magnitude + _to_decimal(other, "addend"), self.unit)
        return NotImplemented

    def __radd__(self, other: object) -> "Quantity":
        return self.__add__(other)

    def __sub__(self, other: object) -> "Quantity":
        if isinstance(other, Quantity):
            if other.unit != self.unit:
                raise DomainValueError(
                    f"cannot subtract unit {other.unit!r} from {self.unit!r}; units differ"
                )
            return Quantity(self.magnitude - other.magnitude, self.unit)
        if isinstance(other, (int, float, Decimal, str)):
            return Quantity(self.magnitude - _to_decimal(other, "subtrahend"), self.unit)
        return NotImplemented

    def __rsub__(self, other: object) -> "Quantity":
        if isinstance(other, (int, float, Decimal, str)):
            return Quantity(_to_decimal(other, "minuend") - self.magnitude, self.unit)
        return NotImplemented

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Quantity):
            return self.unit == other.unit and self.magnitude == other.magnitude
        if isinstance(other, (int, float, Decimal, str)):
            try:
                return self.magnitude == _to_decimal(other, "other")
            except DomainValueError:
                return False
        return NotImplemented

    def __hash__(self) -> int:
        return hash((self.magnitude, self.unit))

    def __lt__(self, other: object) -> bool:
        if isinstance(other, Quantity):
            if other.unit != self.unit:
                raise DomainValueError("cannot compare different units")
            return self.magnitude < other.magnitude
        if isinstance(other, (int, float, Decimal, str)):
            return self.magnitude < _to_decimal(other, "other")
        return NotImplemented

    def __le__(self, other: object) -> bool:
        return self == other or self < other

    def __gt__(self, other: object) -> bool:
        if isinstance(other, Quantity):
            if other.unit != self.unit:
                raise DomainValueError("cannot compare different units")
            return self.magnitude > other.magnitude
        if isinstance(other, (int, float, Decimal, str)):
            return self.magnitude > _to_decimal(other, "other")
        return NotImplemented

    def __ge__(self, other: object) -> bool:
        return self == other or self > other

    def __neg__(self) -> "Quantity":
        return Quantity(-self.magnitude, self.unit)

    def __mul__(self, other: Number) -> "Quantity":
        if not isinstance(other, (int, float, Decimal, str)):
            return NotImplemented
        factor = _to_decimal(other, "multiplier")
        _require_finite(factor, "multiplier")
        return Quantity(self.magnitude * factor, self.unit)

    __rmul__ = __mul__

    def __truediv__(self, other: object) -> "Quantity | Decimal":
        if isinstance(other, Quantity):
            if other.magnitude == 0:
                raise DomainValueError("cannot divide Quantity by zero")
            return self.magnitude / other.magnitude  # ratio
        if not isinstance(other, (int, float, Decimal, str)):
            return NotImplemented
        factor = _to_decimal(other, "divisor")
        _require_finite(factor, "divisor")
        if factor == 0:
            raise DomainValueError("cannot divide Quantity by zero")
        return Quantity(self.magnitude / factor, self.unit)

    # -- predicates / helpers ------------------------------------------------
    def is_zero(self) -> bool:
        return self.magnitude == 0

    def abs(self) -> "Quantity":
        return Quantity(abs(self.magnitude), self.unit)

    def __abs__(self) -> "Quantity":
        return self.abs()

    def notional(self, unit_price: Money) -> Money:
        """Price this quantity at ``unit_price`` (per unit) -> Money."""
        return unit_price * self.magnitude

    def __str__(self) -> str:
        suffix = f" {self.unit}" if self.unit else ""
        return f"{self.magnitude}{suffix}"


@dataclass(frozen=True, slots=True)
class Clock:
    """Injectable time source — immutable Value Object wrapping a ``now`` callable.

    The callable is **injected** and is the *only* way to obtain the current
    time. This module never binds that callable to the wall clock directly; the
    runtime does (see ``runtime.time_service``). Domain and application code
    must receive a ``Clock`` (or ``TimeService``) via dependency injection and
    call ``clock.now()`` — they must never query the wall clock directly.

    Equality is by the wrapped callable (identity); two clocks with the same
    injected source compare equal.
    """

    _now: Callable[[], datetime]

    def now(self) -> datetime:
        return self._now()

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Clock):
            return NotImplemented
        return self._now is other._now

    def __hash__(self) -> int:
        return hash(self._now)


__all__ = ["Clock", "DomainValueError", "Money", "Quantity"]
