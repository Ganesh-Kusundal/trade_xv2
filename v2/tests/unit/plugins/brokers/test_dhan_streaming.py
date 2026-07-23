"""Tests for DhanStreamingAdapter — WS auto-reconnect support."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from domain.value_objects import InstrumentId
from plugins.brokers.common.ws_reconnect import ReconnectConfig, WsReconnectManager
from plugins.brokers.dhan.wire import DhanWire
from plugins.brokers.dhan.adapters.streaming import DhanStreamingAdapter


class FakeWs:
    """Mock WebSocket that records sends."""

    def __init__(self) -> None:
        self.sent: list[str] = []
        self.closed = False

    def send(self, data: str) -> None:
        self.sent.append(data)

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def wire() -> DhanWire:
    w = DhanWire()
    w.register_security(InstrumentId.parse("NSE:RELIANCE"), "2885")
    return w


def _make_adapter(
    wire: DhanWire,
    reconnect_config: ReconnectConfig | None = None,
    ws_factory=None,
) -> tuple[DhanStreamingAdapter, list[FakeWs]]:
    """Helper: create adapter with tracked WS instances."""
    instances: list[FakeWs] = []

    def factory(url: str) -> FakeWs:
        ws = FakeWs()
        instances.append(ws)
        return ws

    adapter = DhanStreamingAdapter(
        wire=wire,
        token_provider=lambda: "tok",
        client_id="c1",
        ws_factory=ws_factory or factory,
        reconnect_config=reconnect_config,
    )
    return adapter, instances


class TestReconnectTriggersOnClose:
    def test_handle_ws_close_sets_ws_none(self, wire: DhanWire) -> None:
        adapter, _ = _make_adapter(wire)
        adapter.stream(InstrumentId.parse("NSE:RELIANCE"))
        assert adapter._ws is not None
        adapter._handle_ws_close()
        assert adapter._ws is None

    def test_handle_ws_close_spawns_reconnect_thread(self, wire: DhanWire) -> None:
        adapter, _ = _make_adapter(wire, ReconnectConfig(max_retries=0))
        adapter.stream(InstrumentId.parse("NSE:RELIANCE"))
        with patch("plugins.brokers.dhan.adapters.streaming.threading.Thread") as mock_thread:
            mock_instance = MagicMock()
            mock_thread.return_value = mock_instance
            adapter._handle_ws_close()
            mock_thread.assert_called_once()
            mock_instance.start.assert_called_once()


class TestSubscriptionsReplayedAfterReconnect:
    def test_replay_resends_quote_subscribe(self, wire: DhanWire) -> None:
        adapter, instances = _make_adapter(wire, ReconnectConfig(max_retries=1))
        adapter.stream(InstrumentId.parse("NSE:RELIANCE"))
        assert len(instances) == 1

        # Simulate disconnect without thread
        adapter._reconnect_manager.on_close()
        adapter._ws = None
        adapter._do_reconnect()

        assert len(instances) == 2
        replayed_msg = json.loads(instances[1].sent[0])
        assert replayed_msg["RequestCode"] == 15
        assert replayed_msg["InstrumentList"][0]["SecurityId"] == "2885"

    def test_replay_resends_order_subscribe(self, wire: DhanWire) -> None:
        adapter, instances = _make_adapter(wire, ReconnectConfig(max_retries=1))
        adapter.stream_order(on_order=lambda o: None)
        assert len(instances) == 1

        adapter._reconnect_manager.on_close()
        adapter._ws = None
        adapter._do_reconnect()

        assert len(instances) == 2
        assert len(instances[1].sent) >= 1

    def test_replay_multiple_subscriptions(self, wire: DhanWire) -> None:
        wire.register_security(InstrumentId.parse("NSE:TCS"), "11536")
        adapter, instances = _make_adapter(wire, ReconnectConfig(max_retries=1))
        adapter.stream(InstrumentId.parse("NSE:RELIANCE"))
        adapter.stream(InstrumentId.parse("NSE:TCS"))
        assert len(instances) == 1

        adapter._reconnect_manager.on_close()
        adapter._ws = None
        adapter._do_reconnect()

        assert len(instances) == 2
        sent_ids = set()
        for msg_str in instances[1].sent:
            msg = json.loads(msg_str)
            for item in msg["InstrumentList"]:
                sent_ids.add(item["SecurityId"])
        assert sent_ids == {"2885", "11536"}


class TestReconnectRespectsMaxRetries:
    def test_stops_after_max_retries(self, wire: DhanWire) -> None:
        call_count = 0
        fail_after = 1  # first call succeeds (initial connect), subsequent fail

        def flaky_factory(url: str) -> FakeWs:
            nonlocal call_count
            call_count += 1
            if call_count > fail_after:
                raise ConnectionError("nope")
            return FakeWs()

        adapter, _ = _make_adapter(
            wire,
            ReconnectConfig(max_retries=3, base_delay=0.01),
            ws_factory=flaky_factory,
        )
        adapter.stream(InstrumentId.parse("NSE:RELIANCE"))
        assert adapter._ws is not None

        # Simulate disconnect without thread
        adapter._reconnect_manager.on_close()
        adapter._ws = None
        adapter._do_reconnect()

        # initial connect = 1, reconnect attempts = 3 (all fail)
        assert call_count == 1 + 3

    def test_default_config_allows_reconnect(self, wire: DhanWire) -> None:
        adapter, instances = _make_adapter(wire, reconnect_config=None)
        adapter.stream(InstrumentId.parse("NSE:RELIANCE"))

        adapter._reconnect_manager.on_close()
        adapter._ws = None
        adapter._do_reconnect()

        assert adapter._ws is not None
        assert len(instances) == 2


class TestEnsureWsTracking:
    def test_ensure_ws_sets_reconnect_manager_on_connect(self, wire: DhanWire) -> None:
        adapter, _ = _make_adapter(wire)
        assert adapter._reconnect_manager.is_connected is False
        adapter._ensure_ws()
        assert adapter._reconnect_manager.is_connected is True

    def test_ensure_ws_noop_when_ws_exists(self, wire: DhanWire) -> None:
        adapter, instances = _make_adapter(wire)
        adapter._ensure_ws()
        adapter._ensure_ws()
        assert len(instances) == 1

    def test_ensure_ws_noop_when_no_factory(self, wire: DhanWire) -> None:
        adapter = DhanStreamingAdapter(wire=wire)
        adapter._ensure_ws()
        assert adapter._ws is None


class TestSendSubscribeHelper:
    def test_send_subscribe_sends_correct_payload(self, wire: DhanWire) -> None:
        adapter, instances = _make_adapter(wire)
        adapter._ensure_ws()
        adapter._send_subscribe(InstrumentId.parse("NSE:RELIANCE"))
        msg = json.loads(instances[0].sent[0])
        assert msg["RequestCode"] == 15
        assert msg["InstrumentList"][0]["SecurityId"] == "2885"

    def test_send_subscribe_noop_when_ws_none(self, wire: DhanWire) -> None:
        adapter, _ = _make_adapter(wire)
        adapter._send_subscribe(InstrumentId.parse("NSE:RELIANCE"))
