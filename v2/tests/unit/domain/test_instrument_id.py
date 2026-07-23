"""Canonical InstrumentId — construction, serialization, equality, validation."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from domain.value_objects import InstrumentId


class TestFactories:
    def test_equity(self) -> None:
        iid = InstrumentId.equity("NSE", "reliance")
        assert str(iid) == "NSE:RELIANCE"
        assert iid.asset_type == "EQUITY"

    def test_index(self) -> None:
        iid = InstrumentId.index("NSE", "NIFTY")
        assert str(iid) == "NSE:NIFTY"
        assert iid.is_index

    def test_etf(self) -> None:
        iid = InstrumentId.etf("NSE", "NIFTYBEES")
        assert iid.asset_type == "ETF"

    def test_currency(self) -> None:
        iid = InstrumentId.currency("CDS", "USDINR")
        assert iid.asset_type == "CURRENCY"

    def test_future(self) -> None:
        iid = InstrumentId.future("NFO", "NIFTY", date(2026, 7, 30))
        assert str(iid) == "NFO:NIFTY:20260730:FUT"
        assert iid.is_future
        assert iid.right == "FUT"

    def test_commodity_future_via_mcx_auto_kind(self) -> None:
        # .future() auto-classifies MCX as COMMODITY even without kind= passed
        iid = InstrumentId.future("MCX", "CRUDEOIL", date(2026, 7, 20))
        assert iid.kind == "COMMODITY"
        assert iid.is_future

    def test_option_call(self) -> None:
        iid = InstrumentId.option("NFO", "NIFTY", date(2026, 7, 30), 25000, "CE")
        assert str(iid) == "NFO:NIFTY:20260730:25000:CE"
        assert iid.is_option
        assert iid.is_call
        assert not iid.is_put

    def test_option_put(self) -> None:
        iid = InstrumentId.option("NFO", "BANKNIFTY", date(2026, 8, 27), 58000, "PE")
        assert str(iid) == "NFO:BANKNIFTY:20260827:58000:PE"
        assert iid.is_put


class TestParseRoundTrip:
    @pytest.mark.parametrize(
        "s",
        [
            "NSE:RELIANCE",
            "NSE:NIFTY",
            "NFO:NIFTY:20260730:FUT",
            "NFO:NIFTY:20260730:25000:CE",
            "NFO:NIFTY:20260730:25000:PE",
            "BFO:SENSEX:20260827:80000:CE",
            "MCX:CRUDEOIL:20260720:FUT",
        ],
    )
    def test_str_parse_round_trip(self, s: str) -> None:
        assert str(InstrumentId.parse(s)) == s

    def test_parse_rejects_too_few_parts(self) -> None:
        with pytest.raises(ValueError, match="Invalid InstrumentId format"):
            InstrumentId.parse("RELIANCE")

    def test_parse_rejects_unknown_exchange(self) -> None:
        with pytest.raises(ValueError, match="Invalid exchange"):
            InstrumentId.parse("XYZ:FOO")

    def test_construct_rejects_invalid_right(self) -> None:
        with pytest.raises(ValueError, match="Invalid right"):
            InstrumentId(exchange="NFO", underlying="NIFTY", right="XX")

    def test_construct_rejects_invalid_kind(self) -> None:
        with pytest.raises(ValueError, match="Invalid AssetKind"):
            InstrumentId(exchange="NSE", underlying="X", kind="NOT_A_KIND")


class TestEqualityAndHashing:
    def test_equal_regardless_of_kind_metadata(self) -> None:
        """Identity is exchange/underlying/expiry/strike/right — kind is classification
        metadata, excluded from equality (mirrors legacy's .key design)."""
        a = InstrumentId(exchange="NSE", underlying="RELIANCE", kind="EQUITY")
        b = InstrumentId(exchange="NSE", underlying="RELIANCE", kind=None)
        assert a == b
        assert hash(a) == hash(b)

    def test_strike_precision_normalized(self) -> None:
        a = InstrumentId.option("NFO", "NIFTY", date(2026, 7, 30), Decimal("24000"), "CE")
        b = InstrumentId.option("NFO", "NIFTY", date(2026, 7, 30), Decimal("24000.0"), "CE")
        assert a == b
        assert hash(a) == hash(b)

    def test_different_strikes_not_equal(self) -> None:
        a = InstrumentId.option("NFO", "NIFTY", date(2026, 7, 30), 24000, "CE")
        b = InstrumentId.option("NFO", "NIFTY", date(2026, 7, 30), 24100, "CE")
        assert a != b

    def test_call_and_put_not_equal(self) -> None:
        a = InstrumentId.option("NFO", "NIFTY", date(2026, 7, 30), 24000, "CE")
        b = InstrumentId.option("NFO", "NIFTY", date(2026, 7, 30), 24000, "PE")
        assert a != b

    def test_weekly_and_monthly_expiry_not_equal(self) -> None:
        weekly = InstrumentId.option("NFO", "NIFTY", date(2026, 7, 24), 24000, "CE")
        monthly = InstrumentId.option("NFO", "NIFTY", date(2026, 7, 30), 24000, "CE")
        assert weekly != monthly

    def test_usable_as_dict_key(self) -> None:
        d = {InstrumentId.equity("NSE", "RELIANCE"): 1}
        assert d[InstrumentId.equity("NSE", "reliance")] == 1
