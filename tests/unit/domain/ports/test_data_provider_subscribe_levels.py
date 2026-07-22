"""DataProvider.subscribe(levels=...) routes depth level to gateway.stream_depth."""

from __future__ import annotations

from domain.entities.market import DepthLevel, MarketDepth
from domain.instruments.instrument_id import InstrumentId
from infrastructure.providers.broker.broker_data_provider import BrokerDataProvider
from tests.unit.domain._fakes import FakeProvider


class _FakeDepthHandle:
    def disconnect(self) -> None:
        pass


class _LevelsGateway:
    def __init__(self) -> None:
        self.stream_depth_calls: list[dict] = []

    def stream_depth(self, *, symbol, exchange, levels, on_depth):
        self.stream_depth_calls.append({"symbol": symbol, "exchange": exchange, "levels": levels})
        on_depth(
            MarketDepth(
                symbol=symbol,
                bids=[DepthLevel(price=100, quantity=1, orders=1)],
                asks=[DepthLevel(price=101, quantity=1, orders=1)],
            )
        )
        return _FakeDepthHandle()


def test_broker_data_provider_subscribe_passes_levels_to_stream_depth() -> None:
    gw = _LevelsGateway()
    provider = BrokerDataProvider(gw, broker_name="fake")
    iid = InstrumentId(exchange="NSE", underlying="RELIANCE")

    provider.subscribe(iid, lambda i, payload: None, depth=True, levels=30)

    assert gw.stream_depth_calls == [{"symbol": "RELIANCE", "exchange": "NSE", "levels": 30}]


def test_fake_provider_accepts_levels_keyword() -> None:
    provider = FakeProvider()
    provider.seed_quote("TCS", "NSE")
    iid = InstrumentId(exchange="NSE", underlying="TCS")
    handle = provider.subscribe(iid, lambda i, q: None, depth=False, levels=30)
    assert handle.is_active is True
