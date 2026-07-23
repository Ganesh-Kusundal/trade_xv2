"""Cross-broker parity — Dhan and Upstox must converge on one canonical
InstrumentId for the same real-world contract, and each broker's own
Canonical -> native symbol must stay broker-correct.

This is the test that would have caught the pre-fix bug: Dhan's loader
produced "IDX:NIFTY" and Upstox's produced "NSE:<raw symbol>" for the same
index — two different InstrumentIds for one instrument.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from domain.enums import InstrumentType, OptionType
import plugins.brokers.dhan.instrument_adapter as dhan_map
import plugins.brokers.upstox.instrument_adapter as upstox_map


def test_equity_converges() -> None:
    dhan_iid = dhan_map.to_instrument_id(symbol="RELIANCE", exchange="NSE", instrument_type=InstrumentType.EQUITY)
    upstox_iid = upstox_map.to_instrument_id(symbol="RELIANCE-EQ".removesuffix("-EQ"), exchange="NSE", instrument_type=InstrumentType.EQUITY)
    assert dhan_iid == upstox_iid


def test_index_converges() -> None:
    """The bug this test guards against: Dhan defaulted to exchange IDX,
    Upstox defaulted to exchange NSE, for the identical index."""
    dhan_iid = dhan_map.to_instrument_id(symbol="NIFTY", exchange="NSE", instrument_type=InstrumentType.INDEX)
    upstox_iid = upstox_map.to_instrument_id(symbol="NIFTY", exchange="NSE", instrument_type=InstrumentType.INDEX)
    assert dhan_iid == upstox_iid
    assert str(dhan_iid) == "NSE:NIFTY"


def test_future_converges_despite_different_native_symbol_shapes() -> None:
    # Dhan's native symbol: "NIFTY24JULFUT". Upstox's: "NIFTY" + segment NSE_FO.
    # Both must canonicalize to the same InstrumentId given the same real fields.
    dhan_iid = dhan_map.to_instrument_id(
        symbol="NIFTY24JULFUT", exchange="NFO", instrument_type=InstrumentType.FUTURE,
        underlying="NIFTY", expiry=date(2026, 7, 30),
    )
    upstox_iid = upstox_map.to_instrument_id(
        symbol="NIFTY", exchange="NFO", instrument_type=InstrumentType.FUTURE,
        underlying="NIFTY", expiry=date(2026, 7, 30),
    )
    assert dhan_iid == upstox_iid


def test_option_converges() -> None:
    dhan_iid = dhan_map.to_instrument_id(
        symbol="NIFTY24JUL24000CE", exchange="NFO", instrument_type=InstrumentType.OPTION,
        underlying="NIFTY", expiry=date(2026, 7, 30), strike=Decimal("24000"), option_type=OptionType.CALL,
    )
    upstox_iid = upstox_map.to_instrument_id(
        symbol="NIFTY", exchange="NFO", instrument_type=InstrumentType.OPTION,
        underlying="NIFTY", expiry=date(2026, 7, 30), strike=Decimal("24000"), option_type=OptionType.CALL,
    )
    assert dhan_iid == upstox_iid


def test_same_canonical_id_produces_broker_correct_native_symbols() -> None:
    """One canonical id in, each broker's own native shape out."""
    from domain.value_objects import InstrumentId

    iid = InstrumentId.future("MCX", "CRUDEOIL", date(2026, 7, 20))
    assert dhan_map.to_dhan_symbol(iid) == "CRUDEOIL-20Jul2026-FUT"
    assert upstox_map.to_upstox_symbol(iid) == "CRUDEOIL FUT 20 JUL 26"
    # Different native strings, same underlying contract.
    assert dhan_map.to_dhan_symbol(iid) != upstox_map.to_upstox_symbol(iid)
