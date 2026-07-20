"""Regression test for the start()/stop() race in MarketFeedConnection.

Reproduces (deterministically, without real network/asyncio) the bug where
calling stop() immediately after start() could close the SDK feed before the
background thread had taken ownership of its event loop via feed.run(),
racing the SDK's own loop.run_until_complete() call on the same loop object
from two threads and raising "This event loop is already running".

The fix adds a threading.Event (``_run_claimed``) set by the background
thread right before it calls feed.run(), which stop() now waits on before
touching the feed. This test asserts that invariant holds even when stop()
is called with zero delay after start() returns.
"""

from __future__ import annotations

import threading
import time
from io import StringIO
from unittest import mock
from unittest.mock import MagicMock

from brokers.dhan.websocket.connection import MarketFeedConnection
from tests.support.brokers.dhan.mock_sdk import mock_market_feed_class


class _FakeSDKFeed:
    """Stand-in for dhanhq's MarketFeed — records call ordering, never raises."""

    ready = threading.Event()

    def __init__(self, **kwargs) -> None:
        self.run_called_at: float | None = None
        self.close_called_at: float | None = None
        self._run_delay = 0.02

    def run(self) -> None:
        self.run_called_at = time.monotonic()
        self.ready.set()
        time.sleep(self._run_delay)

    def close_connection(self) -> None:
        self.close_called_at = time.monotonic()

    def subscribe_symbols(self, instruments) -> None:
        pass


def _make_connection(fake_feed: _FakeSDKFeed) -> MarketFeedConnection:
    conn = MarketFeedConnection(
        feed_ref=mock.MagicMock(),
        client_id="CLIENT",
        context=mock.MagicMock(),
        subscribed_instruments_getter=lambda: {(1, "2885", 15)},
        lock=threading.RLock(),
        stop_event=threading.Event(),
    )
    conn._set_admission_for_test(None)
    return conn


def test_stop_immediately_after_start_never_closes_before_run_claims_loop():
    fake_feed = _FakeSDKFeed()

    with mock_market_feed_class() as mock_cls:
        mock_cls.return_value = MagicMock(return_value=fake_feed)
        conn = _make_connection(fake_feed)
        started = conn.start()
        assert started is True
        assert fake_feed.ready.wait(timeout=2.0)
        conn.stop(timeout_seconds=2.0)

    assert fake_feed.run_called_at is not None, "feed.run() was never entered"
    assert fake_feed.close_called_at is not None, "close_connection() was never called"
    assert fake_feed.close_called_at >= fake_feed.run_called_at, (
        "stop() closed the SDK feed before the background thread claimed "
        "the loop via feed.run() — this is the race that raises "
        "'This event loop is already running'"
    )


def test_stop_without_start_does_not_hang():
    fake_feed = _FakeSDKFeed()
    with mock_market_feed_class() as mock_cls:
        mock_cls.return_value = MagicMock(return_value=fake_feed)
        conn = _make_connection(fake_feed)
        started = time.monotonic()
        conn.stop(timeout_seconds=2.0)
        elapsed = time.monotonic() - started

    # No feed was ever built, so stop() must not wait on _run_claimed at all.
    assert elapsed < 0.5
    assert fake_feed.close_called_at is None
