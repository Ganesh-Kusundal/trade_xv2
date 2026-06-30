"""API WebSocket feed wiring: subscribe/unsubscribe symmetry with broker gateway."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import api.ws.feed_wiring as feed_wiring


class TestFeedWiringBrokerSymmetry:
    def setup_method(self) -> None:
        feed_wiring._api_subscriptions.clear()

    def test_subscribe_records_symbols_for_later_unsubscribe(self) -> None:
        gateway = MagicMock()
        container = MagicMock()
        container.broker_service = MagicMock(_gateway=gateway)

        with patch("api.deps.get_container", return_value=container):
            feed_wiring.subscribe_symbols_to_broker(["RELIANCE", "TCS"], exchange="NSE")

        assert gateway.stream.call_count == 2
        assert "RELIANCE:NSE" in feed_wiring._api_subscriptions
        assert "TCS:NSE" in feed_wiring._api_subscriptions

    def test_unsubscribe_calls_gateway_unstream_for_each_symbol(self) -> None:
        gateway = MagicMock()
        container = MagicMock()
        container.broker_service = MagicMock(_gateway=gateway)
        feed_wiring._api_subscriptions["RELIANCE:NSE"] = ("RELIANCE", "NSE")

        with patch("api.deps.get_container", return_value=container):
            feed_wiring.unsubscribe_symbols_from_broker(["RELIANCE"], exchange="NSE")

        gateway.unstream.assert_called_once_with(symbol="RELIANCE", exchange="NSE")
        assert "RELIANCE:NSE" not in feed_wiring._api_subscriptions

    def test_unsubscribe_is_noop_when_container_unavailable(self) -> None:
        feed_wiring._api_subscriptions["RELIANCE:NSE"] = ("RELIANCE", "NSE")

        with patch("api.deps.get_container", side_effect=RuntimeError("no app")):
            feed_wiring.unsubscribe_symbols_from_broker(["RELIANCE"])

        assert "RELIANCE:NSE" in feed_wiring._api_subscriptions
