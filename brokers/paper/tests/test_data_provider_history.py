"""PaperDataProvider history/subscribe — Epic 1 market access."""

from __future__ import annotations

from decimal import Decimal

from brokers.paper.data_provider import PaperDataProvider
from brokers.paper.paper_gateway import PaperGateway
from domain.candles.historical import HistoricalSeries
from domain.instruments.instrument_id import InstrumentId


def test_get_history_returns_non_empty_dataframe() -> None:
    gw = PaperGateway(initial_capital=Decimal("100000"))
    provider = PaperDataProvider(gw)
    iid = InstrumentId.equity("NSE", "RELIANCE")
    df = provider.get_history(iid, timeframe="1D", lookback_days=7)
    assert df is not None
    assert len(df) == 7
    assert {"timestamp", "open", "high", "low", "close", "volume"}.issubset(df.columns)


def test_get_history_series_bar_count() -> None:
    gw = PaperGateway(initial_capital=Decimal("100000"))
    provider = PaperDataProvider(gw)
    iid = InstrumentId.equity("NSE", "INFY")
    series = provider.get_history_series(iid, timeframe="1D", lookback_days=5)
    assert isinstance(series, HistoricalSeries)
    assert series.bar_count == 5
    assert series.bars[0].close > 0


def test_subscribe_delivers_initial_quote() -> None:
    gw = PaperGateway(initial_capital=Decimal("100000"))
    provider = PaperDataProvider(gw)
    iid = InstrumentId.equity("NSE", "TCS")
    received: list = []
    handle = provider.subscribe(iid, lambda i, p: received.append(p))
    assert handle.is_active
    assert len(received) == 1
    assert received[0].ltp is not None
    handle.unsubscribe()
    assert not handle.is_active
