"""Concrete Specification subclasses + factory — Tier 2-F.

Guarantees:
* Each instrument type exposes correct lot_size / tick_size / margin_factor.
* validate_quantity accepts positive multiples of lot_size and rejects others.
* validate_price accepts tick-aligned positive prices and rejects the rest.
* get_specification(instrument) returns the matching concrete subclass.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from domain.instruments.instrument import Equity, Future, Index, Option
from domain.instruments.instrument_id import InstrumentId
from domain.specifications import (
    EquitySpecification,
    FutureSpecification,
    IndexSpecification,
    OptionSpecification,
    Specification,
    get_specification,
)

# ── Construction / shape ──────────────────────────────────────────────────


def test_equity_spec_shape():
    spec = EquitySpecification()
    assert isinstance(spec, Specification)
    assert spec.instrument_type == "EQUITY"
    assert spec.lot_size == 1
    assert spec.tick_size == Decimal("0.05")
    assert spec.margin_factor == Decimal("1.0")
    assert spec.is_tradeable


def test_future_spec_shape():
    spec = FutureSpecification(lot_size=50, tick_size=Decimal("0.05"), margin_factor=Decimal("0.2"))
    assert spec.instrument_type == "FUTURES"
    assert spec.lot_size == 50
    assert spec.tick_size == Decimal("0.05")
    assert spec.margin_factor == Decimal("0.2")


def test_option_spec_shape():
    spec = OptionSpecification(lot_size=75, tick_size=Decimal("0.05"), margin_factor=Decimal("0.5"))
    assert spec.instrument_type == "OPTIONS"
    assert spec.lot_size == 75
    assert spec.margin_factor == Decimal("0.5")


def test_index_spec_not_tradeable():
    spec = IndexSpecification(tick_size=Decimal("0.05"))
    assert spec.instrument_type == "INDEX"
    assert spec.lot_size == 1
    assert spec.is_tradeable is False


def test_future_rejects_bad_lot_size():
    import pytest

    with pytest.raises(ValueError):
        FutureSpecification(lot_size=0)
    with pytest.raises(ValueError):
        OptionSpecification(lot_size=-5)


# ── validate_quantity ─────────────────────────────────────────────────────


def test_equity_validate_quantity():
    spec = EquitySpecification()
    assert spec.validate_quantity(1)
    assert spec.validate_quantity(100)
    assert not spec.validate_quantity(0)
    assert not spec.validate_quantity(-5)


def test_future_validate_quantity():
    spec = FutureSpecification(lot_size=50)
    assert spec.validate_quantity(50)
    assert spec.validate_quantity(150)
    assert not spec.validate_quantity(30)
    assert not spec.validate_quantity(0)
    assert not spec.validate_quantity(-50)


def test_option_validate_quantity():
    spec = OptionSpecification(lot_size=75)
    assert spec.validate_quantity(75)
    assert spec.validate_quantity(225)
    assert not spec.validate_quantity(50)
    assert not spec.validate_quantity(1)


# ── validate_price ────────────────────────────────────────────────────────


def test_equity_validate_price_tick_aligned():
    spec = EquitySpecification(tick_size=Decimal("0.05"))
    assert spec.validate_price(Decimal("100.00"))
    assert spec.validate_price(Decimal("100.05"))
    assert spec.validate_price(Decimal("99.95"))
    assert not spec.validate_price(Decimal("100.03"))  # off-tick
    assert not spec.validate_price(Decimal("0"))       # non-positive
    assert not spec.validate_price(Decimal("-1.00"))


def test_future_validate_price_custom_tick():
    spec = FutureSpecification(lot_size=50, tick_size=Decimal("0.25"))
    assert spec.validate_price(Decimal("250.00"))
    assert spec.validate_price(Decimal("250.25"))
    assert not spec.validate_price(Decimal("250.10"))  # off 0.25 grid
    assert not spec.validate_price(Decimal("0"))


def test_option_validate_price():
    spec = OptionSpecification(lot_size=75, tick_size=Decimal("0.05"))
    assert spec.validate_price(Decimal("12.50"))
    assert not spec.validate_price(Decimal("12.53"))


# ── Factory ───────────────────────────────────────────────────────────────


def test_factory_equity():
    inst = Equity("RELIANCE")
    spec = get_specification(inst)
    assert isinstance(spec, EquitySpecification)
    assert spec.instrument_type == "EQUITY"
    assert spec.lot_size == 1


def test_factory_future_uses_instrument_lot_and_tick():
    inst = Future(
        "NIFTY",
        expiry=date(2026, 7, 31),
        metadata={"lot_size": 50, "tick_size": "0.05"},
    )
    spec = get_specification(inst)
    assert isinstance(spec, FutureSpecification)
    assert spec.lot_size == 50
    assert spec.tick_size == Decimal("0.05")


def test_factory_option():
    iid = InstrumentId.option("NFO", "NIFTY", date(2026, 7, 31), 25000, "CE")
    inst = Option(
        iid,
        strike=Decimal("25000"),
        expiry=date(2026, 7, 31),
        right="CE",
        metadata={"lot_size": 75, "tick_size": "0.05"},
    )
    spec = get_specification(inst)
    assert isinstance(spec, OptionSpecification)
    assert spec.lot_size == 75


def test_factory_index():
    inst = Index("NIFTY")
    spec = get_specification(inst)
    assert isinstance(spec, IndexSpecification)
    assert spec.is_tradeable is False


def test_factory_returns_specification_subclass():
    spec = get_specification(Equity("INFY"))
    assert isinstance(spec, Specification)
