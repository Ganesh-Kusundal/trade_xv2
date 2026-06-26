"""Tests for domain.instrument_id — canonical instrument identity."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from domain.instrument_id import InstrumentId


class TestFactoryMethods:
    """Test factory methods for different asset types."""

    def test_equity(self):
        iid = InstrumentId.equity("NSE", "RELIANCE")
        assert iid.exchange == "NSE"
        assert iid.underlying == "RELIANCE"
        assert iid.expiry is None
        assert iid.strike is None
        assert iid.right is None
        assert iid.asset_type == "EQUITY"

    def test_index(self):
        iid = InstrumentId.index("NSE", "NIFTY")
        assert iid.underlying == "NIFTY"
        assert iid.asset_type == "INDEX"

    def test_future(self):
        iid = InstrumentId.future("NFO", "NIFTY", date(2026, 7, 30))
        assert iid.exchange == "NFO"
        assert iid.underlying == "NIFTY"
        assert iid.expiry == date(2026, 7, 30)
        assert iid.right == "FUT"
        assert iid.asset_type == "FUTURES"

    def test_option(self):
        iid = InstrumentId.option("NFO", "NIFTY", date(2026, 7, 30), 25000, "CE")
        assert iid.strike == Decimal("25000")
        assert iid.right == "CE"
        assert iid.asset_type == "OPTIONS"

    def test_option_put(self):
        iid = InstrumentId.option("NFO", "BANKNIFTY", date(2026, 6, 26), 55000, "PE")
        assert iid.right == "PE"
        assert iid.is_put

    def test_factory_normalizes_case(self):
        iid = InstrumentId.equity("nse", "reliance")
        assert iid.exchange == "NSE"
        assert iid.underlying == "RELIANCE"


class TestSerialization:
    """Test string serialization."""

    def test_equity_str(self):
        iid = InstrumentId.equity("NSE", "RELIANCE")
        assert str(iid) == "NSE:RELIANCE"

    def test_index_str(self):
        iid = InstrumentId.index("NSE", "NIFTY")
        assert str(iid) == "NSE:NIFTY"

    def test_future_str(self):
        iid = InstrumentId.future("NFO", "NIFTY", date(2026, 7, 30))
        assert str(iid) == "NFO:NIFTY:20260730:FUT"

    def test_option_str(self):
        iid = InstrumentId.option("NFO", "NIFTY", date(2026, 7, 30), 25000, "CE")
        assert str(iid) == "NFO:NIFTY:20260730:25000:CE"

    def test_option_put_str(self):
        iid = InstrumentId.option("MCX", "CRUDEOIL", date(2026, 7, 19), 6500, "PE")
        assert str(iid) == "MCX:CRUDEOIL:20260719:6500:PE"

    def test_repr(self):
        iid = InstrumentId.equity("NSE", "RELIANCE")
        assert repr(iid) == "InstrumentId(NSE:RELIANCE)"


class TestParsing:
    """Test string deserialization."""

    def test_parse_equity(self):
        iid = InstrumentId.parse("NSE:RELIANCE")
        assert iid == InstrumentId.equity("NSE", "RELIANCE")

    def test_parse_index(self):
        iid = InstrumentId.parse("NSE:NIFTY")
        assert iid == InstrumentId.index("NSE", "NIFTY")

    def test_parse_future(self):
        iid = InstrumentId.parse("NFO:NIFTY:20260730:FUT")
        assert iid == InstrumentId.future("NFO", "NIFTY", date(2026, 7, 30))

    def test_parse_option(self):
        iid = InstrumentId.parse("NFO:NIFTY:20260730:25000:CE")
        assert iid == InstrumentId.option("NFO", "NIFTY", date(2026, 7, 30), 25000, "CE")

    def test_parse_option_put(self):
        iid = InstrumentId.parse("MCX:CRUDEOIL:20260719:6500:PE")
        assert iid == InstrumentId.option("MCX", "CRUDEOIL", date(2026, 7, 19), 6500, "PE")

    def test_roundtrip(self):
        """Serialization → parsing should produce identical object."""
        original = InstrumentId.option("NFO", "BANKNIFTY", date(2026, 6, 26), 55000, "PE")
        parsed = InstrumentId.parse(str(original))
        assert parsed == original

    def test_parse_invalid_format(self):
        with pytest.raises(ValueError, match="Invalid InstrumentId format"):
            InstrumentId.parse("INVALID")

    def test_parse_case_insensitive(self):
        iid = InstrumentId.parse("nfo:nifty:20260730:25000:ce")
        assert iid.exchange == "NFO"
        assert iid.right == "CE"


class TestEquality:
    """Test equality and hashing."""

    def test_equal_ids(self):
        a = InstrumentId.option("NFO", "NIFTY", date(2026, 7, 30), 25000, "CE")
        b = InstrumentId.option("NFO", "NIFTY", date(2026, 7, 30), 25000, "CE")
        assert a == b
        assert hash(a) == hash(b)

    def test_different_ids(self):
        a = InstrumentId.option("NFO", "NIFTY", date(2026, 7, 30), 25000, "CE")
        b = InstrumentId.option("NFO", "NIFTY", date(2026, 7, 30), 25000, "PE")
        assert a != b

    def test_usable_as_dict_key(self):
        iid = InstrumentId.equity("NSE", "RELIANCE")
        d = {iid: "value"}
        assert d[iid] == "value"

    def test_usable_in_set(self):
        a = InstrumentId.equity("NSE", "RELIANCE")
        b = InstrumentId.equity("NSE", "RELIANCE")
        s = {a, b}
        assert len(s) == 1


class TestProperties:
    """Test asset type detection and convenience properties."""

    def test_equity_properties(self):
        iid = InstrumentId.equity("NSE", "RELIANCE")
        assert iid.is_equity
        assert not iid.is_index
        assert not iid.is_future
        assert not iid.is_option

    def test_index_properties(self):
        iid = InstrumentId.index("NSE", "NIFTY")
        assert iid.is_index
        assert not iid.is_equity

    def test_future_properties(self):
        iid = InstrumentId.future("NFO", "NIFTY", date(2026, 7, 30))
        assert iid.is_future
        assert iid.right == "FUT"

    def test_option_properties(self):
        iid = InstrumentId.option("NFO", "NIFTY", date(2026, 7, 30), 25000, "CE")
        assert iid.is_option
        assert iid.is_call
        assert not iid.is_put

    def test_put_properties(self):
        iid = InstrumentId.option("NFO", "NIFTY", date(2026, 7, 30), 25000, "PE")
        assert iid.is_put
        assert not iid.is_call


class TestValidation:
    """Test input validation."""

    def test_invalid_exchange(self):
        with pytest.raises(ValueError, match="Invalid exchange"):
            InstrumentId(exchange="INVALID", underlying="RELIANCE")

    def test_invalid_right(self):
        with pytest.raises(ValueError, match="Invalid right"):
            InstrumentId(exchange="NSE", underlying="RELIANCE", right="INVALID")

    def test_valid_exchanges(self):
        for exch in ["NSE", "BSE", "NFO", "MCX"]:
            iid = InstrumentId(exchange=exch, underlying="TEST")
            assert iid.exchange == exch

    def test_valid_rights(self):
        for right in ["CE", "PE", "FUT"]:
            iid = InstrumentId(exchange="NFO", underlying="NIFTY", right=right)
            assert iid.right == right


class TestConvenience:
    """Test helper methods."""

    def test_with_expiry(self):
        original = InstrumentId.option("NFO", "NIFTY", date(2026, 6, 26), 25000, "CE")
        new = original.with_expiry(date(2026, 7, 30))
        assert new.expiry == date(2026, 7, 30)
        assert new.strike == original.strike
        assert new.right == original.right

    def test_with_strike(self):
        original = InstrumentId.option("NFO", "NIFTY", date(2026, 7, 30), 25000, "CE")
        new = original.with_strike(26000)
        assert new.strike == Decimal("26000")
        assert new.expiry == original.expiry

    def test_to_equity(self):
        option = InstrumentId.option("NFO", "NIFTY", date(2026, 7, 30), 25000, "CE")
        equity = option.to_equity()
        assert equity == InstrumentId.equity("NFO", "NIFTY")
        assert equity.expiry is None
        assert equity.strike is None
