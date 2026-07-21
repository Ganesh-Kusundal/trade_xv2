"""API WebSocket feed wiring: subscribe/unsubscribe symmetry with broker gateway."""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import patch

import interface.api.ws.feed_wiring as feed_wiring


@dataclass
class RecordingGateway:
    stream_calls: list[tuple[str, str, str]] = field(default_factory=list)
    unstream_calls: list[tuple[str, str]] = field(default_factory=list)

    def stream(self, *, symbol: str, exchange: str, mode: str = "FULL") -> None:
        self.stream_calls.append((symbol, exchange, mode))

    def unstream(self, *, symbol: str, exchange: str) -> None:
        self.unstream_calls.append((symbol, exchange))


@dataclass
class FakeBrokerService:
    active_gateway: RecordingGateway


@dataclass
class FakeContainer:
    broker_service: FakeBrokerService


class TestFeedWiringBrokerSymmetry:
    def setup_method(self) -> None:
        feed_wiring._api_subscriptions.clear()

    def test_subscribe_records_symbols_for_later_unsubscribe(self) -> None:
        gateway = RecordingGateway()
        container = FakeContainer(broker_service=FakeBrokerService(active_gateway=gateway))

        with patch("interface.api.deps.get_container", return_value=container):
            feed_wiring.subscribe_symbols_to_broker(["RELIANCE", "TCS"], exchange="NSE")

        assert gateway.stream_calls == [
            ("RELIANCE", "NSE", "FULL"),
            ("TCS", "NSE", "FULL"),
        ]
        assert "RELIANCE:NSE" in feed_wiring._api_subscriptions
        assert "TCS:NSE" in feed_wiring._api_subscriptions

    def test_unsubscribe_calls_gateway_unstream_for_each_symbol(self) -> None:
        gateway = RecordingGateway()
        container = FakeContainer(broker_service=FakeBrokerService(active_gateway=gateway))
        feed_wiring._api_subscriptions["RELIANCE:NSE"] = ("RELIANCE", "NSE")

        with patch("interface.api.deps.get_container", return_value=container):
            feed_wiring.unsubscribe_symbols_from_broker(["RELIANCE"], exchange="NSE")

        assert gateway.unstream_calls == [("RELIANCE", "NSE")]
        assert "RELIANCE:NSE" not in feed_wiring._api_subscriptions

    def test_unsubscribe_is_noop_when_container_unavailable(self) -> None:
        feed_wiring._api_subscriptions["RELIANCE:NSE"] = ("RELIANCE", "NSE")

        with patch("interface.api.deps.get_container", side_effect=RuntimeError("no app")):
            feed_wiring.unsubscribe_symbols_from_broker(["RELIANCE"])

        assert "RELIANCE:NSE" in feed_wiring._api_subscriptions
