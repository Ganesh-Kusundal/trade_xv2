"""Dhan adapter test — proves BrokerGateway becomes a domain DataProvider plugin.

The broker import is deferred to inside the test so the no-broker assertion in
``test_platform_api.py`` stays valid.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pandas as pd

from domain.entities.market import MarketDepth, Quote
from domain.entities.options import FutureChain, OptionChain
from domain.instruments.instrument_id import InstrumentId
from domain.ports.protocols import DataProvider


class StubDhanGateway:
    """Minimal stand-in for brokers.dhan.gateway.BrokerGateway."""

    def quote(self, symbol, exchange="NSE"):
        return Quote(
            symbol=symbol,
            ltp=Decimal("100"),
            open=Decimal("99"),
            high=Decimal("101"),
            low=Decimal("98"),
            close=Decimal("99"),
            volume=500,
            change=Decimal("1"),
            bid=Decimal("99.9"),
            ask=Decimal("100.1"),
            timestamp=datetime.now(tz=timezone.utc),
        )

    def history(self, symbol, exchange="NSE", timeframe="1D", lookback_days=90, from_date=None, to_date=None):
        return pd.DataFrame({"close": [Decimal("100")]})

    def depth(self, symbol, exchange="NSE"):
        return MarketDepth(symbol=symbol, depth_type="DEPTH_5")

    def option_chain(self, underlying, exchange="NFO", expiry=None):
        return OptionChain(underlying=underlying, exchange=exchange, expiry=expiry or "2026-07-30", strikes=(), spot=Decimal("100"))

    def future_chain(self, underlying, exchange="NFO"):
        return FutureChain(underlying=underlying, exchange=exchange)


def test_adapter_implements_data_provider_port():
    from brokers.dhan.adapter import DhanDataAdapter

    adapter = DhanDataAdapter(StubDhanGateway())
    assert isinstance(adapter, DataProvider)
    assert adapter.name == "dhan-adapter"


def test_adapter_normalizes_quote_to_domain_snapshot():
    from brokers.dhan.adapter import DhanDataAdapter

    adapter = DhanDataAdapter(StubDhanGateway())
    iid = InstrumentId.equity("NSE", "RELIANCE")
    snap = adapter.get_quote(iid)

    assert snap.ltp == Decimal("100")
    assert snap.bid == Decimal("99.9")
    assert snap.ask == Decimal("100.1")
    assert snap.instrument.symbol == "RELIANCE"
    assert snap.instrument.exchange == "NSE"
    assert snap.provenance.source.broker_id == "dhan"


def test_adapter_delegates_history_depth_chain():
    from brokers.dhan.adapter import DhanDataAdapter

    adapter = DhanDataAdapter(StubDhanGateway())
    iid = InstrumentId.index("NFO", "NIFTY")

    assert not adapter.get_history(iid).empty
    assert adapter.get_depth(iid).symbol == "NIFTY"
    chain = adapter.get_option_chain(iid)
    assert chain.underlying == "NIFTY"
    assert isinstance(adapter.get_future_chain(iid), FutureChain)
