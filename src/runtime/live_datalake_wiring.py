"""Wire live TICK events into datalake bar persistence (MD-001)."""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_wired_token: Any | None = None
_stream_wired: bool = False


def _publish_tick(event_bus: Any, tick) -> None:
    from domain.entities.market import Quote
    from domain.events.types import DomainEvent
    from infrastructure.event_bus import EventType

    quote = Quote(
        symbol=tick.instrument.symbol,
        ltp=tick.ltp,
        volume=tick.volume,
        timestamp=tick.event_time,
    )
    from runtime.tick_authority import record_tick_publish

    event_bus.publish(
        DomainEvent(
            event_type=EventType.TICK,
            symbol=tick.instrument.symbol,
            source=tick.broker_id or "stream",
            payload={
                "quote": quote,
                "exchange": tick.instrument.exchange,
                "ltp": tick.ltp,
                "volume": tick.volume,
                "timestamp": tick.event_time,
            },
        )
    )
    record_tick_publish()


def wire_stream_orchestrator_ticks(
    stream_orchestrator: Any,
    event_bus: Any,
) -> None:
    """Publish normalized stream ticks onto the EventBus TICK contract."""
    global _stream_wired
    if stream_orchestrator is None or event_bus is None or _stream_wired:
        return
    from runtime.tick_authority import mark_stream_to_bus_wired

    stream_orchestrator._tick_hook = lambda tick: _publish_tick(event_bus, tick)
    stream_orchestrator._tick_router._tick_hook = stream_orchestrator._tick_hook
    _stream_wired = True
    mark_stream_to_bus_wired()
    logger.info("stream_orchestrator wired to EventBus TICK (MD-001)")


def wire_live_bar_sink(event_bus: Any, *, lake_root: str | None = None) -> Any | None:
    """Subscribe to TICK events and merge closed 1m bars into the datalake.

    Opt-in via ``TRADEX_LIVE_BAR_SINK=1``. Idempotent — safe to call twice.
    Returns the :class:`LiveTickBarPipeline` when wired, else ``None``.
    """
    global _wired_token

    if os.getenv("TRADEX_LIVE_BAR_SINK", "1") == "0":
        return None
    if event_bus is None:
        return None
    if _wired_token is not None:
        return _wired_token

    from application.streaming.live_tick_pipeline import (
        LiveTickBarPipeline,
        market_tick_from_event,
    )
    from datalake.ingestion.live_bar_sink import LiveBarSink
    from infrastructure.event_bus import EventType

    sink = LiveBarSink(root=lake_root)
    pipeline = LiveTickBarPipeline(on_bar=sink.write_bar, timeframes=("1m",))

    def _on_tick(event) -> None:
        tick = market_tick_from_event(event)
        if tick is not None:
            pipeline.on_tick(tick)

    from runtime.tick_authority import mark_live_bar_sink_wired

    token = event_bus.subscribe(EventType.TICK, _on_tick)
    _wired_token = pipeline
    mark_live_bar_sink_wired()
    logger.info("live_bar_sink wired (default-on; TRADEX_LIVE_BAR_SINK=0 to disable, timeframe=1m)")
    return pipeline
