"""Tests for WebSocket auto-wiring in BrokerFactory."""

from __future__ import annotations

from unittest.mock import patch

from brokers.common.event_bus import EventBus
from brokers.common.lifecycle import LifecycleManager
from brokers.common.lifecycle.lifecycle import HealthState
from brokers.dhan import BrokerFactory


class TestFactoryWebSocketWiring:
    """Verify that BrokerFactory auto-creates and registers WebSocket services."""

    def test_factory_auto_creates_market_feed_with_lifecycle(self, tmp_path):
        """Factory.create() should auto-create DhanMarketFeed when lifecycle provided."""
        env_file = tmp_path / ".env.local"
        env_file.write_text(
            "DHAN_CLIENT_ID=TEST_CLIENT\n"
            "DHAN_ACCESS_TOKEN=test_token\n"
            "DHAN_PIN=1234\n"
            "DHAN_TOTP_SECRET=TESTTOTPSECRET\n"
        )

        lifecycle = LifecycleManager()
        event_bus = EventBus()

        with patch("brokers.dhan.factory._generate_totp_token", return_value="test_token"):
            gateway = BrokerFactory.create(
                env_path=env_file,
                load_instruments=False,
                event_bus=event_bus,
                lifecycle=lifecycle,
            )

        # Market feed should be created
        assert gateway._conn.market_feed is not None
        assert gateway._conn.market_feed.name == "dhan.market_feed"

        # Should be registered with lifecycle
        assert "dhan.market_feed" in lifecycle.service_names()

    def test_factory_auto_creates_order_stream_with_lifecycle(self, tmp_path):
        """Factory.create() should auto-create DhanOrderStream when lifecycle provided."""
        env_file = tmp_path / ".env.local"
        env_file.write_text(
            "DHAN_CLIENT_ID=TEST_CLIENT\n"
            "DHAN_ACCESS_TOKEN=test_token\n"
            "DHAN_PIN=1234\n"
            "DHAN_TOTP_SECRET=TESTTOTPSECRET\n"
        )

        lifecycle = LifecycleManager()
        event_bus = EventBus()

        with patch("brokers.dhan.factory._generate_totp_token", return_value="test_token"):
            gateway = BrokerFactory.create(
                env_path=env_file,
                load_instruments=False,
                event_bus=event_bus,
                lifecycle=lifecycle,
            )

        # Order stream should be created
        assert gateway._conn.order_stream is not None
        assert gateway._conn.order_stream.name == "dhan.order_stream"

        # Should be registered with lifecycle
        assert "dhan.order_stream" in lifecycle.service_names()

    def test_factory_no_lifecycle_no_auto_wire(self, tmp_path):
        """Without lifecycle, factory should NOT auto-wire (backward compat)."""
        env_file = tmp_path / ".env.local"
        env_file.write_text(
            "DHAN_CLIENT_ID=TEST_CLIENT\n"
            "DHAN_ACCESS_TOKEN=test_token\n"
            "DHAN_PIN=1234\n"
            "DHAN_TOTP_SECRET=TESTTOTPSECRET\n"
        )

        with patch("brokers.dhan.factory._generate_totp_token", return_value="test_token"):
            gateway = BrokerFactory.create(
                env_path=env_file,
                load_instruments=False,
                # No lifecycle, no event_bus
            )

        # Should NOT auto-create WebSocket services (lazy creation)
        assert gateway._conn.market_feed is None
        assert gateway._conn.order_stream is None

    def test_factory_no_event_bus_no_auto_wire(self, tmp_path):
        """Without event_bus, factory should NOT auto-wire."""
        env_file = tmp_path / ".env.local"
        env_file.write_text(
            "DHAN_CLIENT_ID=TEST_CLIENT\n"
            "DHAN_ACCESS_TOKEN=test_token\n"
            "DHAN_PIN=1234\n"
            "DHAN_TOTP_SECRET=TESTTOTPSECRET\n"
        )

        lifecycle = LifecycleManager()

        with patch("brokers.dhan.factory._generate_totp_token", return_value="test_token"):
            gateway = BrokerFactory.create(
                env_path=env_file,
                load_instruments=False,
                lifecycle=lifecycle,
                # No event_bus
            )

        # Should NOT auto-create WebSocket services
        assert gateway._conn.market_feed is None
        assert gateway._conn.order_stream is None

    def test_factory_websocket_registered_not_started(self, tmp_path):
        """WebSocket services should be registered but not started until lifecycle.start_all()."""
        env_file = tmp_path / ".env.local"
        env_file.write_text(
            "DHAN_CLIENT_ID=TEST_CLIENT\n"
            "DHAN_ACCESS_TOKEN=test_token\n"
            "DHAN_PIN=1234\n"
            "DHAN_TOTP_SECRET=TESTTOTPSECRET\n"
        )

        lifecycle = LifecycleManager()
        event_bus = EventBus()

        with patch("brokers.dhan.factory._generate_totp_token", return_value="test_token"):
            gateway = BrokerFactory.create(
                env_path=env_file,
                load_instruments=False,
                event_bus=event_bus,
                lifecycle=lifecycle,
            )

        # Services should be registered
        assert "dhan.market_feed" in lifecycle.service_names()
        assert "dhan.order_stream" in lifecycle.service_names()

        # But not started yet (lifecycle.start_all() not called)
        market_feed_health = gateway._conn.market_feed.health()
        order_stream_health = gateway._conn.order_stream.health()

        # Should be STOPPED initially (not started)
        assert market_feed_health.state == HealthState.STOPPED
        assert order_stream_health.state == HealthState.STOPPED
