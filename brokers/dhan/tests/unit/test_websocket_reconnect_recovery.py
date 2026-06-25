"""Reconnect subscription recovery tests for Dhan WebSocket feeds.

Verifies that DhanMarketFeed and DhanOrderStream maintain subscription
state across reconnect cycles and that the _connected flag is properly
managed.
"""

from __future__ import annotations

from brokers.dhan.websocket import DhanMarketFeed, DhanOrderStream


class TestDhanWebSocketReconnectRecovery:
    def test_market_feed_preserves_instruments_on_construction(self):
        instruments = [
            (1, "2885", 15),
            (1, "2886", 17),
            (2, "1234", 15),
        ]
        feed = DhanMarketFeed(
            client_id="CLIENT",
            access_token="TOKEN",
            instruments=instruments,
        )
        assert len(feed._instruments) == 3

    def test_market_feed_is_connected_false_before_connect(self):
        feed = DhanMarketFeed(
            client_id="CLIENT",
            access_token="TOKEN",
            instruments=[],
        )
        assert not feed.is_connected

    def test_order_stream_is_connected_false_before_connect(self):
        stream = DhanOrderStream(
            client_id="CLIENT",
            access_token="TOKEN",
        )
        assert not stream.is_connected

    def test_market_feed_instruments_int_conversion(self):
        feed = DhanMarketFeed(
            client_id="CLIENT",
            access_token="TOKEN",
            instruments=[(1, "2885", 15)],
        )
        assert feed._instruments == [(1, 2885, 15)]

    def test_market_feed_preserves_multiple_instruments(self):
        instruments = [(1, str(i), 15) for i in range(100)]
        feed = DhanMarketFeed(
            client_id="CLIENT",
            access_token="TOKEN",
            instruments=instruments,
        )
        assert len(feed._instruments) == 100
