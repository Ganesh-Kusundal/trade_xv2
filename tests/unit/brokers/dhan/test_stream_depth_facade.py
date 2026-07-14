"""DhanBrokerGateway.stream_depth(levels=...) — canonical depth-level dispatch.

Mirrors the Upstox facade test (tests/unit/brokers/upstox/test_stream_depth_facade.py)
so both gateways can be driven by the same call shape.
"""

from __future__ import annotations

import pytest

from brokers.dhan.streaming.connection import DhanConnection
from brokers.dhan.wire import DhanBrokerGateway
from brokers.common.streaming import DepthStreamHandle
from domain import MarketDepth
from tests.support.brokers.dhan.fixtures import FakeHttpClient


def _make_gateway() -> DhanBrokerGateway:
    client = FakeHttpClient()
    conn = DhanConnection(client=client)
    return DhanBrokerGateway(conn)


def test_stream_depth_levels_5_delegates_to_depth(monkeypatch):
    gw = _make_gateway()
    snapshot = MarketDepth(symbol="RELIANCE", depth_type="DEPTH_5")
    monkeypatch.setattr(gw, "depth", lambda symbol, exchange: snapshot)

    handle = gw.stream_depth("RELIANCE", "NSE", levels=5)

    assert isinstance(handle, DepthStreamHandle)
    assert handle.initial is snapshot


def test_stream_depth_levels_5_with_on_depth_uses_live_full_mode_feed(monkeypatch):
    """levels=5 + on_depth must subscribe the live FULL-mode feed (which carries
    an embedded 5-level ladder per tick), not a one-shot REST snapshot — Dhan
    has no separate depth-5 WS feed the way it does for 20/200."""
    gw = _make_gateway()
    snapshot = MarketDepth(symbol="RELIANCE", depth_type="DEPTH_5")
    monkeypatch.setattr(gw, "depth", lambda symbol, exchange: snapshot)

    stream_calls = []
    monkeypatch.setattr(
        gw, "stream", lambda symbol, exchange, mode, on_tick: stream_calls.append((symbol, exchange, mode))
    )

    depth_callbacks = []

    class _FakeFeed:
        def on_depth(self, cb):
            depth_callbacks.append(cb)

        def off_depth(self, cb):
            depth_callbacks.remove(cb)

    fake_feed = _FakeFeed()
    monkeypatch.setattr(gw._conn, "market_feed", fake_feed)

    unstream_calls = []
    monkeypatch.setattr(
        gw, "unstream", lambda symbol, exchange, on_tick: unstream_calls.append((symbol, exchange))
    )

    received = []
    handle = gw.stream_depth("RELIANCE", "NSE", levels=5, on_depth=received.append)

    assert stream_calls == [("RELIANCE", "NSE", "FULL")]
    assert len(depth_callbacks) == 1
    assert handle.initial is snapshot

    depth_callbacks[0](
        {
            "symbol": "RELIANCE",
            "depth": {
                "bids": [{"price": "2450.00", "quantity": 100, "orders": 5}],
                "asks": [{"price": "2451.00", "quantity": 50, "orders": 2}],
            },
        }
    )
    assert len(received) == 1
    assert received[0].bids[0].price == 2450

    # A tick for a different symbol on the shared feed must be ignored.
    depth_callbacks[0]({"symbol": "TCS", "depth": {"bids": [], "asks": []}})
    assert len(received) == 1

    handle.stop()
    assert depth_callbacks == []
    assert unstream_calls == [("RELIANCE", "NSE")]


def test_stream_depth_levels_20_delegates_to_depth_20(monkeypatch):
    gw = _make_gateway()
    snapshot = MarketDepth(symbol="RELIANCE", depth_type="DEPTH_20")
    calls = []
    monkeypatch.setattr(
        gw, "depth_20", lambda symbol, exchange, on_depth=None: (calls.append((symbol, exchange)), snapshot)[1]
    )
    monkeypatch.setattr(gw._conn, "depth_20_feed", None)

    handle = gw.stream_depth("RELIANCE", "NSE", levels=20)

    assert calls == [("RELIANCE", "NSE")]
    assert handle.initial is snapshot


def test_stream_depth_levels_200_delegates_to_depth_200(monkeypatch):
    gw = _make_gateway()
    snapshot = MarketDepth(symbol="RELIANCE", depth_type="DEPTH_200")
    calls = []
    monkeypatch.setattr(
        gw, "depth_200", lambda symbol, exchange, on_depth=None: (calls.append((symbol, exchange)), snapshot)[1]
    )
    monkeypatch.setattr(gw._conn, "depth_200_feed", None)

    handle = gw.stream_depth("RELIANCE", "NSE", levels=200)

    assert calls == [("RELIANCE", "NSE")]
    assert handle.initial is snapshot


def test_stream_depth_unsupported_level_raises():
    gw = _make_gateway()

    with pytest.raises(ValueError, match="Dhan supports depth levels"):
        gw.stream_depth("RELIANCE", "NSE", levels=30)


def test_stream_depth_stop_unsubscribes_only_this_symbol(monkeypatch):
    """.stop() must unsubscribe just this symbol's feed subscription, not tear
    down the whole gateway (the real gap depth_20()/depth_200() alone leave open)."""
    gw = _make_gateway()
    snapshot = MarketDepth(symbol="RELIANCE", depth_type="DEPTH_20")
    monkeypatch.setattr(gw, "depth_20", lambda symbol, exchange, on_depth=None: snapshot)

    class _FakeRef:
        exchange_segment = "NSE_EQ"

        def security_id_str(self) -> str:
            return "2885"

    unsubscribe_calls = []

    class _FakeFeed:
        def unsubscribe(self, instruments):
            unsubscribe_calls.append(instruments)

    monkeypatch.setattr(gw._conn, "depth_20_feed", _FakeFeed())
    monkeypatch.setattr(
        gw._conn.instruments, "resolve_dhan_ref", lambda symbol, exchange: _FakeRef()
    )

    handle = gw.stream_depth("RELIANCE", "NSE", levels=20)
    handle.stop()

    assert unsubscribe_calls == [[("NSE_EQ", "2885")]]
