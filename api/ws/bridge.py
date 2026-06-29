"""WebSocket bridge from EventBus to WebSocket clients.

Subscribes to EventBus TICK/QUOTE/DEPTH/TRADE events and pushes to
WebSocket clients with bounded queue and drop-oldest policy to prevent
backpressure from stalling the synchronous EventBus.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

from infrastructure.event_bus import DomainEvent, EventBus

logger = logging.getLogger(__name__)

# EventBus event types to bridge to WebSocket clients
_BRIDGED_EVENTS = ("TICK", "QUOTE", "DEPTH", "DEPTH_20", "DEPTH_200", "TRADE")


class MarketBridge:
    """Subscribes to EventBus market events and pushes to WebSocket clients.

    Bridges TICK, QUOTE, DEPTH, DEPTH_20, and TRADE events to connected
    WebSocket clients. Uses bounded asyncio.Queue with drop-oldest policy
    to prevent backpressure from stalling the synchronous EventBus.
    """

    def __init__(self, event_bus: EventBus, connection_manager: Any, max_queue_size: int = 1000):
        self._event_bus = event_bus
        self._manager = connection_manager
        self._max_queue_size = max_queue_size
        self._queue: asyncio.Queue | None = None
        self._task: asyncio.Task | None = None
        self._subscription_tokens: list[str] = []

    async def start(self):
        """Start the bridge: subscribe to bus and launch dispatch loop."""
        self._queue = asyncio.Queue(maxsize=self._max_queue_size)

        # Subscribe to all bridged event types
        def on_event(event: DomainEvent):
            try:
                self._queue.put_nowait(event)
            except asyncio.QueueFull:
                # Drop oldest — better than stalling the bus
                logger.warning("MarketBridge queue full, dropping event")
                try:
                    self._queue.get_nowait()
                    self._queue.put_nowait(event)
                except asyncio.QueueFull:
                    pass  # Should not happen

        for event_type in _BRIDGED_EVENTS:
            token = self._event_bus.subscribe(event_type, on_event)
            self._subscription_tokens.append(token)

        # Launch dispatch loop
        self._task = asyncio.create_task(self._dispatch_loop())
        logger.info(
            "MarketBridge started (queue_size=%d, events=%s)",
            self._max_queue_size,
            ",".join(_BRIDGED_EVENTS),
        )

    async def stop(self):
        """Stop the bridge and unsubscribe."""
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

        for token in self._subscription_tokens:
            self._event_bus.unsubscribe(token)

        logger.info("MarketBridge stopped")

    async def _dispatch_loop(self):
        """Dispatch events from queue to WebSocket clients."""
        while True:
            try:
                event = await self._queue.get()

                # Broadcast to all subscribed connections
                for connection_id, symbols in self._manager.subscriptions.items():
                    if event.symbol in symbols or not symbols:
                        msg = self._format_message(event)
                        await self._manager.send_to_client(connection_id, msg)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("MarketBridge dispatch error: %s", exc)

    def _format_message(self, event: DomainEvent) -> dict:
        """Format a domain event into a WebSocket message dict."""
        from api.routers.live.serialize import serialize_value

        event_type = event.event_type.lower()
        msg_type = (
            "depth"
            if event.event_type in ("DEPTH", "DEPTH_20", "DEPTH_200")
            else event_type
        )
        symbol = event.symbol
        if not symbol and event.event_type in ("DEPTH", "DEPTH_20", "DEPTH_200"):
            depth_obj = event.payload.get("depth")
            if depth_obj is not None and getattr(depth_obj, "symbol", None):
                symbol = depth_obj.symbol

        base = {
            "type": msg_type,
            "symbol": symbol,
        }

        # Handle DEPTH events — flatten MarketDepth into bids/asks arrays
        if event.event_type in ("DEPTH", "DEPTH_20", "DEPTH_200"):
            depth = event.payload.get("depth")
            if depth is not None:
                from dataclasses import asdict

                depth_dict = asdict(depth) if hasattr(depth, "__dataclass_fields__") else depth
                base["bids"] = serialize_value(depth_dict.get("bids", []))
                base["asks"] = serialize_value(depth_dict.get("asks", []))
                base["depth_type"] = depth_dict.get("depth_type", "DEPTH_5")
                return base

        # All other events — forward payload directly
        base.update(event.payload)
        return base
