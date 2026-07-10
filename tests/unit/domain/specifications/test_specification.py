"""Tests for Specification ABC."""

from __future__ import annotations

from decimal import Decimal

import pytest

from domain.specifications import Specification


class EquitySpec(Specification):
    @property
    def instrument_type(self) -> str:
        return "EQUITY"

    @property
    def lot_size(self) -> int:
        return 1

    @property
    def tick_size(self) -> Decimal:
        return Decimal("0.05")


class FutureSpec(Specification):
    @property
    def instrument_type(self) -> str:
        return "FUTURES"

    @property
    def lot_size(self) -> int:
        return 50

    @property
    def tick_size(self) -> Decimal:
        return Decimal("0.05")

    @property
    def margin_factor(self) -> Decimal:
        return Decimal("0.2")


def test_cannot_instantiate_abc():
    with pytest.raises(TypeError):
        Specification()  # type: ignore[abstract]


def test_equity_spec_validate_quantity():
    spec = EquitySpec()
    assert spec.validate_quantity(1)
    assert spec.validate_quantity(5)
    assert not spec.validate_quantity(0)
    assert not spec.validate_quantity(-1)


def test_equity_spec_validate_price():
    spec = EquitySpec()
    assert spec.validate_price(Decimal("100.05"))
    assert spec.validate_price(Decimal("100"))
    assert not spec.validate_price(Decimal("100.03"))
    assert not spec.validate_price(Decimal("0"))


def test_future_spec_lot_size():
    spec = FutureSpec()
    assert spec.lot_size == 50
    assert spec.validate_quantity(50)
    assert spec.validate_quantity(100)
    assert not spec.validate_quantity(30)
    assert spec.margin_factor == Decimal("0.2")


def test_default_margin_factor():
    spec = EquitySpec()
    assert spec.margin_factor == Decimal("1.0")


def test_default_is_tradeable():
    spec = EquitySpec()
    assert spec.is_tradeable
