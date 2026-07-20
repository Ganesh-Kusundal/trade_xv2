"""Tests for domain.instrument_resolver — strategy DSL resolution."""

from __future__ import annotations

from datetime import date

import pytest

from domain.instrument_resolver import parse_selector, resolve_selector
from domain.instruments.instrument_id import InstrumentId


class TestParseSelector:
    """Test selector parsing without resolution."""

    def test_parse_equity(self):
        result = parse_selector("RELIANCE")
        assert result["underlying"] == "RELIANCE"
        assert result["kind"] is None

    def test_parse_option(self):
        result = parse_selector("NIFTY_WEEK_0_ATM_CE")
        assert result["underlying"] == "NIFTY"
        assert result["kind"] == "WEEK"
        assert result["offset"] == 0
        assert result["strike_ref"] == "ATM"
        assert result["right"] == "CE"

    def test_parse_future(self):
        result = parse_selector("NIFTY_FUT_CURRENT")
        assert result["underlying"] == "NIFTY"
        assert result["kind"] == "FUT"
        assert result["right"] == "FUT"

    def test_parse_put(self):
        result = parse_selector("BANKNIFTY_MONTH_1_ATM_PE")
        assert result["underlying"] == "BANKNIFTY"
        assert result["kind"] == "MONTH"
        assert result["offset"] == 1
        assert result["right"] == "PE"


class TestResolveEquity:
    """Test equity resolution."""

    def test_equity_passthrough(self):
        iid = resolve_selector("RELIANCE", exchange="NSE")
        assert iid == InstrumentId.equity("NSE", "RELIANCE")

    def test_equity_case_insensitive(self):
        iid = resolve_selector("reliance", exchange="NSE")
        assert iid == InstrumentId.equity("NSE", "RELIANCE")


class TestResolveFuture:
    """Test future resolution."""

    def test_future_current(self):
        iid = resolve_selector("NIFTY_FUT_CURRENT", reference_date=date(2026, 6, 25))
        assert iid.is_future
        assert iid.underlying == "NIFTY"
        assert iid.right == "FUT"
        # Should resolve to a Thursday
        assert iid.expiry.weekday() == 3  # Thursday

    def test_future_offset(self):
        iid = resolve_selector("NIFTY_FUT_1", reference_date=date(2026, 6, 25))
        assert iid.is_future
        # offset=1 should be next week's Thursday
        assert iid.expiry.weekday() == 3


class TestResolveOption:
    """Test option resolution."""

    def test_atm_call(self):
        iid = resolve_selector("NIFTY_WEEK_0_ATM_CE", spot=25000, reference_date=date(2026, 6, 25))
        assert iid.is_option
        assert iid.is_call
        assert iid.underlying == "NIFTY"
        assert iid.strike == 25000
        assert iid.right == "CE"

    def test_atm_put(self):
        iid = resolve_selector("NIFTY_WEEK_0_ATM_PE", spot=25000, reference_date=date(2026, 6, 25))
        assert iid.is_put
        assert iid.strike == 25000

    def test_atm_nearest_strike(self):
        iid = resolve_selector("NIFTY_WEEK_0_ATM_CE", spot=25023, reference_date=date(2026, 6, 25))
        assert iid.strike == 25000  # Rounded to nearest 50

    def test_atm_requires_spot(self):
        with pytest.raises(ValueError, match="Spot price required"):
            resolve_selector("NIFTY_WEEK_0_ATM_CE")

    def test_otm_strike(self):
        iid = resolve_selector("NIFTY_WEEK_0_OTM1_CE", spot=25000, reference_date=date(2026, 6, 25))
        assert iid.strike == 25050  # OTM1 = 1 tick above ATM

    def test_itm_strike(self):
        iid = resolve_selector("NIFTY_WEEK_0_ITM1_CE", spot=25000, reference_date=date(2026, 6, 25))
        assert iid.strike == 24950  # ITM1 = 1 tick below ATM

    def test_monthly_option(self):
        iid = resolve_selector("NIFTY_MONTH_0_ATM_CE", spot=25000, reference_date=date(2026, 6, 25))
        assert iid.is_option
        assert iid.underlying == "NIFTY"
        # Monthly expiry should be a Thursday
        assert iid.expiry.weekday() == 3
        # Monthly expiry should be in the future relative to reference
        assert iid.expiry >= date(2026, 6, 25)


class TestInvalidSelectors:
    """Test error handling."""

    def test_invalid_format(self):
        with pytest.raises(ValueError, match="Cannot parse"):
            resolve_selector("NIFTY_INVALID_FORMAT")

    def test_missing_right(self):
        with pytest.raises(ValueError, match="Cannot parse"):
            resolve_selector("NIFTY_WEEK_0_ATM")
