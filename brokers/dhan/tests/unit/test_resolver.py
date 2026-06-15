"""Unit tests for SymbolResolver."""

import pytest

from brokers.dhan.domain import Exchange, InstrumentType, OptionType
from brokers.dhan.exceptions import InstrumentNotFoundError
from brokers.dhan.resolver import SymbolResolver


def test_resolve_equity(resolver):
    inst = resolver.resolve("RELIANCE", "NSE")
    assert inst.security_id == "2885"
    assert inst.exchange == Exchange.NSE
    assert inst.instrument_type == InstrumentType.EQUITY


def test_resolve_index(resolver):
    inst = resolver.resolve("NIFTY", "INDEX")
    assert inst.security_id == "13"
    assert inst.exchange == Exchange.INDEX


def test_resolve_unknown_raises(resolver):
    with pytest.raises(InstrumentNotFoundError):
        resolver.resolve("DOES_NOT_EXIST", "NSE")


def test_get_by_symbol_returns_none(resolver):
    result = resolver.get_by_symbol("DOES_NOT_EXIST", "NSE")
    assert result is None


def test_get_by_security_id(resolver):
    inst = resolver.get_by_security_id("2885")
    assert inst is not None
    assert inst.symbol == "RELIANCE"
    assert inst.exchange == Exchange.NSE


def test_get_futures_sorted(resolver):
    futures = resolver.get_futures("NIFTY", "NFO")
    assert len(futures) >= 1
    # Verify sorted by expiry (ascending)
    expiries = [f.expiry for f in futures if f.expiry]
    assert expiries == sorted(expiries)
    assert futures[0].instrument_type == InstrumentType.FUTURE


def test_get_futures_mcx(resolver):
    futures = resolver.get_futures("GOLD", "MCX")
    assert len(futures) == 2
    # Should be sorted: AUG before OCT
    assert futures[0].expiry < futures[1].expiry
    assert all(f.instrument_type == InstrumentType.FUTURE for f in futures)


def test_load_from_rows_atomic(sample_rows):
    r = SymbolResolver()
    r.load_from_rows(sample_rows)
    s = r.stats()
    assert s["loaded"] is True
    assert s["total"] == len(sample_rows)


def test_stripped_symbol_match(resolver):
    inst = resolver.resolve("NIFTY26JUN25000CE", "NFO")
    assert inst is not None
    assert inst.security_id == "55000"
    assert inst.instrument_type == InstrumentType.OPTION
    assert inst.option_type == OptionType.CALL


def test_exchange_normalization(resolver):
    inst = resolver.resolve("RELIANCE", "NSE_EQ")
    assert inst is not None
    assert inst.security_id == "2885"
    assert inst.exchange == Exchange.NSE
