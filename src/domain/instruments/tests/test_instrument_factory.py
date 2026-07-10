"""Tests for InstrumentFactory."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from domain.instruments.instrument_factory import InstrumentFactory


def test_create_equity():
    agg = InstrumentFactory.create_equity("RELIANCE", "NSE")
    assert agg.symbol == "RELIANCE"
    assert agg.exchange == "NSE"
    assert agg.asset_type == "EQUITY"


def test_create_index():
    agg = InstrumentFactory.create_index("NIFTY", "NSE")
    assert agg.symbol == "NIFTY"
    assert agg.asset_type == "INDEX"


def test_create_future():
    agg = InstrumentFactory.create_future("NIFTY", "NSE", date(2026, 7, 31))
    assert agg.asset_type == "FUTURES"


def test_create_option():
    agg = InstrumentFactory.create_option(
        "NIFTY", "NSE", date(2026, 7, 31), Decimal("25000"), "CE"
    )
    assert agg.asset_type == "OPTIONS"


def test_with_metadata():
    agg = InstrumentFactory.create_equity("TCS", "NSE", metadata={"lot_size": 1})
    assert agg.lot_size == 1
