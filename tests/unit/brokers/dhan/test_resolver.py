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
    futures = resolver.get_futures("CRUDEOIL", "MCX")
    assert len(futures) == 2
    # Should be sorted: JUN before JUL
    assert futures[0].expiry < futures[1].expiry
    assert all(f.instrument_type == InstrumentType.FUTURE for f in futures)


def test_load_from_rows_atomic(sample_rows):
    r = SymbolResolver()
    r.load_from_rows(sample_rows)
    s = r.stats()
    assert s["loaded"] is True
    assert s["total"] == len(sample_rows)


def test_stripped_symbol_match(resolver):
    # The trading symbol is NIFTY-26Jun2026-25000-CE, stripped form should also match
    inst = resolver.get_by_symbol("NIFTY26JUN202625000CE", "NFO")
    assert inst is not None
    assert inst.security_id == "55000"
    assert inst.instrument_type == InstrumentType.OPTION
    assert inst.option_type == OptionType.CALL


def test_exchange_normalization(resolver):
    inst = resolver.resolve("RELIANCE", "NSE_EQ")
    assert inst is not None
    assert inst.security_id == "2885"
    assert inst.exchange == Exchange.NSE


def test_resolve_indices_additional():
    r = SymbolResolver()
    r.load_from_rows(
        [
            {
                "SEM_TRADING_SYMBOL": "NIFTY",
                "SEM_SMST_SECURITY_ID": "13",
                "SEM_EXM_EXCH_ID": "IDX_I",
                "SEM_INSTRUMENT_NAME": "INDEX",
                "SEM_LOT_UNITS": 1,
                "SEM_TICK_SIZE": 0.05,
            },
            {
                "SEM_TRADING_SYMBOL": "BANKNIFTY",
                "SEM_SMST_SECURITY_ID": "25",
                "SEM_EXM_EXCH_ID": "IDX_I",
                "SEM_INSTRUMENT_NAME": "INDEX",
                "SEM_LOT_UNITS": 1,
                "SEM_TICK_SIZE": 0.05,
            },
            {
                "SEM_TRADING_SYMBOL": "FINNIFTY",
                "SEM_SMST_SECURITY_ID": "27",
                "SEM_EXM_EXCH_ID": "IDX_I",
                "SEM_INSTRUMENT_NAME": "INDEX",
                "SEM_LOT_UNITS": 1,
                "SEM_TICK_SIZE": 0.05,
            },
        ]
    )

    for symbol, sec_id in [("NIFTY", "13"), ("BANKNIFTY", "25"), ("FINNIFTY", "27")]:
        inst = r.resolve(symbol, "IDX_I")
        assert inst.security_id == sec_id
        assert inst.exchange == Exchange.INDEX
        assert inst.instrument_type == InstrumentType.EQUITY

        # Test direct INDEX exchange normalization
        inst_idx = r.resolve(symbol, "INDEX")
        assert inst_idx.security_id == sec_id


def _equity_row(security_id: str, exch_instrument_type: str) -> dict:
    return {
        "SEM_TRADING_SYMBOL": "CHOLAFIN",
        "SEM_SMST_SECURITY_ID": security_id,
        "SEM_EXM_EXCH_ID": "NSE_EQ",
        "SEM_INSTRUMENT_NAME": "EQUITY",
        "SEM_LOT_UNITS": 1,
        "SEM_TICK_SIZE": 5.0,
        "SEM_EXCH_INSTRUMENT_TYPE": exch_instrument_type,
        "SEM_SERIES": "D1" if exch_instrument_type != "ES" else "EQ",
    }


@pytest.mark.parametrize("row_order", [("DEB", "ES"), ("ES", "DEB")])
def test_resolve_prefers_equity_share_over_bond_on_symbol_collision(row_order):
    """A stock and its issuer's bond/NCD can share the same trading symbol
    on Dhan (e.g. real-world CHOLAFIN: security_id=685 series=EQ type=ES vs
    security_id=19257 series=D1 type=DEB). Resolution must always prefer
    the equity share regardless of which row loads first."""
    stock_id, bond_id = "685", "19257"
    rows = [_equity_row(stock_id if t == "ES" else bond_id, t) for t in row_order]

    r = SymbolResolver()
    r.load_from_rows(rows)

    inst = r.resolve("CHOLAFIN", "NSE")
    assert inst.security_id == stock_id
    assert inst.is_equity_share is True
