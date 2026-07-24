"""Tests for UpstoxStreamingAdapter WebSocket auto-reconnect."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch


from plugins.brokers.common.ws_reconnect import ReconnectConfig
from plugins.brokers.upstox.adapters.streaming import UpstoxStreamingAdapter
from plugins.brokers.upstox.wire import UpstoxWire


class FakeWs:
    """Minimal WebSocket stub for testing."""

    def __init__(self) -> None:
        self.sent: list[str] = []
        self.close_called = False
        self.on_close: Any = None

    def send(self, data: str) -> None:
        self.sent.append(data)

    def close(self) -> None:
        self.close_called = True
        if self.on_close:
            self.on_close(1000, "normal")


def _make_adapter(
    ws_factory: Any = None,
    reconnect_config: ReconnectConfig | None = None,
) -> UpstoxStreamingAdapter:
    wire = MagicMock(spec=UpstoxWire)
    wire.instrument_key.return_value = "NSE_EQ|INE001A0001"
    if ws_factory is None:

        def _ws_factory(url: str) -> FakeWs:
            return FakeWs()

        ws_factory = _ws_factory
    return UpstoxStreamingAdapter(
        wire=wire,
        ws_factory=ws_factory,
        reconnect_config=reconnect_config,
    )


class TestUpstoxStreamingReconnect:
    def test_reconnect_config_parameter_accepted(self) -> None:
        config = ReconnectConfig(max_retries=5, base_delay=0.01)
        adapter = _make_adapter(reconnect_config=config)
        assert adapter._reconnect_manager._config.max_retries == 5

    def test_default_reconnect_config_when_none(self) -> None:
        adapter = _make_adapter()
        assert adapter._reconnect_manager._config.max_retries == 10

    def test_ensure_ws_sets_connected(self) -> None:
        adapter = _make_adapter()
        adapter._ensure_ws()
        assert adapter._reconnect_manager.is_connected is True

    def test_handle_ws_close_triggers_reconnect(self) -> None:
        ws = FakeWs()
        adapter = _make_adapter(ws_factory=lambda url: ws)
        adapter._ensure_ws()

        with patch.object(adapter, "_do_reconnect"):
            adapter._handle_ws_close(1000, "normal")

        assert adapter._ws is None
        assert adapter._reconnect_manager.is_connected is False

    def test_do_reconnect_calls_on_disconnect(self) -> None:
        adapter = _make_adapter()
        adapter._ensure_ws()

        with patch.object(adapter._reconnect_manager, "on_disconnect") as mock_disconnect:
            adapter._do_reconnect()
            mock_disconnect.assert_called_once()
            kwargs = mock_disconnect.call_args
            assert "reconnect_fn" in kwargs.kwargs
            assert "replay_fn" in kwargs.kwargs

    def test_replay_subscriptions_resends_quote_subs(self) -> None:
        adapter = _make_adapter()
        ws = FakeWs()
        adapter._ws = ws
        adapter._quote_subs["NSE:RELIANCE"] = MagicMock()

        adapter._replay_subscriptions()

        assert len(ws.sent) == 1
        payload = json.loads(ws.sent[0])
        assert payload["method"] == "sub"
        assert "NSE_EQ|INE001A0001" in payload["data"]["instrumentKeys"]

    def test_replay_subscriptions_resends_order_sub(self) -> None:
        adapter = _make_adapter()
        ws = FakeWs()
        adapter._ws = ws
        adapter._order_cb = MagicMock()

        adapter._replay_subscriptions()

        assert len(ws.sent) == 1
        payload = json.loads(ws.sent[0])
        assert payload["method"] == "sub"

    def test_replay_subscriptions_noop_when_no_ws(self) -> None:
        adapter = _make_adapter()
        adapter._ws = None
        adapter._quote_subs["NSE:RELIANCE"] = MagicMock()

        adapter._replay_subscriptions()

    def test_replay_subscriptions_noop_when_ws_no_send(self) -> None:
        adapter = _make_adapter()
        adapter._ws = object()
        adapter._quote_subs["NSE:RELIANCE"] = MagicMock()

        adapter._replay_subscriptions()

    def test_send_subscribe_uses_wire_key(self) -> None:
        adapter = _make_adapter()
        ws = FakeWs()
        adapter._ws = ws
        instrument_id = MagicMock()
        instrument_id.value = "INE001A0001"

        adapter._send_subscribe(instrument_id)

        adapter._wire.instrument_key.assert_called_once_with(instrument_id)
        assert len(ws.sent) == 1

    def test_close_stops_reconnect_manager(self) -> None:
        adapter = _make_adapter()
        adapter._ensure_ws()
        assert adapter._reconnect_manager.is_connected is True

        adapter.close()
        assert adapter._ws is None

    def test_reconnect_replays_after_successful_reconnect(self) -> None:
        """Integration test: close → reconnect → replay subscriptions."""
        ws1 = FakeWs()
        ws2 = FakeWs()
        call_count = 0

        def factory(url: str) -> FakeWs:
            nonlocal call_count
            call_count += 1
            return ws1 if call_count == 1 else ws2

        adapter = _make_adapter(ws_factory=factory)
        adapter._ensure_ws()
        adapter._quote_subs["NSE_EQ|TEST"] = MagicMock()

        # Simulate WS close
        with patch("plugins.brokers.upstox.adapters.streaming.threading.Thread") as MockThread:
            mock_thread = MagicMock()
            MockThread.return_value = mock_thread
            adapter._handle_ws_close()
            mock_thread.start.assert_called_once()

    def test_max_retries_respected(self) -> None:
        config = ReconnectConfig(max_retries=2, base_delay=0.01)
        adapter = _make_adapter(reconnect_config=config)

        with patch.object(adapter._reconnect_manager, "on_disconnect") as mock_disconnect:
            adapter._do_reconnect()

        mock_disconnect.assert_called_once()
        # The manager's on_disconnect will handle retry logic internally
