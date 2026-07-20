"""Architecture ratchet — tick authority and EventBus drop observability."""

from __future__ import annotations

from decimal import Decimal

from infrastructure.event_bus.async_event_bus import AsyncEventBus
from infrastructure.event_bus.event_bus import EventBus, DomainEvent
from infrastructure.observability.event_metrics import EventMetrics
from runtime.tick_authority import (
    mark_stream_to_bus_wired,
    reset_tick_authority_for_tests,
    should_publish_tick_directly,
    tick_authority_status,
)


def test_tick_authority_starts_unwired() -> None:
    reset_tick_authority_for_tests()
    status = tick_authority_status()
    assert status.stream_to_bus is False
    assert status.live_bar_sink is False


def test_should_publish_tick_directly_false_when_orchestrator_wired() -> None:
    reset_tick_authority_for_tests()
    assert should_publish_tick_directly() is True
    mark_stream_to_bus_wired()
    assert should_publish_tick_directly() is False


def test_dhan_publisher_skips_eventbus_when_orchestrator_wired() -> None:
    from brokers.dhan.websocket.publish import MarketFeedPublisher

    reset_tick_authority_for_tests()
    mark_stream_to_bus_wired()
    published: list[str] = []

    class _Bus:
        def publish(self, event) -> None:
            published.append(str(event.event_type))

    pub = MarketFeedPublisher(_Bus(), lambda _s: 1, to_decimal=lambda x: Decimal(str(x)))
    pub.publish_tick({"symbol": "RELIANCE", "ltp": 2500.0})
    assert published == []


def test_upstox_skips_eventbus_when_orchestrator_wired() -> None:
    from types import SimpleNamespace

    from brokers.upstox.websocket.market_data_v3 import UpstoxMarketDataV3Multiplexer
    from domain import Quote

    reset_tick_authority_for_tests()
    mark_stream_to_bus_wired()
    published: list[str] = []

    class _Bus:
        def publish(self, event) -> None:
            published.append(str(event.event_type))

    svc = UpstoxMarketDataV3Multiplexer.__new__(UpstoxMarketDataV3Multiplexer)
    svc._event_bus = _Bus()
    frame = SimpleNamespace(
        payload=SimpleNamespace(
            instrument_key="NSE_EQ|RELIANCE",
            ltp=2500.0,
            symbol="RELIANCE",
        )
    )
    # Force valid quote path
    from unittest.mock import patch

    with patch(
        "brokers.upstox.websocket.market_data_v3.TickTranslatorAdapter.translate",
        return_value=Quote(symbol="RELIANCE", ltp=Decimal("2500")),
    ):
        svc._publish_tick_to_bus(frame)
    assert published == []


def test_async_event_bus_drop_increments_metrics() -> None:
    metrics = EventMetrics()
    sync = EventBus(metrics=metrics)
    async_bus = AsyncEventBus(sync, max_queue_size=1)
    async_bus.start()
    try:
        async_bus.publish(DomainEvent.now("TICK", {"ltp": 1}))
        async_bus.publish(DomainEvent.now("TICK", {"ltp": 2}))
        assert async_bus.dropped >= 1
        assert metrics.get("TICK", "async_dropped") >= 1
        assert metrics.get("AsyncEventBus", "dropped") >= 1
    finally:
        async_bus.stop()
