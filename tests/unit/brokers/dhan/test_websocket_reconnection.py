"""Unit and chaos tests for Dhan WebSocket reconnection hardening (H2 Critical Fix).

Wall-clock backoff is zeroed via ``zero_ws_failure_backoff`` so these stay
unit-fast; production defaults remain 1s / exponential.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from tests.support.brokers.dhan.mock_sdk import mock_market_feed_class


def _wait_until(pred: Callable[[], bool], *, timeout: float = 2.0, interval: float = 0.005) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pred():
            return
        time.sleep(interval)
    raise AssertionError(f"condition not met within {timeout}s")


@pytest.fixture
def zero_ws_failure_backoff(monkeypatch):
    """Collapse reconnect failure backoff; leave cooldown so max-attempt parks."""
    monkeypatch.setattr("brokers.dhan.websocket.connection.DHAN_INITIAL_BACKOFF_SECONDS", 0.0)
    monkeypatch.setattr("brokers.dhan.websocket.connection.DHAN_BACKOFF_BASE_DELAY_MS", 0.0)


def _make_feed(mock_sdk, *, monkeypatch_admission: bool = True):
    """Build DhanMarketFeed under an active SDK patch with sticky fake rebuild."""
    from brokers.dhan.websocket import DhanMarketFeed

    mock_sdk_instance = MagicMock()
    mock_sdk.return_value = mock_sdk_instance
    mock_sdk.return_value.return_value = mock_sdk_instance

    mock_admission = MagicMock()
    mock_admission.try_acquire.return_value = True
    mock_admission.seconds_until_connect_allowed.return_value = 0.0
    mock_admission.lock_held = True

    feed = DhanMarketFeed(
        client_id="test_client",
        access_token="test_token",
        admission=mock_admission if monkeypatch_admission else None,
    )
    feed._conn._feed = mock_sdk_instance

    def _fake_build():
        feed._conn._feed = mock_sdk_instance
        return mock_sdk_instance

    feed._conn._build_sdk_feed_locked = _fake_build
    return feed, mock_sdk_instance


class TestDhanMarketFeedMaxReconnectAttempts:
    """Test max reconnect attempts prevents infinite retry loop."""

    def test_max_reconnect_attempts_stops_feed(self, monkeypatch, zero_ws_failure_backoff):
        """Feed should park after MAX_RECONNECT_ATTEMPTS failures (cooldown)."""
        monkeypatch.setattr("brokers.dhan.websocket.connection.DHAN_MAX_RECONNECT_ATTEMPTS", 5)

        with mock_market_feed_class() as mock_sdk:
            feed, mock_sdk_instance = _make_feed(mock_sdk)

            call_count = 0

            def fail_on_run():
                nonlocal call_count
                call_count += 1
                raise ConnectionError("Connection lost")

            mock_sdk_instance.run.side_effect = fail_on_run

            thread = threading.Thread(target=feed._run, daemon=True)
            thread.start()

            _wait_until(lambda: call_count >= 5 or feed._reconnect_count >= 5)
            feed._stop_event.set()
            thread.join(timeout=2.0)

            assert call_count <= 6, f"Feed continued beyond max attempts: {call_count}"
            assert feed._is_connected is False

    def test_reconnect_count_resets_on_success(self, monkeypatch, zero_ws_failure_backoff):
        """Reconnect count should reset after successful connection."""
        monkeypatch.setattr("brokers.dhan.websocket.connection.DHAN_MAX_RECONNECT_ATTEMPTS", 50)

        with mock_market_feed_class() as mock_sdk:
            feed, mock_sdk_instance = _make_feed(mock_sdk)

            call_count = 0

            def intermittent_failures():
                nonlocal call_count
                call_count += 1
                if call_count <= 3 or call_count == 5:
                    raise ConnectionError("Connection lost")
                # Successful connect resets the counter (SDK on_connect path).
                feed._conn._on_connect(mock_sdk_instance)

            mock_sdk_instance.run.side_effect = intermittent_failures

            thread = threading.Thread(target=feed._run, daemon=True)
            thread.start()

            _wait_until(lambda: call_count >= 5)
            feed._stop_event.set()
            thread.join(timeout=2.0)

            assert feed._reconnect_count <= 2, (
                f"Reconnect count didn't reset after success: {feed._reconnect_count}"
            )


class TestDhanMarketFeedStalenessDetection:
    """Test staleness detection warns on ghost connections."""

    @pytest.fixture
    def feed_with_old_message(self):
        from brokers.dhan.websocket import DhanMarketFeed
        from datetime import timedelta

        feed = DhanMarketFeed(
            client_id="test_client",
            access_token="test_token",
        )
        feed._last_message_at = datetime.now(timezone.utc) - timedelta(seconds=120)
        feed._message_count = 10
        return feed

    def test_staleness_detected_in_health(self, feed_with_old_message, monkeypatch):
        feed = feed_with_old_message
        monkeypatch.setenv("DHAN_STALENESS_THRESHOLD_SECONDS", "60.0")

        health = feed.health()

        assert health.metrics["is_stale"] is True
        assert health.metrics["last_message_age_seconds"] >= 120
        assert health.metrics["staleness_threshold_seconds"] == 60.0

    def test_no_staleness_when_recent_message(self, monkeypatch):
        from brokers.dhan.websocket import DhanMarketFeed

        feed = DhanMarketFeed(
            client_id="test_client",
            access_token="test_token",
        )
        feed._last_message_at = datetime.now(timezone.utc)
        feed._message_count = 100

        monkeypatch.setenv("DHAN_STALENESS_THRESHOLD_SECONDS", "60.0")

        health = feed.health()

        assert health.metrics["is_stale"] is False
        assert health.metrics["last_message_age_seconds"] < 1.0


class TestDhanMarketFeedHealthMetrics:
    """Test health endpoint exposes all reconnect metrics."""

    def test_health_exposes_reconnect_metrics(self):
        from brokers.dhan.websocket import DhanMarketFeed

        feed = DhanMarketFeed(
            client_id="test_client",
            access_token="test_token",
        )

        feed._reconnect_count = 10
        feed._is_connected = True
        feed._last_message_at = datetime.now(timezone.utc)

        health = feed.health()

        assert "max_reconnect_attempts" in health.metrics
        assert "is_stale" in health.metrics
        assert "staleness_threshold_seconds" in health.metrics
        assert "reconnect_count" in health.metrics
        assert "last_message_age_seconds" in health.metrics

        assert health.metrics["max_reconnect_attempts"] == 50
        assert health.metrics["reconnect_count"] == 10
        assert health.metrics["is_stale"] is False

    def test_health_max_reconnect_attempts_configurable(self, monkeypatch):
        from brokers.dhan.websocket import DhanMarketFeed

        monkeypatch.setattr("config.ws_settings.DHAN_MAX_RECONNECT_ATTEMPTS", 100)

        feed = DhanMarketFeed(
            client_id="test_client",
            access_token="test_token",
        )

        health = feed.health()

        assert health.metrics["max_reconnect_attempts"] == 100


class TestDhanMarketFeedChaosScenarios:
    """Chaos tests for extreme failure scenarios."""

    def test_rapid_reconnect_does_not_exhaust_resources(self, monkeypatch, zero_ws_failure_backoff):
        monkeypatch.setattr("brokers.dhan.websocket.connection.DHAN_MAX_RECONNECT_ATTEMPTS", 3)

        with mock_market_feed_class() as mock_sdk:
            feed, mock_sdk_instance = _make_feed(mock_sdk)
            mock_sdk_instance.run.side_effect = ConnectionError("Immediate fail")

            thread = threading.Thread(target=feed._run, daemon=True)
            thread.start()

            _wait_until(lambda: feed._reconnect_count >= 3 or mock_sdk_instance.run.call_count >= 3)
            feed._stop_event.set()
            thread.join(timeout=2.0)

            assert feed._reconnect_count >= 3 or mock_sdk_instance.run.call_count >= 3
            assert feed._is_connected is False

    def test_intermittent_failures_handled_gracefully(self, monkeypatch, zero_ws_failure_backoff):
        monkeypatch.setattr("brokers.dhan.websocket.connection.DHAN_MAX_RECONNECT_ATTEMPTS", 20)

        with mock_market_feed_class() as mock_sdk:
            feed, mock_sdk_instance = _make_feed(mock_sdk)

            call_count = 0

            def pattern():
                nonlocal call_count
                call_count += 1
                if call_count % 2 == 1:
                    raise ConnectionError("Fail")

            mock_sdk_instance.run.side_effect = pattern

            thread = threading.Thread(target=feed._run, daemon=True)
            thread.start()

            _wait_until(lambda: call_count >= 4)
            feed._stop_event.set()
            thread.join(timeout=2.0)

            assert call_count >= 4, f"Expected at least 4 calls, got {call_count}"
