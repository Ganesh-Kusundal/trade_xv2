"""Upstox <-> canonical InstrumentId bidirectional mapping — pure-function tests.

Mirrors test_dhan_instrument_mapping.py's matrix so both brokers get equal
coverage: equity, index, future (weekly + monthly), call/put option, multiple
exchanges, strike parsing, expired instruments, invalid/missing data.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from domain.enums import InstrumentType, OptionType
from domain.value_objects import InstrumentId
from plugins.brokers.upstox.instrument_adapter import (
    from_instrument_id,
    to_instrument_id,
    to_upstox_symbol,
)


# ---------------------------------------------------------------------------
# Broker -> Canonical
# ---------------------------------------------------------------------------


class TestToInstrumentId:
    def test_equity(self) -> None:
        iid = to_instrument_id(symbol="RELIANCE", exchange="NSE", instrument_type=InstrumentType.EQUITY)
        assert str(iid) == "NSE:RELIANCE"

    def test_index(self) -> None:
        iid = to_instrument_id(symbol="NIFTY", exchange="NSE", instrument_type=InstrumentType.INDEX)
        assert str(iid) == "NSE:NIFTY"

    def test_future_monthly_expiry(self) -> None:
        iid = to_instrument_id(
            symbol="NIFTY", exchange="NFO", instrument_type=InstrumentType.FUTURE,
            underlying="NIFTY", expiry=date(2026, 7, 30),
        )
        assert str(iid) == "NFO:NIFTY:20260730:FUT"

    def test_future_weekly_expiry(self) -> None:
        iid = to_instrument_id(
            symbol="NIFTY", exchange="NFO", instrument_type=InstrumentType.FUTURE,
            underlying="NIFTY", expiry=date(2026, 7, 24),
        )
        assert str(iid) == "NFO:NIFTY:20260724:FUT"

    def test_call_option(self) -> None:
        iid = to_instrument_id(
            symbol="NIFTY", exchange="NFO", instrument_type=InstrumentType.OPTION,
            underlying="NIFTY", expiry=date(2026, 7, 30), strike=Decimal("24000"), option_type=OptionType.CALL,
        )
        assert str(iid) == "NFO:NIFTY:20260730:24000:CE"

    def test_put_option(self) -> None:
        iid = to_instrument_id(
            symbol="BANKNIFTY", exchange="NFO", instrument_type=InstrumentType.OPTION,
            underlying="BANKNIFTY", expiry=date(2026, 8, 27), strike=Decimal("58000"), option_type=OptionType.PUT,
        )
        assert str(iid) == "NFO:BANKNIFTY:20260827:58000:PE"

    def test_fractional_strike(self) -> None:
        iid = to_instrument_id(
            symbol="X", exchange="NFO", instrument_type=InstrumentType.OPTION,
            underlying="BANKEX", expiry=date(2026, 8, 27), strike=Decimal("57500.5"), option_type=OptionType.CALL,
        )
        assert str(iid) == "NFO:BANKEX:20260827:57500.5:CE"

    def test_multiple_exchanges(self) -> None:
        nse = to_instrument_id(symbol="RELIANCE", exchange="NSE", instrument_type=InstrumentType.EQUITY)
        bse = to_instrument_id(symbol="RELIANCE", exchange="BSE", instrument_type=InstrumentType.EQUITY)
        assert nse != bse

    def test_expired_instrument_still_parses(self) -> None:
        iid = to_instrument_id(
            symbol="NIFTY", exchange="NFO", instrument_type=InstrumentType.FUTURE,
            underlying="NIFTY", expiry=date(2023, 7, 27),
        )
        assert str(iid) == "NFO:NIFTY:20230727:FUT"

    def test_underlying_falls_back_to_symbol(self) -> None:
        iid = to_instrument_id(symbol="RELIANCE", exchange="NSE", instrument_type=InstrumentType.EQUITY, underlying=None)
        assert iid.underlying == "RELIANCE"


# ---------------------------------------------------------------------------
# Canonical -> Broker
# ---------------------------------------------------------------------------


class TestToUpstoxSymbol:
    def test_equity_passthrough(self) -> None:
        assert to_upstox_symbol(InstrumentId.equity("NSE", "RELIANCE")) == "RELIANCE"

    def test_future(self) -> None:
        iid = InstrumentId.future("MCX", "CRUDEOIL", date(2026, 7, 20))
        assert to_upstox_symbol(iid) == "CRUDEOIL FUT 20 JUL 26"

    def test_put_option(self) -> None:
        iid = InstrumentId.option("MCX", "CRUDEOIL", date(2026, 7, 16), 7800, "PE")
        assert to_upstox_symbol(iid) == "CRUDEOIL 7800 PE 16 JUL 26"

    def test_call_option(self) -> None:
        iid = InstrumentId.option("NFO", "NIFTY", date(2026, 7, 30), 24000, "CE")
        assert to_upstox_symbol(iid) == "NIFTY 24000 CE 30 JUL 26"


class TestFromInstrumentId:
    def test_equity_params(self) -> None:
        params = from_instrument_id(InstrumentId.equity("NSE", "RELIANCE"))
        assert params == {"symbol": "RELIANCE", "exchange_segment": "NSE_EQ"}

    def test_option_params(self) -> None:
        iid = InstrumentId.option("NFO", "NIFTY", date(2026, 7, 30), 24000, "CE")
        params = from_instrument_id(iid)
        assert params["strike"] == 24000.0
        assert params["option_type"] == "CE"
        assert params["expiry"] == "2026-07-30"

    def test_future_params(self) -> None:
        iid = InstrumentId.future("MCX", "CRUDEOIL", date(2026, 7, 20))
        params = from_instrument_id(iid)
        assert params["exchange_segment"] == "MCX_FUT"
        assert params["instrument_type"] == "FUT"


def test_full_round_trip_option() -> None:
    canonical = to_instrument_id(
        symbol="NIFTY", exchange="NFO", instrument_type=InstrumentType.OPTION,
        underlying="NIFTY", expiry=date(2026, 7, 30), strike=Decimal("24000"), option_type=OptionType.CALL,
    )
    assert to_upstox_symbol(canonical) == "NIFTY 24000 CE 30 JUL 26"
