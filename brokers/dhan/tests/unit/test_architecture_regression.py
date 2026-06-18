"""Regression tests for Dhan WebSocket architecture hardening.

Covers the 6 architecture fixes:
1. Dual feed path prevention — create_market_feed() stops existing feed
2. Callback dedup in gateway.stream()
3. Subscription limit enforcement (1000 cap)
4. unstream() unregistration mechanism
5. Cache eviction (_last_tick_time, _depth_cache) on unsubscribe
6. Thread-safe feed creation (_stream_lock)
"""

from __future__ import annotations

import threading
import time
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from brokers.dhan.gateway import BrokerGateway
from brokers.dhan.websocket import DhanMarketFeed
from brokers.dhan.depth_20 import DhanDepth20Feed


# ── Fix 1: Dual feed path prevention ────────────────────────────────────────


class TestDualFeedPrevention:

    def _make_connection(self):
        conn = MagicMock()
        conn.client_id = "TEST"
        conn._client = MagicMock()
        conn._client.client_id = "TEST"
        conn._client.access_token = "TOKEN"
        conn.access_token = "TOKEN"
        conn.instruments = MagicMock()
        conn._event_bus = None
        conn._lifecycle = None
        conn._backfill_callback = None
        conn._market_feed = None
        return conn

    def test_create_market_feed_stops_existing_feed(self):
        """create_market_feed() must stop the existing feed before creating a new one."""
        from brokers.dhan.connection import DhanConnection

        conn = MagicMock(spec=DhanConnection)
        conn._client = MagicMock()
        conn._client.client_id = "TEST"
        conn._event_bus = None
        conn._lifecycle = None
        conn._backfill_callback = None
        conn.instruments = MagicMock()

        old_feed = MagicMock()
        conn._market_feed = old_feed

        # Call the real create_market_feed
        DhanConnection.create_market_feed(conn, access_token="TOKEN")

        old_feed.stop.assert_called_once_with(timeout_seconds=5.0)

    def test_create_market_feed_noop_when_no_existing(self):
        """create_market_feed() should not fail when no existing feed."""
        from brokers.dhan.connection import DhanConnection

        conn = MagicMock(spec=DhanConnection)
        conn._client = MagicMock()
        conn._client.client_id = "TEST"
        conn._event_bus = None
        conn._lifecycle = None
        conn._backfill_callback = None
        conn.instruments = MagicMock()
        conn._market_feed = None

        feed = DhanConnection.create_market_feed(conn, access_token="TOKEN")
        assert feed is not None


# ── Fix 2: Callback dedup in stream() ───────────────────────────────────────


class TestStreamCallbackDedup:

    def _make_gateway(self):
        conn = MagicMock()
        conn.client_id = "TEST"
        conn.access_token = "TOKEN"
        conn.market_feed = None
        conn.instruments = MagicMock()
        conn.event_bus = None

        inst = MagicMock()
        inst.exchange = MagicMock()
        inst.exchange.value = "NSE"
        inst.security_id = "2885"
        conn.instruments.resolve.return_value = inst

        gw = BrokerGateway(conn)
        return gw

    def test_same_callback_not_registered_twice(self):
        """Calling stream() with the same on_tick for the same symbol must not duplicate."""
        gw = self._make_gateway()
        received = []

        def my_tick(q):
            received.append(q)

        gw.stream("RELIANCE", "NSE", on_tick=my_tick)
        gw.stream("RELIANCE", "NSE", on_tick=my_tick)

        assert len(gw._stream_registry.get(("RELIANCE", "NSE"), [])) == 1

    def test_different_callbacks_both_registered(self):
        """Different on_tick callbacks for the same symbol should both be registered."""
        gw = self._make_gateway()

        def tick_a(q):
            pass

        def tick_b(q):
            pass

        gw.stream("RELIANCE", "NSE", on_tick=tick_a)
        gw.stream("RELIANCE", "NSE", on_tick=tick_b)

        assert len(gw._stream_registry.get(("RELIANCE", "NSE"), [])) == 2

    def test_stream_without_callback_no_registry_entry(self):
        """stream() without on_tick should not create a registry entry."""
        gw = self._make_gateway()
        gw.stream("RELIANCE", "NSE")

        assert ("RELIANCE", "NSE") not in gw._stream_registry


# ── Fix 3: Subscription limit enforcement ───────────────────────────────────


class TestSubscriptionLimitEnforcement:

    def test_max_instruments_constant(self):
        """DhanMarketFeed must declare MAX_INSTRUMENTS = 1000."""
        assert DhanMarketFeed.MAX_INSTRUMENTS == 1000

    def test_subscribe_within_limit_succeeds(self):
        """subscribe() within the limit should succeed."""
        feed = DhanMarketFeed(client_id="X", instruments=[])
        feed.subscribe([("NSE_EQ", "2885", "LTP")])
        assert len(feed._instruments) == 1

    def test_subscribe_exceeding_limit_raises(self):
        """subscribe() beyond MAX_INSTRUMENTS must raise ValueError."""
        feed = DhanMarketFeed(client_id="X", instruments=[])
        # Pre-fill the subscription tracking set to the limit
        feed._subscribed_instruments = {(1, i, 15) for i in range(1000)}

        with pytest.raises(ValueError, match="1000"):
            feed.subscribe([("NSE", "9999", "LTP")])


# ── Fix 4: unstream() unregistration ────────────────────────────────────────


class TestUnstream:

    def _make_gateway_with_stream(self):
        gw = self._make_gateway()

        def my_tick(q):
            pass

        gw.stream("RELIANCE", "NSE", on_tick=my_tick)
        return gw, my_tick

    def _make_gateway(self):
        conn = MagicMock()
        conn.client_id = "TEST"
        conn.access_token = "TOKEN"
        conn.market_feed = None
        conn.instruments = MagicMock()
        conn.event_bus = None

        inst = MagicMock()
        inst.exchange = MagicMock()
        inst.exchange.value = "NSE"
        inst.security_id = "2885"
        conn.instruments.resolve.return_value = inst

        return BrokerGateway(conn)

    def test_unstream_removes_specific_callback(self):
        """unstream() with on_tick should remove only that callback."""
        gw = self._make_gateway()

        def tick_a(q):
            pass

        def tick_b(q):
            pass

        gw.stream("RELIANCE", "NSE", on_tick=tick_a)
        gw.stream("RELIANCE", "NSE", on_tick=tick_b)
        gw.unstream("RELIANCE", "NSE", on_tick=tick_a)

        remaining = gw._stream_registry.get(("RELIANCE", "NSE"), [])
        assert len(remaining) == 1
        assert remaining[0] is tick_b

    def test_unstream_all_removes_everything(self):
        """unstream() without on_tick should remove ALL callbacks and registry entry."""
        gw, my_tick = self._make_gateway_with_stream()
        gw.unstream("RELIANCE", "NSE")

        assert ("RELIANCE", "NSE") not in gw._stream_registry

    def test_unstream_nonexistent_is_noop(self):
        """unstream() for a symbol never streamed should not raise."""
        gw = self._make_gateway()
        gw.unstream("NONEXISTENT", "NSE")  # Should not raise


# ── Fix 5: Cache eviction ───────────────────────────────────────────────────


class TestCacheEviction:

    def test_last_tick_time_evicted_on_unsubscribe(self):
        """unstream() should remove _last_tick_time entries for the symbol."""
        gw = self._make_gateway_with_feed()
        feed = gw._conn.market_feed

        # Simulate tick tracking
        feed._last_tick_time["RELIANCE"] = "some_timestamp"

        gw.unstream("RELIANCE", "NSE")

        assert "RELIANCE" not in feed._last_tick_time

    def test_depth_20_cache_evicted_on_unsubscribe(self):
        """depth_20.unsubscribe() should evict _depth_cache entries."""
        feed = DhanDepth20Feed(
            client_id="X",
            access_token="T",
            instruments=[("NSE_EQ", "2885")],
        )
        # Populate depth cache
        feed._depth_cache[2885] = {"bids": [], "asks": []}

        feed.unsubscribe([("NSE_EQ", "2885")])

        assert 2885 not in feed._depth_cache

    def test_depth_20_subscribe_dedup(self):
        """depth_20.subscribe() should skip instruments already subscribed."""
        feed = DhanDepth20Feed(
            client_id="X",
            access_token="T",
            instruments=[("NSE_EQ", "2885")],
        )
        initial_count = len(feed._subscriptions)

        feed.subscribe([("NSE_EQ", "2885")])  # duplicate

        assert len(feed._subscriptions) == initial_count

    def _make_gateway_with_feed(self):
        conn = MagicMock()
        conn.client_id = "TEST"
        conn.access_token = "TOKEN"
        conn.instruments = MagicMock()
        conn.event_bus = None

        inst = MagicMock()
        inst.exchange = MagicMock()
        inst.exchange.value = "NSE"
        inst.security_id = "2885"
        conn.instruments.resolve.return_value = inst

        feed = MagicMock()
        feed._lock = threading.RLock()
        feed._last_tick_time = {}
        feed.is_connected = False
        conn.market_feed = feed

        gw = BrokerGateway(conn)
        gw.stream("RELIANCE", "NSE", on_tick=lambda q: None)
        return gw


# ── Fix 6: Thread-safe feed creation ────────────────────────────────────────


class TestThreadSafeStreamCreation:

    def test_concurrent_stream_creates_single_feed(self):
        """Multiple threads calling stream() simultaneously should create only one feed."""
        conn = MagicMock()
        conn.client_id = "TEST"
        conn.access_token = "TOKEN"
        conn.market_feed = None
        conn.instruments = MagicMock()
        conn.event_bus = None

        inst = MagicMock()
        inst.exchange = MagicMock()
        inst.exchange.value = "NSE"
        inst.security_id = "2885"
        conn.instruments.resolve.return_value = inst

        gw = BrokerGateway(conn)

        errors: list[Exception] = []
        results: list = []

        def stream_reliance():
            try:
                r = gw.stream("RELIANCE", "NSE")
                results.append(r)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=stream_reliance) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert not errors
        # All threads should get the same feed instance
        assert len(set(id(r) for r in results)) == 1

    def test_stream_lock_exists(self):
        """BrokerGateway must have a _stream_lock attribute."""
        conn = MagicMock()
        gw = BrokerGateway(conn)
        assert hasattr(gw, "_stream_lock")
        assert isinstance(gw._stream_lock, type(threading.Lock()))

    def test_stream_registry_exists(self):
        """BrokerGateway must have a _stream_registry attribute."""
        conn = MagicMock()
        gw = BrokerGateway(conn)
        assert hasattr(gw, "_stream_registry")
        assert isinstance(gw._stream_registry, dict)
