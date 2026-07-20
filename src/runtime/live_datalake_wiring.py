"""Wire live TICK events into datalake bar persistence (MD-001 increment 2)."""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_wired_token: Any | None = None


def wire_live_bar_sink(event_bus: Any, *, lake_root: str | None = None) -> Any | None:
    """Subscribe to TICK events and merge closed 1m bars into the datalake.

    Opt-in via ``TRADEX_LIVE_BAR_SINK=1``. Idempotent — safe to call twice.
    Returns the :class:`LiveTickBarPipeline` when wired, else ``None``.
    """
    global _wired_token

    if os.getenv("TRADEX_LIVE_BAR_SINK", "0") != "1":
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

    token = event_bus.subscribe(EventType.TICK, _on_tick)
    _wired_token = pipeline
    logger.info("live_bar_sink wired (TRADEX_LIVE_BAR_SINK=1, timeframe=1m)")
    return pipeline
