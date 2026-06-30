"""Tests for broker instrument adapters — InstrumentId translation."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from brokers.common.instrument_adapter import from_instrument_id as common_from_iid
from brokers.common.instrument_adapter import to_instrument_id as common_to_iid
from brokers.common.instruments import Instrument
from domain import InstrumentType
from domain.entities.instrument import Instrument as DomainInstrument
from domain.instrument_id import InstrumentId


def _create_instrument(
    symbol: str,
    exchange: str,
    asset_class: InstrumentType = InstrumentType.EQUITY,
    *,
    expiry: str | None = None,
    strike: Decimal | None = None,
    option_type: str | None = None,
) -> Instrument:
    """Helper to create a trading engine Instrument from old-style fields."""
    domain_inst = DomainInstrument(
        symbol=symbol,
        exchange=exchange,
        security_id="",
        instrument_type=asset_class.value if hasattr(asset_class, 'value') else str(asset_class),
        lot_size=0,
        tick_size=Decimal("0"),
        option_type=option_type,
        strike_price=strike,
        expiry=expiry,
    )
    return Instrument(
        domain_instrument=domain_inst,
        asset_class=asset_class,
    )


class TestCommonAdapter:
    """Test common broker adapter."""

    def test_equity_to_instrument_id(self):
        inst = _create_instrument("RELIANCE", "NSE", InstrumentType.EQUITY)
        iid = common_to_iid(inst)
        assert iid == InstrumentId.equity("NSE", "RELIANCE")
        assert iid.asset_type == "EQUITY"

    def test_option_to_instrument_id(self):
        inst = _create_instrument(
            "NIFTY", "NFO", InstrumentType.OPTIONS,
            expiry="2026-07-30", strike=Decimal("25000"),
            option_type="CE",
        )
        iid = common_to_iid(inst)
        assert iid == InstrumentId.option("NFO", "NIFTY", date(2026, 7, 30), 25000, "CE")

    def test_future_to_instrument_id(self):
        inst = _create_instrument(
            "NIFTY", "NFO", InstrumentType.FUTURES,
            expiry="2026-07-30",
        )
        iid = common_to_iid(inst)
        assert iid == InstrumentId.future("NFO", "NIFTY", date(2026, 7, 30))

    def test_roundtrip(self):
        original = InstrumentId.option("NFO", "NIFTY", date(2026, 7, 30), 25000, "CE")
        inst = common_from_iid(original)
        result = common_to_iid(inst)
        assert result == original


class TestDhanAdapter:
    """Test Dhan broker adapter."""

    def test_equity(self):
        from brokers.dhan.instrument_adapter import to_instrument_id
        iid = to_instrument_id(symbol="RELIANCE", exchange="NSE")
        assert iid == InstrumentId.equity("NSE", "RELIANCE")

    def test_option(self):
        from brokers.dhan.instrument_adapter import to_instrument_id
        iid = to_instrument_id(
            symbol="NIFTY-26Jun2026-25000-CE",
            exchange="NFO",
            option_type="CE",
            strike_price=Decimal("25000"),
            expiry="26Jun2026",
            underlying="NIFTY",
        )
        assert iid == InstrumentId.option("NFO", "NIFTY", date(2026, 6, 26), 25000, "CE")

    def test_future(self):
        from brokers.dhan.instrument_adapter import to_instrument_id
        iid = to_instrument_id(
            symbol="NIFTY-26Jun2026-FUT",
            exchange="NFO",
            instrument_type="FUTIDX",
            expiry="26Jun2026",
            underlying="NIFTY",
        )
        assert iid == InstrumentId.future("NFO", "NIFTY", date(2026, 6, 26))

    def test_from_instrument_id(self):
        from brokers.dhan.instrument_adapter import from_instrument_id
        iid = InstrumentId.option("NFO", "NIFTY", date(2026, 7, 30), 25000, "CE")
        params = from_instrument_id(iid)
        assert params["symbol"] == "NIFTY"
        assert params["exchange"] == "NFO"
        assert params["right"] == "CE"


class TestUpstoxAdapter:
    """Test Upstox broker adapter."""

    def test_equity(self):
        from brokers.upstox.instrument_adapter import to_instrument_id
        iid = to_instrument_id(symbol="RELIANCE", exchange="NSE")
        assert iid == InstrumentId.equity("NSE", "RELIANCE")

    def test_option(self):
        from brokers.upstox.instrument_adapter import to_instrument_id
        iid = to_instrument_id(
            symbol="NIFTY22MAY2524000CE",
            exchange_segment="NSE_FO",
            option_type="CE",
            strike=24000.0,
            expiry="2025-05-22",
            underlying_symbol="NIFTY",
        )
        assert iid == InstrumentId.option("NFO", "NIFTY", date(2025, 5, 22), 24000, "CE")

    def test_from_instrument_id(self):
        from brokers.upstox.instrument_adapter import from_instrument_id
        iid = InstrumentId.option("NFO", "NIFTY", date(2026, 7, 30), 25000, "CE")
        params = from_instrument_id(iid)
        assert params["symbol"] == "NIFTY"
        assert params["exchange_segment"] == "NSE_FO"
        assert params["option_type"] == "CE"
