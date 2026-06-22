"""WebSocket bridge from EventBus to WebSocket clients.

Subscribes to EventBus TICK/QUOTE events and pushes to WebSocket clients
with bounded queue and drop-oldest policy to prevent backpressure from
stalling the synchronous EventBus.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from brokers.common.event_bus import EventBus, DomainEvent

logger = logging.getLogger(__name__)


class MarketBridge:
    """Subscribes to EventBus TICK/QUOTE events and pushes to WebSocket clients.
    
    Uses bounded asyncio.Queue with drop-oldest policy to prevent backpressure
    from stalling the synchronous EventBus.
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
        
        # Subscribe to TICK and QUOTE events
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
        
        token_tick = self._event_bus.subscribe("TICK", on_event)
        token_quote = self._event_bus.subscribe("QUOTE", on_event)
        self._subscription_tokens = [token_tick, token_quote]
        
        # Launch dispatch loop
        self._task = asyncio.create_task(self._dispatch_loop())
        logger.info("MarketBridge started (queue_size=%d)", self._max_queue_size)
    
    async def stop(self):
        """Stop the bridge and unsubscribe."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
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
                        await self._manager.send_to_client(
                            connection_id,
                            {
                                "type": event.event_type.lower(),
                                "symbol": event.symbol,
                                **event.payload,
                            },
                        )
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("MarketBridge dispatch error: %s", exc)
