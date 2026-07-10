"""Tests for api.ws.bridge — MarketBridge event bridging."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from interface.api.ws.bridge import _BRIDGED_EVENTS, MarketBridge
from infrastructure.event_bus import DomainEvent


def _make_event(event_type="QUOTE", symbol="RELIANCE", payload=None):
    return DomainEvent(
        event_type=event_type,
        symbol=symbol,
        payload=payload or {"ltp": 100.0},
        timestamp=datetime.now(timezone.utc),
    )


class TestFormatMessage:
    def test_quote_event(self):
        bridge = MarketBridge(event_bus=MagicMock(), connection_manager=MagicMock())
        event = _make_event("QUOTE", "RELIANCE", {"ltp": 100.0})
        msg = bridge._format_message(event)
        assert msg["type"] == "quote"
        assert msg["symbol"] == "RELIANCE"
        assert msg["ltp"] == 100.0

    def test_depth_event(self):
        bridge = MarketBridge(event_bus=MagicMock(), connection_manager=MagicMock())
        event = _make_event("DEPTH", "RELIANCE", {"depth": {"bids": [], "asks": [], "depth_type": "DEPTH_5"}})
        msg = bridge._format_message(event)
        assert msg["type"] == "depth"
        assert "bids" in msg
        assert "asks" in msg

    def test_tick_event(self):
        bridge = MarketBridge(event_bus=MagicMock(), connection_manager=MagicMock())
        event = _make_event("TICK", "INFY", {"ltp": 1500.0})
        msg = bridge._format_message(event)
        assert msg["type"] == "tick"
        assert msg["symbol"] == "INFY"


class TestBridgedEvents:
    def test_includes_quote(self):
        assert "QUOTE" in _BRIDGED_EVENTS

    def test_includes_depth(self):
        assert "DEPTH" in _BRIDGED_EVENTS

    def test_includes_trade(self):
        assert "TRADE" in _BRIDGED_EVENTS


class TestStartStop:
    @pytest.mark.asyncio
    async def test_start_subscribes_to_events(self):
        bus = MagicMock()
        bus.subscribe.return_value = "token-1"
        manager = MagicMock()
        bridge = MarketBridge(event_bus=bus, connection_manager=manager)

        await bridge.start()
        assert bus.subscribe.call_count == len(_BRIDGED_EVENTS)
        await bridge.stop()

    @pytest.mark.asyncio
    async def test_stop_unsubscribes(self):
        bus = MagicMock()
        bus.subscribe.return_value = "token-1"
        manager = MagicMock()
        bridge = MarketBridge(event_bus=bus, connection_manager=manager)

        await bridge.start()
        await bridge.stop()
        assert bus.unsubscribe.call_count == len(_BRIDGED_EVENTS)


class TestDropOldest:
    def test_queue_full_drops_oldest(self):
        bus = MagicMock()
        manager = MagicMock()
        bridge = MarketBridge(event_bus=bus, connection_manager=manager, max_queue_size=2)
        bridge._queue = asyncio.Queue(maxsize=2)

        bridge._queue.put_nowait("old-event-1")
        bridge._queue.put_nowait("old-event-2")

        on_event = None
        def capture_subscribe(event_type, callback):
            nonlocal on_event
            if on_event is None:
                on_event = callback
            return f"token-{event_type}"

        bus.subscribe.side_effect = capture_subscribe

        for event_type in _BRIDGED_EVENTS:
            bus.subscribe(event_type, MagicMock())

        assert on_event is not None
        new_event = _make_event()
        on_event(new_event)

        assert bridge._queue.qsize() == 2
