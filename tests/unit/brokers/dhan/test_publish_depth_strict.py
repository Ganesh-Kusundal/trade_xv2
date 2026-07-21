"""Unit tests for strict-mode ``_publish_depth`` (Plan §7.7).

Mirrors :mod:`test_publish_tick_strict` for the depth path. The legacy
``_publish_depth`` silently published any frame, including zero-quantity
or empty-side packets that downstream subscribers could mistake for real
snapshots. The strict mode drops such events and increments a counter
that ``health()`` exposes.

These tests pin the behaviour so a regression that re-introduces the
silent publish is caught immediately.
"""

from __future__ import annotations

from unittest import mock

from brokers.providers.dhan.websocket import DhanMarketFeed
from brokers.providers.dhan.websocket._helpers import _to_decimal
from brokers.providers.dhan.websocket.publish import MarketFeedPublisher


def _make_feed(event_bus=None) -> DhanMarketFeed:
    """Build a DhanMarketFeed with the SDK and resolver stubbed out."""
    import threading

    feed = DhanMarketFeed.__new__(DhanMarketFeed)
    feed._event_bus = event_bus
    # _published_depths/_dropped_depths/etc. are read-only properties
    # delegating to self._publisher (MarketFeedPublisher) -- see the
    # identical fix in test_publish_tick_strict.py for the full
    # explanation (property has no setter; _publish_depth() is a silent
    # no-op when self._publisher is None).
    feed._publisher = MarketFeedPublisher(
        event_bus,
        lambda symbol: 1,
        to_decimal=_to_decimal,
    )
    feed._thread = None
    feed._reconnect_count = 0
    feed._last_message_at = None
    feed._lock = threading.RLock()
    feed._is_connected = False
    return feed


def _good_bids():
    return [{"price": 2450.55, "quantity": 100, "orders": 5}]


def _good_asks():
    return [{"price": 2450.65, "quantity": 80, "orders": 4}]


# ── Happy path ──────────────────────────────────────────────────────────────


class TestPublishDepthHappyPath:
    def test_publishes_when_both_sides_present(self):
        bus = mock.MagicMock()
        feed = _make_feed(event_bus=bus)
        feed._publish_depth(
            {
                "symbol": "RELIANCE",
                "depth": {"bids": _good_bids(), "asks": _good_asks()},
            }
        )
        bus.publish.assert_called_once()
        assert feed._published_depths == 1
        assert feed._dropped_depths == 0

    def test_publishes_when_only_bids_present(self):
        bus = mock.MagicMock()
        feed = _make_feed(event_bus=bus)
        feed._publish_depth(
            {
                "symbol": "RELIANCE",
                "depth": {"bids": _good_bids(), "asks": []},
            }
        )
        bus.publish.assert_called_once()
        assert feed._published_depths == 1

    def test_publishes_when_only_asks_present(self):
        bus = mock.MagicMock()
        feed = _make_feed(event_bus=bus)
        feed._publish_depth(
            {
                "symbol": "RELIANCE",
                "depth": {"bids": [], "asks": _good_asks()},
            }
        )
        bus.publish.assert_called_once()
        assert feed._published_depths == 1


# ── Drop cases (the strict-mode rules) ─────────────────────────────────────


class TestPublishDepthStrictModeDrops:
    def test_drops_when_symbol_missing(self):
        bus = mock.MagicMock()
        feed = _make_feed(event_bus=bus)
        feed._publish_depth(
            {
                "depth": {"bids": _good_bids(), "asks": _good_asks()},
            }
        )
        bus.publish.assert_not_called()
        assert feed._dropped_depths == 1
        assert feed._published_depths == 0

    def test_drops_when_symbol_is_empty_string(self):
        bus = mock.MagicMock()
        feed = _make_feed(event_bus=bus)
        feed._publish_depth(
            {
                "symbol": "",
                "depth": {"bids": _good_bids(), "asks": _good_asks()},
            }
        )
        bus.publish.assert_not_called()
        assert feed._dropped_depths == 1

    def test_drops_when_both_sides_empty(self):
        bus = mock.MagicMock()
        feed = _make_feed(event_bus=bus)
        feed._publish_depth({"symbol": "RELIANCE", "depth": {"bids": [], "asks": []}})
        bus.publish.assert_not_called()
        assert feed._dropped_depths == 1

    def test_drops_when_top_bid_price_is_zero(self):
        bus = mock.MagicMock()
        feed = _make_feed(event_bus=bus)
        feed._publish_depth(
            {
                "symbol": "RELIANCE",
                "depth": {
                    "bids": [{"price": 0, "quantity": 100, "orders": 5}],
                    "asks": _good_asks(),
                },
            }
        )
        bus.publish.assert_not_called()
        assert feed._dropped_depths == 1

    def test_drops_when_top_ask_price_is_zero(self):
        bus = mock.MagicMock()
        feed = _make_feed(event_bus=bus)
        feed._publish_depth(
            {
                "symbol": "RELIANCE",
                "depth": {
                    "bids": _good_bids(),
                    "asks": [{"price": 0, "quantity": 100, "orders": 5}],
                },
            }
        )
        bus.publish.assert_not_called()
        assert feed._dropped_depths == 1

    def test_dropped_counter_accumulates(self):
        bus = mock.MagicMock()
        feed = _make_feed(event_bus=bus)
        for _ in range(5):
            feed._publish_depth(
                {
                    "symbol": "RELIANCE",
                    "depth": {"bids": [], "asks": []},
                }
            )
        assert feed._dropped_depths == 5
        assert feed._published_depths == 0


# ── No event bus configured ────────────────────────────────────────────────


class TestPublishDepthNoBus:
    def test_publish_depth_is_silent_when_no_event_bus(self):
        feed = _make_feed(event_bus=None)
        # Must not raise; must not increment counters either.
        feed._publish_depth(
            {
                "symbol": "RELIANCE",
                "depth": {"bids": _good_bids(), "asks": _good_asks()},
            }
        )
        assert feed._published_depths == 0
        assert feed._dropped_depths == 0


# ── health() exposes the counters ───────────────────────────────────────────


class TestHealthExposesDepthCounters:
    def test_health_metrics_contain_published_and_dropped(self):
        feed = _make_feed(event_bus=None)
        feed._publisher.published_depths = 17
        feed._publisher.dropped_depths = 4
        h = feed.health()
        assert h.metrics["published_depths"] == 17
        assert h.metrics["dropped_depths"] == 4

    def test_health_metrics_initialise_to_zero(self):
        feed = _make_feed(event_bus=None)
        h = feed.health()
        assert h.metrics["published_depths"] == 0
        assert h.metrics["dropped_depths"] == 0
