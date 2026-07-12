"""Concrete per-instrument-type Specification subclasses.

These turn the :class:`Specification` contract into usable, reusable rules for
equity, futures, options and index instruments. Each subclass pins the
``instrument_type`` and exposes ``lot_size`` / ``tick_size`` / ``margin_factor``;
quantity/price validation is centralized on the ABC (with tick alignment
delegated to the :class:`TickSize` value object reused from
``domain.value_objects.money``).

Design notes
------------
* Subclasses are constructed from explicit values so they can be unit-tested
  without a full :class:`Instrument` (the factory wires them to instruments).
* ``tick_size`` is stored as a :class:`TickSize` value object and surfaced as a
  ``Decimal`` via the ABC property; ``validate_price`` delegates to
  ``TickSize.is_valid_price`` for correct tick-boundary rounding.
* Margin factors are *typical* defaults and can be overridden per instance.
"""

from __future__ import annotations

from decimal import Decimal

from domain.constants.market import DEFAULT_TICK_SIZE
from domain.specifications.specification import Specification
from domain.value_objects.money import TickSize

# Typical margin requirements as a fraction of notional (exchange/segment
# defaults; real values come from the risk module / clearing corporation).
_EQUITY_MARGIN: Decimal = Decimal("1.0")   # cash segment: full margin
_FUTURE_MARGIN: Decimal = Decimal("0.2")   # SPAN-style initial margin fraction
_OPTION_MARGIN: Decimal = Decimal("0.5")   # short-option style margin fraction


class _BaseConcreteSpec(Specification):
    """Shared machinery for concrete specs: tick alignment + margin storage."""

    _tick: TickSize
    _margin: Decimal

    def validate_price(self, price: Decimal) -> bool:
        """Tick-aligned price check delegated to the TickSize value object."""
        if price is None or price <= 0:
            return False
        return self._tick.is_valid_price(price)

    @property
    def tick_size(self) -> Decimal:
        return self._tick.value

    @property
    def margin_factor(self) -> Decimal:
        return self._margin


class EquitySpecification(_BaseConcreteSpec):
    """Equity (and ETF / spot / currency) trading rules.

    Equities trade in lot size 1; tick size is exchange-specific (default
    ``DEFAULT_TICK_SIZE``). Cash segment carries full (1.0) margin.
    """

    def __init__(
        self,
        *,
        tick_size: Decimal | str | float = DEFAULT_TICK_SIZE,
        margin_factor: Decimal | str | float = _EQUITY_MARGIN,
    ) -> None:
        self._tick = TickSize(tick_size)
        self._margin = Decimal(str(margin_factor))

    @property
    def instrument_type(self) -> str:
        return "EQUITY"

    @property
    def lot_size(self) -> int:
        return 1


class FutureSpecification(_BaseConcreteSpec):
    """Futures trading rules.

    Lot size comes from the instrument's contract; tick size is per-underlying.
    Margin is a fraction of notional (SPAN-style, default 0.2).
    """

    def __init__(
        self,
        *,
        lot_size: int,
        tick_size: Decimal | str | float = DEFAULT_TICK_SIZE,
        margin_factor: Decimal | str | float = _FUTURE_MARGIN,
    ) -> None:
        if int(lot_size) < 1:
            raise ValueError(f"Future lot_size must be >= 1, got {lot_size}")
        self._lot = int(lot_size)
        self._tick = TickSize(tick_size)
        self._margin = Decimal(str(margin_factor))

    @property
    def instrument_type(self) -> str:
        return "FUTURES"

    @property
    def lot_size(self) -> int:
        return self._lot


class OptionSpecification(_BaseConcreteSpec):
    """Options trading rules.

    Options trade in contract lots (>= 1); tick size is per-option. Margin is a
    fraction of premium-plus-notional (default 0.5).
    """

    def __init__(
        self,
        *,
        lot_size: int,
        tick_size: Decimal | str | float = DEFAULT_TICK_SIZE,
        margin_factor: Decimal | str | float = _OPTION_MARGIN,
    ) -> None:
        if int(lot_size) < 1:
            raise ValueError(f"Option lot_size must be >= 1, got {lot_size}")
        self._lot = int(lot_size)
        self._tick = TickSize(tick_size)
        self._margin = Decimal(str(margin_factor))

    @property
    def instrument_type(self) -> str:
        return "OPTIONS"

    @property
    def lot_size(self) -> int:
        return self._lot


class IndexSpecification(_BaseConcreteSpec):
    """Index trading rules.

    Indices are not directly tradeable (you trade futures/options on them), so
    ``is_tradeable`` is ``False``. Lot size is 1 and tick size per-index.
    """

    def __init__(
        self,
        *,
        tick_size: Decimal | str | float = DEFAULT_TICK_SIZE,
        margin_factor: Decimal | str | float = _EQUITY_MARGIN,
    ) -> None:
        self._tick = TickSize(tick_size)
        self._margin = Decimal(str(margin_factor))

    @property
    def instrument_type(self) -> str:
        return "INDEX"

    @property
    def lot_size(self) -> int:
        return 1

    @property
    def is_tradeable(self) -> bool:
        return False
