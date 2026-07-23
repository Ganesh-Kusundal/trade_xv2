"""Dhan <-> canonical InstrumentId bidirectional mapping — pure-function tests.

Covers the full instrument-type matrix requested for mapping validation:
equity, index, future (weekly + monthly expiry), call option, put option,
multiple exchanges, strike parsing, expired instruments, invalid/missing data.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from domain.enums import InstrumentType, OptionType
from plugins.brokers.dhan.instrument_adapter import (
    from_instrument_id,
    to_dhan_symbol,
    to_instrument_id,
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
            symbol="NIFTY24JULFUT",
            exchange="NFO",
            instrument_type=InstrumentType.FUTURE,
            underlying="NIFTY",
            expiry=date(2026, 7, 30),
        )
        assert str(iid) == "NFO:NIFTY:20260730:FUT"

    def test_future_weekly_expiry(self) -> None:
        iid = to_instrument_id(
            symbol="NIFTY24JULFUT",
            exchange="NFO",
            instrument_type=InstrumentType.FUTURE,
            underlying="NIFTY",
            expiry=date(2026, 7, 24),
        )
        assert str(iid) == "NFO:NIFTY:20260724:FUT"
        # Distinct from the monthly contract for the same underlying
        monthly = to_instrument_id(
            symbol="NIFTY24JULFUT", exchange="NFO", instrument_type=InstrumentType.FUTURE,
            underlying="NIFTY", expiry=date(2026, 7, 30),
        )
        assert iid != monthly

    def test_call_option(self) -> None:
        iid = to_instrument_id(
            symbol="NIFTY24JUL24000CE",
            exchange="NFO",
            instrument_type=InstrumentType.OPTION,
            underlying="NIFTY",
            expiry=date(2026, 7, 30),
            strike=Decimal("24000"),
            option_type=OptionType.CALL,
        )
        assert str(iid) == "NFO:NIFTY:20260730:24000:CE"
        assert iid.is_call

    def test_put_option(self) -> None:
        iid = to_instrument_id(
            symbol="NIFTY24JUL24000PE",
            exchange="NFO",
            instrument_type=InstrumentType.OPTION,
            underlying="NIFTY",
            expiry=date(2026, 7, 30),
            strike=Decimal("24000"),
            option_type=OptionType.PUT,
        )
        assert str(iid) == "NFO:NIFTY:20260730:24000:PE"
        assert iid.is_put

    def test_fractional_strike(self) -> None:
        iid = to_instrument_id(
            symbol="X", exchange="NFO", instrument_type=InstrumentType.OPTION,
            underlying="BANKEX", expiry=date(2026, 8, 27), strike=Decimal("57500.5"),
            option_type=OptionType.CALL,
        )
        assert iid.strike == Decimal("57500.5")
        assert str(iid) == "NFO:BANKEX:20260827:57500.5:CE"

    def test_multiple_exchanges(self) -> None:
        nse = to_instrument_id(symbol="RELIANCE", exchange="NSE", instrument_type=InstrumentType.EQUITY)
        bse = to_instrument_id(symbol="RELIANCE", exchange="BSE", instrument_type=InstrumentType.EQUITY)
        bfo = to_instrument_id(
            symbol="SENSEX26AUG80000CE", exchange="BFO", instrument_type=InstrumentType.OPTION,
            underlying="SENSEX", expiry=date(2026, 8, 27), strike=Decimal("80000"), option_type=OptionType.CALL,
        )
        assert nse != bse
        assert nse.exchange == "NSE"
        assert bse.exchange == "BSE"
        assert bfo.exchange == "BFO"

    def test_expired_instrument_still_parses(self) -> None:
        """A past-expiry contract must still produce a valid, well-formed id — not error."""
        iid = to_instrument_id(
            symbol="NIFTY23JULFUT", exchange="NFO", instrument_type=InstrumentType.FUTURE,
            underlying="NIFTY", expiry=date(2023, 7, 27),
        )
        assert str(iid) == "NFO:NIFTY:20230727:FUT"

    def test_underlying_falls_back_to_symbol_when_missing(self) -> None:
        """No SM_SYMBOL_NAME available — degrade to the raw symbol, not an error."""
        iid = to_instrument_id(symbol="RELIANCE", exchange="NSE", instrument_type=InstrumentType.EQUITY, underlying=None)
        assert iid.underlying == "RELIANCE"

    def test_option_missing_strike_falls_back_to_equity_shape(self) -> None:
        """Option row with incomplete data (no strike) shouldn't crash — degrades safely."""
        iid = to_instrument_id(
            symbol="BROKEN", exchange="NFO", instrument_type=InstrumentType.OPTION,
            underlying="BROKEN", expiry=date(2026, 7, 30), strike=None, option_type=OptionType.CALL,
        )
        assert iid.right is None  # not a valid option shape, degraded to bare underlying


# ---------------------------------------------------------------------------
# Canonical -> Broker
# ---------------------------------------------------------------------------


class TestToDhanSymbol:
    def test_equity_passthrough(self) -> None:
        from domain.value_objects import InstrumentId

        assert to_dhan_symbol(InstrumentId.equity("NSE", "RELIANCE")) == "RELIANCE"

    def test_future(self) -> None:
        from domain.value_objects import InstrumentId

        iid = InstrumentId.future("MCX", "CRUDEOIL", date(2026, 7, 20))
        assert to_dhan_symbol(iid) == "CRUDEOIL-20Jul2026-FUT"

    def test_call_option(self) -> None:
        from domain.value_objects import InstrumentId

        iid = InstrumentId.option("MCX", "CRUDEOIL", date(2026, 7, 16), 7650, "CE")
        assert to_dhan_symbol(iid) == "CRUDEOIL-16Jul2026-7650-CE"

    def test_put_option(self) -> None:
        from domain.value_objects import InstrumentId

        iid = InstrumentId.option("NFO", "NIFTY", date(2026, 7, 30), 24000, "PE")
        assert to_dhan_symbol(iid) == "NIFTY-30Jul2026-24000-PE"


class TestFromInstrumentId:
    def test_equity_params(self) -> None:
        from domain.value_objects import InstrumentId

        params = from_instrument_id(InstrumentId.equity("NSE", "RELIANCE"))
        assert params == {"symbol": "RELIANCE", "exchange": "NSE"}

    def test_option_params(self) -> None:
        from domain.value_objects import InstrumentId

        iid = InstrumentId.option("NFO", "NIFTY", date(2026, 7, 30), 24000, "CE")
        params = from_instrument_id(iid)
        assert params["strike_price"] == "24000"
        assert params["right"] == "CE"
        assert params["expiry"] == "30Jul2026"

    def test_future_params(self) -> None:
        from domain.value_objects import InstrumentId

        iid = InstrumentId.future("NFO", "NIFTY", date(2026, 7, 30))
        params = from_instrument_id(iid)
        assert params["instrument_type"] == "FUT"


# ---------------------------------------------------------------------------
# Full round-trip: Broker row -> Canonical -> Dhan symbol
# ---------------------------------------------------------------------------


def test_full_round_trip_option() -> None:
    canonical = to_instrument_id(
        symbol="NIFTY24JUL24000CE", exchange="NFO", instrument_type=InstrumentType.OPTION,
        underlying="NIFTY", expiry=date(2026, 7, 30), strike=Decimal("24000"), option_type=OptionType.CALL,
    )
    assert to_dhan_symbol(canonical) == "NIFTY-30Jul2026-24000-CE"
