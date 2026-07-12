"""Tests for pure domain value objects: Money, Quantity, Clock.

Proves:
- The VO module is pure: it never calls ``datetime.now()``.
- Money/Quantity arithmetic, equality, ordering, and validation work.
- Clock is injected (no internal ``datetime.now``), behaviour driven by caller.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from domain.primitives.value_objects import (
    Clock,
    DomainValueError,
    Money,
    Quantity,
)

VO_MODULE = Path(__file__).resolve().parents[4] / "src" / "domain" / "primitives" / "value_objects.py"


class TestModuleIsPure:
    def test_no_datetime_now_in_module(self):
        """DR-D2: the VO module must never call datetime.now() directly."""
        source = VO_MODULE.read_text(encoding="utf-8")
        assert "datetime.now()" not in source, "value_objects.py must not call datetime.now()"
        assert "datetime.now(" not in source, "value_objects.py must not obtain 'now' internally"

    def test_module_imports_cleanly(self):
        import domain.primitives.value_objects as vo

        assert inspect.ismodule(vo)


class TestMoney:
    def test_construction_normalises_float_and_currency(self):
        m = Money(10.5, "inr")
        assert m.amount == Decimal("10.5")
        assert m.currency == "INR"

    def test_equality_by_value(self):
        assert Money(100, "INR") == Money(Decimal("100"), "INR")
        assert Money(100, "INR") != Money(100, "USD")
        assert Money(100, "INR") != Money(200, "INR")

    def test_addition_same_currency(self):
        assert Money(40, "INR") + Money(60, "INR") == Money(100, "INR")

    def test_addition_cross_currency_raises(self):
        with pytest.raises(DomainValueError):
            _ = Money(1, "INR") + Money(1, "USD")

    def test_subtraction_negation(self):
        assert Money(60, "INR") - Money(10, "INR") == Money(50, "INR")
        assert -Money(5, "INR") == Money(-5, "INR")

    def test_multiplication_and_division_by_scalar(self):
        assert Money(10, "INR") * 3 == Money(30, "INR")
        assert 3 * Money(10, "INR") == Money(30, "INR")
        assert Money(30, "INR") / 2 == Money(15, "INR")

    def test_division_by_zero_raises(self):
        with pytest.raises(DomainValueError):
            _ = Money(10, "INR") / 0

    def test_ordering_same_currency(self):
        assert Money(10, "INR") < Money(20, "INR")
        assert Money(20, "INR") >= Money(20, "INR")
        with pytest.raises(DomainValueError):
            _ = Money(1, "INR") < Money(1, "USD")

    def test_immutability(self):
        m = Money(10, "INR")
        with pytest.raises(AttributeError):
            m.amount = Decimal("99")  # type: ignore[misc]

    def test_validation_rejects_non_finite_and_empty_currency(self):
        with pytest.raises(DomainValueError):
            Money("not-a-number", "INR")
        with pytest.raises(DomainValueError):
            Money(10, "")
        with pytest.raises(DomainValueError):
            Money(float("inf"), "INR")

    def test_predicates_and_scale(self):
        assert Money(0, "INR").is_zero()
        assert Money(5, "INR").is_positive()
        assert Money(-5, "INR").is_negative()
        assert Money(10, "INR").scale(2) == Money(20, "INR")
        assert Money(-10, "INR").abs() == Money(10, "INR")


class TestQuantity:
    def test_construction(self):
        q = Quantity(25, "NSE:INFY")
        assert q.magnitude == Decimal("25")
        assert q.unit == "NSE:INFY"

    def test_equality_by_value_and_unit(self):
        assert Quantity(10, "LOTS") == Quantity(Decimal("10"), "LOTS")
        assert Quantity(10, "LOTS") != Quantity(10, "SHARES")

    def test_addition_same_unit(self):
        assert Quantity(5, "LOTS") + Quantity(3, "LOTS") == Quantity(8, "LOTS")

    def test_addition_cross_unit_raises(self):
        with pytest.raises(DomainValueError):
            _ = Quantity(1, "LOTS") + Quantity(1, "SHARES")

    def test_scalar_arithmetic_and_negation(self):
        assert Quantity(10, "X") * 2 == Quantity(20, "X")
        assert 2 * Quantity(10, "X") == Quantity(20, "X")
        assert Quantity(20, "X") / 4 == Quantity(5, "X")
        assert -Quantity(4, "X") == Quantity(-4, "X")

    def test_notional_prices_against_money(self):
        price = Money(100, "INR")
        assert Quantity(5, "SHARES").notional(price) == Money(500, "INR")

    def test_ordering_and_immutability(self):
        assert Quantity(1, "U") < Quantity(2, "U")
        with pytest.raises(DomainValueError):
            _ = Quantity(1, "A") < Quantity(1, "B")
        q = Quantity(1, "U")
        with pytest.raises(AttributeError):
            q.magnitude = Decimal("9")  # type: ignore[misc]


class TestClock:
    def test_clock_is_injected_and_pure(self):
        fixed = datetime(2021, 6, 1, 12, 0, tzinfo=timezone.utc)
        clock = Clock(_now=lambda: fixed)
        assert clock.now() == fixed
        # no internal binding to datetime.now: two clocks with same source eq
        clock2 = Clock(_now=lambda: fixed)
        assert clock == clock  # identical instance
        assert clock != clock2  # different injected callables -> not identical

    def test_clock_drives_domain_time_without_datetime_now(self):
        calls: list[datetime] = []

        def fake_now() -> datetime:
            t = datetime(2022, 1, 1, tzinfo=timezone.utc)
            calls.append(t)
            return t

        clock = Clock(_now=fake_now)
        # Simulate domain logic using the injected clock.
        first = clock.now()
        assert first == datetime(2022, 1, 1, tzinfo=timezone.utc)
        assert len(calls) == 1
