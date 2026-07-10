"""Tests for new Instrument hierarchy — pure domain objects."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from domain.candles.historical import InstrumentRef
from domain.entities.market import MarketDepth, QuoteSnapshot
from domain.instruments.instrument import (
    Equity,
    Future,
    Index,
    Instrument,
    Option,
)
from domain.instruments.instrument_id import InstrumentId
from domain.provenance import DataProvenance, ProvenanceConfidence, SourceIdentity
from domain.value_objects.state import InstrumentState


@pytest.fixture(autouse=True)
def _clear_provider_ambient():
    from domain.ports.provider_registry import set_default_provider
    from domain.ports.session_context import set_ambient_session

    set_default_provider(None)
    set_ambient_session(None)
    yield
    set_default_provider(None)
    set_ambient_session(None)


def _make_quote(
    symbol="RELIANCE", exchange="NSE", ltp=Decimal("2450"), bid=Decimal("2449"), ask=Decimal("2451")
):
    return QuoteSnapshot(
        instrument=InstrumentRef(symbol=symbol, exchange=exchange),
        ltp=ltp,
        event_time=datetime.now(),
        provenance=DataProvenance(
            source=SourceIdentity(broker_id="mock"),
            fetched_at=datetime.now(),
            request_id="test",
            confidence=ProvenanceConfidence.AUTHORITATIVE,
        ),
        bid=bid,
        ask=ask,
        high=Decimal("2500"),
        low=Decimal("2400"),
        open=Decimal("2420"),
        close=Decimal("2480"),
        volume=1000000,
    )


# ══════════════════════════════════════════════════════════════════════
# Instrument Identity
# ══════════════════════════════════════════════════════════════════════


class TestInstrumentIdentity:
    def test_equity_symbol(self):
        assert Equity("RELIANCE").symbol == "RELIANCE"

    def test_equity_exchange(self):
        assert Equity("RELIANCE").exchange == "NSE"

    def test_equity_asset_type(self):
        assert Equity("RELIANCE").asset_type == "EQUITY"

    def test_index_symbol(self):
        assert Index("NIFTY").symbol == "NIFTY"

    def test_index_exchange(self):
        assert Index("NIFTY").exchange == "NSE"

    def test_index_asset_type(self):
        assert Index("NIFTY").asset_type == "INDEX"

    def test_instrument_id_property(self):
        stock = Equity("RELIANCE")
        assert isinstance(stock.id, InstrumentId)
        assert stock.id.underlying == "RELIANCE"

    def test_equality(self):
        assert Equity("RELIANCE") == Equity("RELIANCE")

    def test_inequality(self):
        assert Equity("RELIANCE") != Equity("TCS")

    def test_hash(self):
        assert hash(Equity("RELIANCE")) == hash(Equity("RELIANCE"))

    def test_repr(self):
        assert "RELIANCE" in repr(Equity("RELIANCE"))


# ══════════════════════════════════════════════════════════════════════
# Instrument State (no provider)
# ══════════════════════════════════════════════════════════════════════


class TestInstrumentStateNoProvider:
    def test_quote_is_none(self):
        assert Equity("RELIANCE").quote is None

    def test_ltp_is_none(self):
        assert Equity("RELIANCE").ltp is None

    def test_bid_is_none(self):
        assert Equity("RELIANCE").bid is None

    def test_ask_is_none(self):
        assert Equity("RELIANCE").ask is None

    def test_volume_is_zero(self):
        assert Equity("RELIANCE").volume == 0

    def test_market_depth_is_none(self):
        assert Equity("RELIANCE").market_depth is None

    def test_is_live_is_false(self):
        assert Equity("RELIANCE").is_live is False

    def test_refresh_raises_without_provider(self):
        from domain.errors import NotConfiguredError
        from domain.ports.provider_registry import set_default_provider

        set_default_provider(None)
        with pytest.raises(NotConfiguredError):
            Equity("RELIANCE").refresh()

    def test_history_raises_without_provider(self):
        from domain.errors import NotConfiguredError
        from domain.ports.provider_registry import set_default_provider

        set_default_provider(None)
        with pytest.raises(NotConfiguredError):
            Equity("RELIANCE").history()

    def test_spread_is_none(self):
        assert Equity("RELIANCE").spread() is None

    def test_mid_price_is_none(self):
        assert Equity("RELIANCE").mid_price() is None


# ══════════════════════════════════════════════════════════════════════
# Instrument State (with mock provider)
# ══════════════════════════════════════════════════════════════════════


class TestInstrumentStateWithProvider:
    def _make_provider(self, quote=None):
        from domain.ports.protocols import DataProvider

        class MockProvider(DataProvider):
            @property
            def name(self):
                return "mock"

            def get_quote(self, instrument_id):
                return quote

            def get_history(self, instrument_id, **kwargs):
                import pandas as pd

                return pd.DataFrame()

            def get_depth(self, instrument_id):
                return None

            def get_option_chain(self, underlying, **kwargs):
                from domain.entities.options import OptionChain

                return OptionChain(underlying="", exchange="", expiry="")

            def get_future_chain(self, underlying):
                from domain.entities.options import FutureChain

                return FutureChain(underlying="", exchange="")

            def subscribe(self, instrument_id, callback, **kwargs):
                return MagicMock()

            def unsubscribe(self, handle):
                pass

        return MockProvider()

    def test_quote_from_provider(self):
        q = _make_quote(ltp=Decimal("2450"), bid=Decimal("2449"), ask=Decimal("2451"))
        stock = Equity("RELIANCE", data_provider=self._make_provider(q))
        stock.refresh()  # Must call refresh to populate state
        assert stock.quote is not None
        assert stock.ltp == Decimal("2450")
        assert stock.bid == Decimal("2449")
        assert stock.ask == Decimal("2451")
        assert stock.volume == 1000000

    def test_refresh_updates_state(self):
        q = _make_quote(ltp=Decimal("2500"))
        stock = Equity("RELIANCE", data_provider=self._make_provider(q))
        result = stock.refresh()
        assert result is not None
        assert stock.ltp == Decimal("2500")

    def test_spread_computed(self):
        q = _make_quote(bid=Decimal("2449"), ask=Decimal("2451"))
        stock = Equity("RELIANCE", data_provider=self._make_provider(q))
        stock.refresh()
        assert stock.spread() == Decimal("2")

    def test_mid_price_computed(self):
        q = _make_quote(bid=Decimal("2448"), ask=Decimal("2452"))
        stock = Equity("RELIANCE", data_provider=self._make_provider(q))
        stock.refresh()
        assert stock.mid_price() == Decimal("2450")


# ══════════════════════════════════════════════════════════════════════
# Future
# ══════════════════════════════════════════════════════════════════════


class TestFuture:
    def test_expiry_property(self):
        from datetime import date

        f = Future("NIFTY", expiry=date(2026, 7, 31))
        assert f.expiry == date(2026, 7, 31)

    def test_asset_type(self):
        from datetime import date

        assert Future("NIFTY", expiry=date(2026, 7, 31)).asset_type == "FUTURES"


# ══════════════════════════════════════════════════════════════════════
# Option
# ══════════════════════════════════════════════════════════════════════


class TestOption:
    def test_strike_property(self):
        from datetime import date

        iid = InstrumentId.option("NFO", "NIFTY", date(2026, 7, 31), Decimal("25000"), "CE")
        opt = Option(iid, strike=Decimal("25000"), expiry=date(2026, 7, 31), right="CE")
        assert opt.strike == Decimal("25000")

    def test_right_property(self):
        from datetime import date

        iid = InstrumentId.option("NFO", "NIFTY", date(2026, 7, 31), Decimal("25000"), "CE")
        opt = Option(iid, strike=Decimal("25000"), expiry=date(2026, 7, 31), right="CE")
        assert opt.right == "CE"

    def test_is_call(self):
        from datetime import date

        iid = InstrumentId.option("NFO", "NIFTY", date(2026, 7, 31), Decimal("25000"), "CE")
        opt = Option(iid, strike=Decimal("25000"), expiry=date(2026, 7, 31), right="CE")
        assert opt.is_call is True

    def test_is_put(self):
        from datetime import date

        iid = InstrumentId.option("NFO", "NIFTY", date(2026, 7, 31), Decimal("25000"), "PE")
        opt = Option(iid, strike=Decimal("25000"), expiry=date(2026, 7, 31), right="PE")
        assert opt.is_call is False

    def test_greeks_zero_when_no_leg(self):
        from datetime import date

        iid = InstrumentId.option("NFO", "NIFTY", date(2026, 7, 31), Decimal("25000"), "CE")
        opt = Option(iid, strike=Decimal("25000"), expiry=date(2026, 7, 31), right="CE")
        assert opt.greeks.delta == Decimal("0")

    def test_greeks_from_leg(self):
        from datetime import date

        iid = InstrumentId.option("NFO", "NIFTY", date(2026, 7, 31), Decimal("25000"), "CE")
        mock_leg = MagicMock()
        mock_leg.greeks = {
            "delta": "0.5",
            "gamma": "0.02",
            "theta": "-0.1",
            "vega": "0.3",
            "rho": "0.01",
        }
        opt = Option(
            iid, strike=Decimal("25000"), expiry=date(2026, 7, 31), right="CE", leg=mock_leg
        )
        assert opt.greeks.delta == Decimal("0.5")

    def test_from_leg_classmethod(self):
        from datetime import date

        mock_leg = MagicMock()
        mock_leg.greeks = {"delta": "0.5"}
        opt = Option.from_leg("NIFTY", "NFO", date(2026, 7, 31), Decimal("25000"), "CE", mock_leg)
        assert opt.strike == Decimal("25000")
        assert opt.right == "CE"
        assert opt.is_call is True


# ══════════════════════════════════════════════════════════════════════
# Serialization
# ══════════════════════════════════════════════════════════════════════


class TestSerialization:
    def test_serialize_equity(self):
        data = Equity("RELIANCE").serialize()
        assert data["symbol"] == "RELIANCE"
        assert data["exchange"] == "NSE"
        assert data["asset_type"] == "EQUITY"

    def test_clone(self):
        stock = Equity("RELIANCE", metadata={"lot_size": 10})
        clone = stock.clone()
        assert clone.symbol == "RELIANCE"
        assert clone is not stock
        assert clone.lot_size == 10


# ══════════════════════════════════════════════════════════════════════
# Callbacks
# ══════════════════════════════════════════════════════════════════════


class TestCallbacks:
    def test_on_tick_registers(self):
        stock = Equity("RELIANCE")
        cb = MagicMock()
        stock.on_tick(cb)
        assert cb in stock._callbacks["tick"]

    def test_on_quote_registers(self):
        stock = Equity("RELIANCE")
        cb = MagicMock()
        stock.on_quote(cb)
        assert cb in stock._callbacks["quote"]

    def test_on_depth_registers(self):
        stock = Equity("RELIANCE")
        cb = MagicMock()
        stock.on_depth(cb)
        assert cb in stock._callbacks["depth"]

    def test_on_disconnect_registers(self):
        stock = Equity("RELIANCE")
        cb = MagicMock()
        stock.on_disconnect(cb)
        assert cb in stock._callbacks["disconnect"]

    def test_on_reconnect_registers(self):
        stock = Equity("RELIANCE")
        cb = MagicMock()
        stock.on_reconnect(cb)
        assert cb in stock._callbacks["reconnect"]
