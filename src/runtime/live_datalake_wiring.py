"""Wire live TICK events into datalake bar persistence (MD-001)."""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_wired_token: Any | None = None
_stream_wired: bool = False
_live_sink: Any | None = None
_live_pipeline: Any | None = None


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


_paper_fill_wired: bool = False


def wire_paper_limit_fills(event_bus: Any, paper_orders: Any) -> None:
    """Subscribe paper resting limits to EventBus TICK for zero-parity fills."""
    global _paper_fill_wired
    if event_bus is None or paper_orders is None or _paper_fill_wired:
        return

    from decimal import Decimal

    from domain.constants import DEFAULT_EXCHANGE
    from infrastructure.event_bus import EventType

    def _on_tick(event) -> None:
        payload = getattr(event, "payload", None) or {}
        ltp = payload.get("ltp")
        quote = payload.get("quote")
        if ltp is None and quote is not None:
            ltp = getattr(quote, "ltp", None)
        if ltp is None:
            return

        symbol = getattr(event, "symbol", None)
        if symbol is None and quote is not None:
            symbol = getattr(quote, "symbol", None)
        if not symbol:
            return

        exchange = payload.get("exchange") or DEFAULT_EXCHANGE
        ts = payload.get("timestamp")
        try:
            paper_orders.try_fill_on_quote(symbol, exchange, Decimal(str(ltp)), ts)
        except Exception as exc:
            logger.warning(
                "paper_limit_fill_tick_failed",
                extra={"symbol": symbol, "exc_type": type(exc).__name__},
            )

    event_bus.subscribe(EventType.TICK, _on_tick)
    _paper_fill_wired = True
    logger.info("paper_limit_fills wired to EventBus TICK")


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
    global _wired_token, _live_sink, _live_pipeline

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
    _live_sink = sink
    _live_pipeline = pipeline

    def _on_tick(event) -> None:
        tick = market_tick_from_event(event)
        if tick is not None:
            pipeline.on_tick(tick)

    from runtime.tick_authority import mark_live_bar_sink_wired

    event_bus.subscribe(EventType.TICK, _on_tick)
    _wired_token = pipeline
    mark_live_bar_sink_wired()
    logger.info("live_bar_sink wired (default-on; TRADEX_LIVE_BAR_SINK=0 to disable, timeframe=1m)")
    return pipeline


def attach_orchestrator_gap_fill(stream_orchestrator: Any) -> None:
    """Route gap-reconciled bars into the live bar sink when wired."""
    if stream_orchestrator is None or _live_sink is None:
        return
    attach = getattr(stream_orchestrator, "attach_reconciled_bar_handler", None)
    if callable(attach):
        attach(_live_sink.write_bar)
        logger.info("gap_reconcile wired to LiveBarSink via StreamOrchestrator")


def flush_live_bar_pipeline() -> None:
    """Flush in-progress bars and drain async parquet writes on shutdown."""
    if _live_pipeline is not None:
        _live_pipeline.flush()
    if _live_sink is not None:
        _live_sink.flush()
