"""Tests for UpstoxDataAdapter — broker-to-domain DataProvider adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pandas as pd
import pytest

from brokers.upstox.adapter import UpstoxDataAdapter
from brokers.common import DepthLevel, MarketDepth, Quote
from domain.entities.options import FutureChain, OptionChain
from domain.instruments.instrument_id import InstrumentId
from domain.ports.protocols import DataProvider


class StubUpstoxGateway:
    """Minimal gateway stub implementing only the methods the adapter calls."""

    def ltp(self, symbol: str, exchange: str) -> Decimal:
        return Decimal("2500.00")

    def quote(self, symbol: str, exchange: str) -> Quote:
        return Quote(
            symbol=symbol,
            ltp=Decimal("2500.00"),
            open=Decimal("2480.00"),
            high=Decimal("2520.00"),
            low=Decimal("2470.00"),
            close=Decimal("2490.00"),
            volume=1_200_000,
            change=Decimal("10.00"),
            bid=Decimal("2499.50"),
            ask=Decimal("2500.50"),
            timestamp=datetime(2026, 7, 8, 10, 30, tzinfo=timezone.utc),
        )

    def depth(self, symbol: str, exchange: str) -> MarketDepth:
        return MarketDepth(
            symbol=symbol,
            bids=[
                DepthLevel(price=Decimal("2499.50"), quantity=100, orders=5),
                DepthLevel(price=Decimal("2499.00"), quantity=200, orders=8),
            ],
            asks=[
                DepthLevel(price=Decimal("2500.50"), quantity=150, orders=7),
                DepthLevel(price=Decimal("2501.00"), quantity=250, orders=10),
            ],
            timestamp=datetime(2026, 7, 8, 10, 30, tzinfo=timezone.utc),
            depth_type="DEPTH_5",
        )

    def history(
        self,
        symbol: str,
        exchange: str,
        timeframe: str = "1D",
        lookback_days: int = 120,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> pd.DataFrame:
        dates = pd.date_range("2026-01-01", periods=5, freq="B")
        return pd.DataFrame(
            {
                "timestamp": dates,
                "open": [2400.0] * 5,
                "high": [2500.0] * 5,
                "low": [2380.0] * 5,
                "close": [2480.0] * 5,
                "volume": [1_000_000] * 5,
            }
        )

    def option_chain(
        self,
        underlying: str,
        exchange: str = "NFO",
        expiry: str | None = None,
    ) -> OptionChain:
        return OptionChain(
            underlying=underlying,
            exchange=exchange,
            expiry=expiry or "2026-07-30",
        )

    def future_chain(
        self,
        underlying: str,
        exchange: str = "NFO",
    ) -> FutureChain:
        return FutureChain.from_dict(
            {
                "underlying": underlying,
                "exchange": exchange,
                "expiries": ["2026-07-30"],
                "contracts": [
                    {
                        "expiry": "2026-07-30",
                        "symbol": f"{underlying}26JULFUT",
                        "lot_size": 1,
                        "underlying": underlying,
                    }
                ],
            }
        )

    def stream_depth(self, symbol: str, exchange: str, on_depth=None):
        if on_depth is not None:
            md = self.depth(symbol, exchange)
            on_depth(md)
        return None


@pytest.fixture
def gateway() -> StubUpstoxGateway:
    return StubUpstoxGateway()


@pytest.fixture
def adapter(gateway: StubUpstoxGateway) -> UpstoxDataAdapter:
    return UpstoxDataAdapter(gateway)


def _instrument(exchange: str = "NSE", symbol: str = "RELIANCE") -> InstrumentId:
    return InstrumentId(exchange=exchange, underlying=symbol)


def test_adapter_implements_data_provider(adapter: UpstoxDataAdapter) -> None:
    assert isinstance(adapter, DataProvider)


def test_adapter_name(adapter: UpstoxDataAdapter) -> None:
    assert adapter.name == "upstox-adapter"


def test_adapter_custom_broker_id() -> None:
    a = UpstoxDataAdapter(StubUpstoxGateway(), broker_id="my-broker")
    assert a.name == "my-broker-adapter"


def test_adapter_normalizes_quote(adapter: UpstoxDataAdapter) -> None:
    snap = adapter.get_quote(_instrument())
    assert snap is not None
    assert snap.ltp == Decimal("2500.00")
    assert snap.bid == Decimal("2499.50")
    assert snap.ask == Decimal("2500.50")
    assert snap.open == Decimal("2480.00")
    assert snap.high == Decimal("2520.00")
    assert snap.low == Decimal("2470.00")
    assert snap.volume == 1_200_000
    assert snap.provenance.source.broker_id == "upstox"
    assert snap.instrument.symbol == "RELIANCE"
    assert snap.instrument.exchange == "NSE"


def test_adapter_returns_none_for_missing_quote() -> None:
    class NullGateway:
        def quote(self, symbol, exchange):
            return None

    a = UpstoxDataAdapter(NullGateway())
    assert a.get_quote(_instrument()) is None


def test_adapter_delegates_history(adapter: UpstoxDataAdapter) -> None:
    df = adapter.get_history(_instrument())
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 5
    assert list(df.columns[:6]) == [
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]


def test_adapter_delegates_depth(adapter: UpstoxDataAdapter) -> None:
    md = adapter.get_depth(_instrument())
    assert isinstance(md, MarketDepth)
    assert len(md.bids) == 2
    assert len(md.asks) == 2
    assert md.bids[0].price == Decimal("2499.50")
    assert md.asks[0].price == Decimal("2500.50")


def test_adapter_delegates_option_chain(adapter: UpstoxDataAdapter) -> None:
    chain = adapter.get_option_chain(_instrument("NFO", "NIFTY"))
    assert isinstance(chain, OptionChain)
    assert chain.underlying == "NIFTY"
    assert chain.exchange == "NFO"


def test_adapter_delegates_future_chain(adapter: UpstoxDataAdapter) -> None:
    chain = adapter.get_future_chain(_instrument("NFO", "NIFTY"))
    assert isinstance(chain, FutureChain)
    assert chain.underlying == "NIFTY"
    assert len(chain.contracts) == 1


def test_adapter_history_batch(adapter: UpstoxDataAdapter) -> None:
    ids = [_instrument("NSE", "RELIANCE"), _instrument("NSE", "INFY")]
    df = adapter.history_batch(ids, timeframe="1D", lookback_days=10)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 10  # 5 rows per instrument


def test_adapter_history_batch_empty() -> None:
    a = UpstoxDataAdapter(StubUpstoxGateway())
    df = a.history_batch([])
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 0


def test_adapter_subscribe_delivers_snapshot(adapter: UpstoxDataAdapter) -> None:
    delivered: list = []

    def cb(iid, snap):
        delivered.append(snap)

    sub = adapter.subscribe(_instrument(), cb)
    assert sub.is_active
    assert len(delivered) == 1
    assert delivered[0].ltp == Decimal("2500.00")


def test_adapter_unsubscribe(adapter: UpstoxDataAdapter) -> None:
    sub = adapter.subscribe(_instrument(), lambda iid, s: None)
    assert sub.is_active
    adapter.unsubscribe(sub)
    assert not sub.is_active


def test_adapter_subscribe_depth(adapter: UpstoxDataAdapter) -> None:
    delivered: list = []

    def cb(iid, snap):
        delivered.append(snap)

    sub = adapter.subscribe(_instrument(), cb, depth=True)
    assert sub.is_active
    assert len(delivered) == 1
    assert delivered[0].bid == Decimal("2499.50")


def test_adapter_list_instruments_empty(adapter: UpstoxDataAdapter) -> None:
    assert adapter.list_instruments() == []


def test_adapter_get_quote_snapshot(adapter: UpstoxDataAdapter) -> None:
    snap = adapter.get_quote_snapshot(_instrument())
    assert snap is not None
    assert snap.ltp == Decimal("2500.00")
    assert snap.provenance.source.broker_id == "upstox"
    assert snap.instrument.symbol == "RELIANCE"
