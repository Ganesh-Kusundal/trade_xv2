"""BrokerDataProvider.subscribe(depth=True) must route through gateway.stream_depth()
and deliver MarketDepth objects directly — not force them through the tick/QuoteSnapshot
path via an invalid mode="DEPTH" stream() call (real bug, fixed alongside the
Dhan/Upstox stream_depth(levels=...) standardization).
"""

from __future__ import annotations

from domain.entities.market import DepthLevel, MarketDepth
from domain.instruments.instrument_id import InstrumentId
from infrastructure.providers.broker.broker_data_provider import BrokerDataProvider


class _FakeDepthHandle:
    def __init__(self) -> None:
        self.stopped = False

    def disconnect(self) -> None:
        self.stopped = True


class _FakeGateway:
    """Minimal stand-in satisfying the gateway.stream()/stream_depth() surface."""

    def __init__(self) -> None:
        self.stream_depth_calls: list[dict] = []
        self.stream_calls: list[dict] = []
        self.handle = _FakeDepthHandle()

    def stream_depth(self, *, symbol, exchange, levels, on_depth):
        self.stream_depth_calls.append(
            {"symbol": symbol, "exchange": exchange, "levels": levels}
        )
        on_depth(
            MarketDepth(
                symbol=symbol,
                bids=[DepthLevel(price=100, quantity=10, orders=1)],
                asks=[DepthLevel(price=101, quantity=5, orders=1)],
            )
        )
        return self.handle

    def stream(self, *, symbol, exchange, mode, on_tick):
        self.stream_calls.append({"symbol": symbol, "exchange": exchange, "mode": mode})
        return self.handle


def test_subscribe_depth_true_routes_through_stream_depth():
    gw = _FakeGateway()
    provider = BrokerDataProvider(gw, broker_name="fake")
    iid = InstrumentId(exchange="NSE", underlying="RELIANCE")

    received = []
    provider.subscribe(iid, lambda i, payload: received.append(payload), depth=True)

    assert gw.stream_depth_calls == [{"symbol": "RELIANCE", "exchange": "NSE", "levels": 5}]
    assert gw.stream_calls == []
    assert len(received) == 1
    assert isinstance(received[0], MarketDepth)
    assert received[0].bids[0].price == 100


def test_subscribe_depth_false_uses_quote_mode_stream():
    gw = _FakeGateway()
    provider = BrokerDataProvider(gw, broker_name="fake")
    iid = InstrumentId(exchange="NSE", underlying="RELIANCE")

    provider.subscribe(iid, lambda i, payload: None, depth=False)

    assert gw.stream_depth_calls == []
    assert gw.stream_calls == [{"symbol": "RELIANCE", "exchange": "NSE", "mode": "QUOTE"}]
