"""Unit tests for DhanDepth20Feed, DhanDepth200Feed and gateway.depth_20/depth_200."""

from __future__ import annotations

import struct
from decimal import Decimal
from unittest import mock

import pytest

from brokers.common.core.domain import DepthLevel, MarketDepth

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _make_depth_packet(response_code, security_id, levels, total_slots=20):
    """Build a minimal Dhan depth-20 binary packet for testing."""
    HEADER_SIZE = 12
    LEVEL_SIZE = 16
    body_size = total_slots * LEVEL_SIZE
    packet = bytearray(HEADER_SIZE + body_size)
    struct.pack_into("<H", packet, 0, HEADER_SIZE + body_size)
    packet[2] = response_code
    packet[3] = 1
    struct.pack_into("<I", packet, 4, security_id)
    for i, (price, qty, orders) in enumerate(levels[:total_slots]):
        offset = HEADER_SIZE + i * LEVEL_SIZE
        struct.pack_into("<d", packet, offset, price)
        struct.pack_into("<I", packet, offset + 8, qty)
        struct.pack_into("<I", packet, offset + 12, orders)
    return bytes(packet)


def _make_200_packet(response_code, num_rows, levels):
    """Build a minimal Dhan depth-200 binary packet for testing."""
    HEADER_SIZE = 12
    LEVEL_SIZE = 16
    body = num_rows * LEVEL_SIZE
    packet = bytearray(HEADER_SIZE + body)
    packet[2] = response_code
    struct.pack_into("<I", packet, 8, num_rows)
    for i, (price, qty, orders) in enumerate(levels[:num_rows]):
        offset = HEADER_SIZE + i * LEVEL_SIZE
        struct.pack_into("<d", packet, offset, price)
        struct.pack_into("<I", packet, offset + 8, qty)
        struct.pack_into("<I", packet, offset + 12, orders)
    return bytes(packet)


def _make_feed20(instruments=None):
    from brokers.dhan.depth_20 import DhanDepth20Feed
    return DhanDepth20Feed("test_client", "test_token", instruments=instruments or [])


def _make_feed200(instrument=None):
    from brokers.dhan.depth_200 import DhanDepth200Feed
    return DhanDepth200Feed("test_client", "test_token", instrument=instrument)


# ──────────────────────────────────────────────────────────────────────────────
# DhanDepth20Feed
# ──────────────────────────────────────────────────────────────────────────────

class TestDhanDepth20Feed:

    def test_init_empty(self):
        feed = _make_feed20()
        assert feed._subscriptions == []
        assert feed._depth_cache == {}

    def test_init_with_instruments(self):
        feed = _make_feed20([("NSE_EQ", "500325")])
        assert len(feed._subscriptions) == 1

    def test_max_instruments_exceeded(self):
        from brokers.dhan.depth_20 import DhanDepth20Feed
        instruments = [("NSE_EQ", str(i)) for i in range(51)]
        with pytest.raises(ValueError, match="Maximum 50"):
            DhanDepth20Feed("c", "t", instruments=instruments)

    def test_subscribe_adds_instruments(self):
        feed = _make_feed20()
        feed.subscribe([("NSE_EQ", "500325"), ("NSE_FNO", "999")])
        assert len(feed._subscriptions) == 2

    def test_subscribe_exceeds_limit_raises(self):
        instruments = [("NSE_EQ", str(i)) for i in range(50)]
        feed = _make_feed20(instruments)
        with pytest.raises(ValueError, match="Maximum 50"):
            feed.subscribe([("NSE_EQ", "extra")])

    def test_parse_bid_packet(self):
        feed = _make_feed20()
        levels = [(24500.5, 100, 5), (24499.0, 200, 3)]
        packet = _make_depth_packet(41, 123456, levels)
        result = feed._parse_depth_packet(packet, 41, 123456)
        assert result["side"] == "bids"
        assert result["security_id"] == 123456
        assert len(result["levels"]) == 2
        assert result["levels"][0].price == Decimal("24500.5")
        assert result["levels"][0].quantity == 100

    def test_parse_ask_packet(self):
        feed = _make_feed20()
        levels = [(24501.0, 150, 2)]
        packet = _make_depth_packet(51, 777, levels)
        result = feed._parse_depth_packet(packet, 51, 777)
        assert result["side"] == "asks"
        assert result["security_id"] == 777

    def test_zero_qty_levels_skipped(self):
        feed = _make_feed20()
        levels = [(24500.0, 0, 0), (24499.0, 50, 1)]
        packet = _make_depth_packet(41, 1, levels)
        result = feed._parse_depth_packet(packet, 41, 1)
        assert len(result["levels"]) == 1
        assert result["levels"][0].quantity == 50

    def test_too_short_packet_no_crash(self):
        feed = _make_feed20()
        feed._process_binary_message(b"\x00\x01")

    def test_bid_cache_updated(self):
        feed = _make_feed20()
        bids = [DepthLevel(Decimal("100"), 10, 1)]
        feed._dispatch_depth({"side": "bids", "levels": bids, "security_id": 42})
        with feed._depth_cache_lock:
            assert feed._depth_cache[42]["bids"] == bids
            assert feed._depth_cache[42]["asks"] == []

    def test_ask_does_not_clear_bids(self):
        feed = _make_feed20()
        bids = [DepthLevel(Decimal("100"), 10, 1)]
        asks = [DepthLevel(Decimal("101"), 5, 2)]
        feed._dispatch_depth({"side": "bids", "levels": bids, "security_id": 42})
        feed._dispatch_depth({"side": "asks", "levels": asks, "security_id": 42})
        with feed._depth_cache_lock:
            assert feed._depth_cache[42]["bids"] == bids
            assert feed._depth_cache[42]["asks"] == asks

    def test_latest_depth_none_before_data(self):
        assert _make_feed20().latest_depth(99999) is None

    def test_latest_depth_returns_market_depth(self):
        feed = _make_feed20()
        bid = [DepthLevel(Decimal("200"), 20, 2)]
        ask = [DepthLevel(Decimal("201"), 10, 1)]
        feed._dispatch_depth({"side": "bids", "levels": bid, "security_id": 55})
        feed._dispatch_depth({"side": "asks", "levels": ask, "security_id": 55})
        depth = feed.latest_depth(55)
        assert isinstance(depth, MarketDepth)
        assert depth.depth_type == "DEPTH_20"
        assert depth.bids[0].price == Decimal("200")
        assert depth.asks[0].price == Decimal("201")

    def test_on_depth_callback_receives_market_depth(self):
        feed = _make_feed20()
        received = []
        feed.on_depth(received.append)
        feed._dispatch_depth({"side": "bids", "levels": [], "security_id": 7})
        assert len(received) == 1
        assert isinstance(received[0], MarketDepth)
        assert received[0].depth_type == "DEPTH_20"

    def test_callback_exception_does_not_propagate(self):
        feed = _make_feed20()
        feed.on_depth(lambda d: (_ for _ in ()).throw(RuntimeError("boom")))
        feed._dispatch_depth({"side": "bids", "levels": [], "security_id": 1})

    def test_multiple_callbacks_all_fired(self):
        feed = _make_feed20()
        a, b = [], []
        feed.on_depth(a.append)
        feed.on_depth(b.append)
        feed._dispatch_depth({"side": "asks", "levels": [], "security_id": 2})
        assert len(a) == len(b) == 1

    def test_full_binary_roundtrip(self):
        feed = _make_feed20()
        received = []
        feed.on_depth(received.append)
        levels = [(24500.0, 50, 2), (24499.5, 100, 5)]
        packet = _make_depth_packet(41, 500325, levels)
        feed._process_binary_message(packet)
        assert len(received) == 1
        assert received[0].depth_type == "DEPTH_20"
        assert len(received[0].bids) == 2

    def test_send_subscription_no_running_loop_no_crash(self):
        feed = _make_feed20()
        feed._ws = mock.MagicMock()
        feed._send_subscription([("NSE_EQ", "500325")])

    def test_health_stopped(self):
        from brokers.common.lifecycle.lifecycle import HealthState
        assert _make_feed20().health().state == HealthState.STOPPED

    def test_health_degraded(self):
        from brokers.common.lifecycle.lifecycle import HealthState
        feed = _make_feed20()
        feed._thread = mock.MagicMock()
        feed._thread.is_alive.return_value = True
        feed._is_connected = False
        assert feed.health().state == HealthState.DEGRADED


# ──────────────────────────────────────────────────────────────────────────────
# DhanDepth200Feed
# ──────────────────────────────────────────────────────────────────────────────

class TestDhanDepth200Feed:

    def test_init_no_instrument(self):
        feed = _make_feed200()
        assert feed._subscriptions == []
        assert feed._depth_cache == {"bids": [], "asks": []}

    def test_init_with_instrument(self):
        feed = _make_feed200(("NSE_EQ", "500325"))
        assert len(feed._subscriptions) == 1

    def test_latest_depth_none_before_data(self):
        assert _make_feed200().latest_depth() is None

    def test_dispatch_merges_sides(self):
        feed = _make_feed200()
        bid = [DepthLevel(Decimal("1000"), 5, 1)]
        ask = [DepthLevel(Decimal("1001"), 3, 1)]
        feed._dispatch_depth({"side": "bids", "levels": bid})
        feed._dispatch_depth({"side": "asks", "levels": ask})
        depth = feed.latest_depth()
        assert depth.depth_type == "DEPTH_200"
        assert depth.bids[0].price == Decimal("1000")
        assert depth.asks[0].price == Decimal("1001")

    def test_ask_does_not_wipe_bids(self):
        feed = _make_feed200()
        bid = [DepthLevel(Decimal("500"), 10, 2)]
        feed._dispatch_depth({"side": "bids", "levels": bid})
        feed._dispatch_depth({"side": "asks", "levels": []})
        assert len(feed.latest_depth().bids) == 1

    def test_on_depth_callback_receives_market_depth(self):
        feed = _make_feed200()
        received = []
        feed.on_depth(received.append)
        feed._dispatch_depth({"side": "bids", "levels": []})
        assert isinstance(received[0], MarketDepth)

    def test_parse_bid_packet_200(self):
        feed = _make_feed200()
        levels = [(1332.5, 100, 10), (1332.0, 200, 5)]
        packet = _make_200_packet(41, 2, levels)
        result = feed._parse_depth_packet(packet, 41, 2)
        assert result["side"] == "bids"
        assert len(result["levels"]) == 2

    def test_parse_ask_packet_200(self):
        feed = _make_feed200()
        packet = _make_200_packet(51, 1, [(1333.0, 50, 3)])
        result = feed._parse_depth_packet(packet, 51, 1)
        assert result["side"] == "asks"

    def test_send_subscription_no_running_loop_no_crash(self):
        feed = _make_feed200(("NSE_EQ", "500325"))
        feed._ws = mock.MagicMock()
        feed._send_subscription(("NSE_EQ", "500325"))


# ──────────────────────────────────────────────────────────────────────────────
# gateway.depth_20 / gateway.depth_200
# ──────────────────────────────────────────────────────────────────────────────

def _make_offline_gateway():
    from brokers.dhan.gateway import BrokerGateway
    from brokers.dhan.resolver import SymbolResolver

    resolver = SymbolResolver()
    resolver.load_from_rows([{
        "SEM_TRADING_SYMBOL": "RELIANCE",
        "SEM_CUSTOM_SYMBOL": "RELIANCE",
        "SEM_SMST_SECURITY_ID": "500325",
        "SEM_EXM_EXCH_ID": "NSE_EQ",
        "SEM_INSTRUMENT_NAME": "EQUITY",
        "SEM_LOT_UNITS": 1,
        "SEM_TICK_SIZE": 0.05,
    }])

    conn = mock.MagicMock()
    conn.instruments = resolver
    conn.client_id = "testclient"
    conn.access_token = "testtoken"
    conn.depth_20_feed = None
    conn.depth_200_feed = None
    conn.market_data.get_depth.return_value = MarketDepth(
        bids=[DepthLevel(Decimal("1330"), 50, 2)],
        asks=[DepthLevel(Decimal("1331"), 30, 1)],
        depth_type="DEPTH_5",
    )

    gw = BrokerGateway.__new__(BrokerGateway)
    gw._conn = conn
    return gw


class TestGatewayDepth20:

    def _mock_feed20(self):
        from brokers.dhan.depth_20 import DhanDepth20Feed
        f = mock.MagicMock(spec=DhanDepth20Feed)
        f._subscriptions = []
        f.is_running = False
        f.latest_depth.return_value = None
        return f

    def test_wrong_exchange_raises(self):
        gw = _make_offline_gateway()
        with pytest.raises(ValueError, match="NSE segments"):
            gw.depth_20("CRUDEOIL", exchange="MCX")

    def test_creates_feed_on_first_call(self):
        gw = _make_offline_gateway()
        f = self._mock_feed20()
        gw._conn.create_depth_20_feed.return_value = f
        gw.depth_20("RELIANCE")
        gw._conn.create_depth_20_feed.assert_called_once()
        f.start.assert_called_once()

    def test_falls_back_to_rest_when_cache_empty(self):
        gw = _make_offline_gateway()
        f = self._mock_feed20()
        gw._conn.create_depth_20_feed.return_value = f
        result = gw.depth_20("RELIANCE")
        assert result.depth_type == "DEPTH_5"
        gw._conn.market_data.get_depth.assert_called_once()

    def test_returns_cached_depth(self):
        gw = _make_offline_gateway()
        cached = MarketDepth(bids=[], asks=[], depth_type="DEPTH_20")
        f = self._mock_feed20()
        f.latest_depth.return_value = cached
        gw._conn.create_depth_20_feed.return_value = f
        result = gw.depth_20("RELIANCE")
        assert result.depth_type == "DEPTH_20"
        gw._conn.market_data.get_depth.assert_not_called()

    def test_reuses_existing_feed(self):
        gw = _make_offline_gateway()
        f = self._mock_feed20()
        f._subscriptions = [("NSE_EQ", "500325")]
        f.is_running = True
        gw._conn.depth_20_feed = f
        gw.depth_20("RELIANCE")
        gw._conn.create_depth_20_feed.assert_not_called()
        f.start.assert_not_called()

    def test_subscribes_new_symbol_on_existing_feed(self):
        gw = _make_offline_gateway()
        f = self._mock_feed20()
        f._subscriptions = [("NSE_EQ", "999999")]
        f.is_running = True
        gw._conn.depth_20_feed = f
        gw.depth_20("RELIANCE")
        f.subscribe.assert_called_once_with([("NSE_EQ", "500325")])

    def test_on_depth_callback_registered(self):
        gw = _make_offline_gateway()
        f = self._mock_feed20()
        gw._conn.create_depth_20_feed.return_value = f
        cb = mock.MagicMock()
        gw.depth_20("RELIANCE", on_depth=cb)
        f.on_depth.assert_called_once_with(cb)


class TestGatewayDepth200:

    def _mock_feed200(self):
        from brokers.dhan.depth_200 import DhanDepth200Feed
        f = mock.MagicMock(spec=DhanDepth200Feed)
        f._subscriptions = []
        f.is_running = False
        f.latest_depth.return_value = None
        return f

    def test_wrong_exchange_raises(self):
        gw = _make_offline_gateway()
        with pytest.raises(ValueError, match="NSE segments"):
            gw.depth_200("CRUDEOIL", exchange="MCX")

    def test_creates_feed_on_first_call(self):
        gw = _make_offline_gateway()
        f = self._mock_feed200()
        gw._conn.create_depth_200_feed.return_value = f
        gw.depth_200("RELIANCE")
        gw._conn.create_depth_200_feed.assert_called_once()
        f.start.assert_called_once()

    def test_falls_back_to_rest_when_cache_empty(self):
        gw = _make_offline_gateway()
        f = self._mock_feed200()
        gw._conn.create_depth_200_feed.return_value = f
        result = gw.depth_200("RELIANCE")
        assert result.depth_type == "DEPTH_5"

    def test_returns_cached_depth(self):
        gw = _make_offline_gateway()
        cached = MarketDepth(bids=[], asks=[], depth_type="DEPTH_200")
        f = self._mock_feed200()
        f.latest_depth.return_value = cached
        gw._conn.create_depth_200_feed.return_value = f
        result = gw.depth_200("RELIANCE")
        assert result.depth_type == "DEPTH_200"
        gw._conn.market_data.get_depth.assert_not_called()

    def test_rejects_second_different_instrument(self):
        gw = _make_offline_gateway()
        f = self._mock_feed200()
        f._subscriptions = [("NSE_EQ", "888888")]
        f.is_running = True
        gw._conn.depth_200_feed = f
        with pytest.raises(ValueError, match="already subscribed"):
            gw.depth_200("RELIANCE")
