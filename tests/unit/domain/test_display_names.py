"""TH-2: TradeHull-style display name parse / format."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from domain.instruments.display_names import format_display_name, parse_display_name
from domain.instruments.instrument_id import InstrumentId


class TestParseEquityIndex:
    def test_bare_equity(self):
        iid = parse_display_name("RELIANCE")
        assert iid == InstrumentId.equity("NSE", "RELIANCE")

    def test_bare_index_auto(self):
        iid = parse_display_name("NIFTY")
        assert iid.is_index
        assert iid.underlying == "NIFTY"

    def test_bare_index_force(self):
        # Equity/index share InstrumentId shape; treat_as_index uses index factory path
        iid = parse_display_name("CUSTOM", treat_as_index=True)
        assert iid.underlying == "CUSTOM"
        assert iid.exchange == "NSE"
        assert iid.expiry is None

    def test_canonical_passthrough(self):
        iid = parse_display_name("NFO:NIFTY:20261121:24400:CE")
        assert iid.is_option
        assert iid.strike == Decimal("24400")


class TestParseOption:
    def test_tradehull_call(self):
        iid = parse_display_name(
            "NIFTY 21 NOV 24400 CALL",
            default_year=2026,
        )
        assert iid == InstrumentId.option("NFO", "NIFTY", date(2026, 11, 21), 24400, "CE")

    def test_ce_alias(self):
        iid = parse_display_name("BANKNIFTY 26 JUN 52000 CE", default_year=2026)
        assert iid.right == "CE"
        assert iid.underlying == "BANKNIFTY"
        assert iid.strike == Decimal("52000")

    def test_put_with_year(self):
        iid = parse_display_name("NIFTY 21 NOV 2025 24000 PUT")
        assert iid.expiry == date(2025, 11, 21)
        assert iid.right == "PE"

    def test_format_roundtrip_option(self):
        iid = InstrumentId.option("NFO", "NIFTY", date(2026, 11, 21), 24400, "CE")
        display = format_display_name(iid)
        assert display == "NIFTY 21 NOV 24400 CALL"
        back = parse_display_name(display, default_year=2026)
        assert back == iid


class TestParseFuture:
    def test_future_with_day(self):
        iid = parse_display_name("NIFTY 27 NOV FUT", default_year=2026)
        assert iid == InstrumentId.future("NFO", "NIFTY", date(2026, 11, 27))

    def test_commodity_mcx(self):
        iid = parse_display_name("CRUDEOIL 19 NOV FUT", default_year=2026)
        assert iid.exchange == "MCX"
        assert iid.is_future

    def test_format_future(self):
        iid = InstrumentId.future("NFO", "NIFTY", date(2026, 11, 27))
        assert format_display_name(iid) == "NIFTY 27 NOV FUT"


class TestParseErrors:
    def test_empty(self):
        with pytest.raises(ValueError, match="Empty"):
            parse_display_name("  ")

    def test_garbage(self):
        with pytest.raises(ValueError, match="Unrecognized"):
            parse_display_name("not a real instrument name!!!")


class TestFormatEquity:
    def test_equity(self):
        assert format_display_name(InstrumentId.equity("NSE", "RELIANCE")) == "RELIANCE"

    def test_from_string(self):
        assert format_display_name("NSE:INFY") == "INFY"
