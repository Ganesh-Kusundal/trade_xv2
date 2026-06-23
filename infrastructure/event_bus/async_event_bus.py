"""Async EventBus with backpressure support.

This module provides an async-compatible EventBus that uses asyncio.Queue
for bounded capacity and backpressure handling. It maintains FIFO ordering
through a single dispatch worker and supports both sync and async handlers.

Key Features
------------
- **Backpressure**: Queue has bounded capacity (maxsize=N). When full,
  the publisher can BLOCK (default), DROP, or raise ERROR.
- **FIFO Ordering**: Single dispatch worker ensures events are processed
  in order.
- **Mixed Handler Support**: Handles both sync and async callbacks
  (uses asyncio.to_thread() for sync handlers).
- **DLQ Integration**: Reuses existing DeadLetterQueue for failed handlers.
- **Metrics Integration**: Reuses existing EventMetrics for observability.
- **Alerting Integration**: Optional AlertingEngine for threshold-based alerts.

Usage
-----
    async_bus = AsyncEventBus(
        maxsize=1000,
        backpressure_policy=BackpressurePolicy.BLOCK,
        event_log=event_log,
        metrics=metrics,
        dead_letter_queue=dlq,
        alerting_engine=alerting_engine,
    )
    
    # Subscribe handlers (sync or async)
    async_bus.subscribe("ORDER_PLACED", sync_handler)
    async_bus.subscribe("ORDER_PLACED", async_handler)
    
    # Publish events (async)
    await async_bus.publish("ORDER_PLACED", payload={"order_id": "123"})
    
    # Start/stop the dispatch worker
    await async_bus.start()
    await async_bus.stop()

Thread Safety
-------------
The AsyncEventBus is designed for async contexts. Do NOT mix sync publish()
calls with async publish() calls. Use the sync EventBus for purely synchronous
workflows.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import traceback
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any

from infrastructure.event_bus.event_bus import DomainEvent

if TYPE_CHECKING:
    from infrastructure.event_bus.dead_letter_queue import DeadLetterQueue
    from brokers.common.observability.event_metrics import EventMetrics
    from brokers.common.observability.alerting import AlertingEngine

logger = logging.getLogger(__name__)


class BackpressurePolicy(str, Enum):
    """Policy for handling queue-full scenarios.
    
    BLOCK: Publisher blocks until queue has space (default).
    DROP: Publisher drops the event and logs a warning.
    ERROR: Publisher raises QueueFull exception immediately.
    """
    
    BLOCK = "BLOCK"
    DROP = "DROP"
    ERROR = "ERROR"


@dataclass
class AsyncEventBusConfig:
    """Configuration for AsyncEventBus.
    
    Attributes
    ----------
    maxsize:
        Maximum queue size (bounded capacity for backpressure).
        Default 1000 events.
    backpressure_policy:
        Policy when queue is full. Default BLOCK.
    worker_name:
        Name for the dispatch worker (for logging).
    """
    
    maxsize: int = 1000
    backpressure_policy: BackpressurePolicy = BackpressurePolicy.BLOCK
    worker_name: str = "AsyncEventBusWorker"


class AsyncEventBus:
    """Async event bus with backpressure and FIFO ordering.
    
    Parameters
    ----------
    maxsize:
        Maximum queue size for backpressure (default 1000).
    backpressure_policy:
        Policy when queue is full (BLOCK, DROP, or ERROR).
    event_log:
        Optional event log for persistence.
    metrics:
        Optional metrics for observability.
    dead_letter_queue:
        Optional DLQ for failed handler invocations.
    alerting_engine:
        Optional AlertingEngine for threshold-based alerting.
        When provided, an asyncio task evaluates alert rules periodically.
    alerting_interval_seconds:
        Interval between alert evaluations (default 10 seconds).
    
    Event Processing
    ----------------
    Events are processed FIFO by a single dispatch worker. This ensures:
    - ORDER_PLACED always arrives before ORDER_UPDATED
    - TRADE always arrives before TRADE_APPLIED
    - No race conditions between handlers
    
    Handler Support
    ---------------
    Both sync and async handlers are supported:
    - Sync handlers run in executor (asyncio.to_thread)
    - Async handlers run directly in event loop
    - Handler failures go to DLQ, don't block other handlers
    
    Backpressure
    ------------
    When the queue is full:
    - BLOCK: publish() waits until space available (may block forever)
    - DROP: publish() returns immediately, event is lost
    - ERROR: publish() raises asyncio.QueueFull immediately
    
    Alerting
    --------
    When an alerting_engine is provided, a background asyncio task
    periodically evaluates alert rules. All metrics use timestamped
    counters to enable rate-based alerting.
    
    Usage
    -----
        bus = AsyncEventBus(maxsize=1000)
        bus.subscribe("ORDER_PLACED", my_handler)
        await bus.start()
        await bus.publish("ORDER_PLACED", {"order_id": "123"})
        await bus.stop()
    """
    
    def __init__(
        self,
        maxsize: int = 1000,
        backpressure_policy: BackpressurePolicy = BackpressurePolicy.BLOCK,
        event_log: Any | None = None,
        metrics: EventMetrics | None = None,
        dead_letter_queue: DeadLetterQueue | None = None,
        alerting_engine: AlertingEngine | None = None,
        alerting_interval_seconds: float = 10.0,
    ) -> None:
        self._queue: asyncio.Queue[tuple[str, dict[str, Any]] | None] = asyncio.Queue(
            maxsize=maxsize
        )
        self._config = AsyncEventBusConfig(
            maxsize=maxsize,
            backpressure_policy=backpressure_policy,
        )
        
        self._subscribers: dict[str, list[Callable]] = {}
        self._lock = threading.RLock()
        
        self._event_log = event_log
        self._metrics = metrics
        self._dead_letter_queue = dead_letter_queue
        self._alerting_engine = alerting_engine
        self._alerting_interval = alerting_interval_seconds
        
        self._worker_task: asyncio.Task | None = None
        self._alerting_task: asyncio.Task | None = None
        self._running = False
        self._event_count = 0
        self._error_count = 0
        self._dropped_count = 0
    
    @property
    def queue_size(self) -> int:
        """Current number of events in queue."""
        return self._queue.qsize()
    
    @property
    def is_full(self) -> bool:
        """True if queue is at capacity."""
        return self._queue.full()
    
    @property
    def is_running(self) -> bool:
        """True if dispatch worker is running."""
        return self._running
    
    @property
    def alerting_engine(self) -> AlertingEngine | None:
        """The alerting engine instance, if configured."""
        return self._alerting_engine
    
    async def start(self) -> None:
        """Start the dispatch worker and alerting task.
        
        Must be called before publish(). Creates a background task that
        continuously processes events from the queue.
        """
        if self._running:
            logger.warning("AsyncEventBus already running")
            return
        
        self._running = True
        self._worker_task = asyncio.create_task(
            self._dispatch_worker(),
            name=self._config.worker_name,
        )
        
        # Start alerting task if engine is provided.
        if self._alerting_engine is not None:
            self._alerting_task = asyncio.create_task(
                self._alerting_loop(),
                name="AsyncEventBus-Alerting",
            )
        
        logger.info(
            "AsyncEventBus started (maxsize=%d, policy=%s)",
            self._config.maxsize,
            self._config.backpressure_policy.value,
        )
    
    async def stop(self) -> None:
        """Stop the dispatch worker and alerting task.
        
        Waits for all pending events to be processed before returning.
        Call this during graceful shutdown.
        """
        if not self._running:
            return
        
        self._running = False
        
        # Send sentinel to stop the worker
        await self._queue.put(None)
        
        # Wait for worker to finish
        if self._worker_task is not None:
            try:
                await asyncio.wait_for(self._worker_task, timeout=10.0)
            except asyncio.TimeoutError:
                logger.error("AsyncEventBus worker did not stop within timeout")
                self._worker_task.cancel()
        
        # Wait for alerting task to finish
        if self._alerting_task is not None:
            self._alerting_task.cancel()
            try:
                await asyncio.wait_for(self._alerting_task, timeout=5.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
        
        logger.info(
            "AsyncEventBus stopped: events=%d, errors=%d, dropped=%d",
            self._event_count,
            self._error_count,
            self._dropped_count,
        )
    
    async def _alerting_loop(self) -> None:
        """Background loop that periodically evaluates alert rules."""
        try:
            while self._running:
                try:
                    if self._alerting_engine is not None:
                        alerts = self._alerting_engine.evaluate_all()
                        if alerts:
                            logger.info(
                                "AsyncEventBus alerting: %d alert(s) fired",
                                len(alerts),
                            )
                except Exception as exc:
                    logger.error(
                        "AsyncEventBus alerting evaluation failed: %s",
                        exc,
                        exc_info=True,
                    )
                await asyncio.sleep(self._alerting_interval)
        except asyncio.CancelledError:
            logger.info("AsyncEventBus alerting task cancelled")
            raise
    
    def subscribe(self, event_type: str, handler: Callable) -> None:
        """Subscribe a handler to an event type.
        
        Handler can be sync or async:
        - Sync: Will be run in executor via asyncio.to_thread()
        - Async: Will be awaited directly
        
        Parameters
        ----------
        event_type:
            Event type to subscribe to.
        handler:
            Callback function (sync or async).
        """
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            self._subscribers[event_type].append(handler)
            logger.debug("Subscribed handler to %s (total: %d)", 
                        event_type, len(self._subscribers[event_type]))
    
    def unsubscribe(self, event_type: str, handler: Callable) -> None:
        """Unsubscribe a handler from an event type.
        
        Parameters
        ----------
        event_type:
            Event type to unsubscribe from.
        handler:
            Callback function to remove.
        """
        with self._lock:
            if event_type in self._subscribers:
                try:
                    self._subscribers[event_type].remove(handler)
                    logger.debug("Unsubscribed handler from %s", event_type)
                except ValueError:
                    logger.warning("Handler not subscribed to %s", event_type)
    
    async def publish(
        self,
        event_type: str,
        payload: dict[str, Any],
        symbol: str | None = None,
        source: str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        """Publish an event to the bus.
        
        This is async and may block if backpressure policy is BLOCK and
        queue is full.
        
        Parameters
        ----------
        event_type:
            Type of the event.
        payload:
            Event payload dictionary.
        symbol:
            Optional symbol associated with the event.
        source:
            Optional source identifier.
        correlation_id:
            Optional correlation ID for tracing.
        
        Raises
        ------
        asyncio.QueueFull:
            If backpressure policy is ERROR and queue is full.
        """
        if not self._running:
            logger.warning("AsyncEventBus not running, dropping event")
            self._dropped_count += 1
            return
        
        event_data = (
            event_type,
            {
                "payload": payload,
                "symbol": symbol,
                "source": source,
                "correlation_id": correlation_id,
            },
        )
        
        try:
            if self._config.backpressure_policy == BackpressurePolicy.DROP:
                # Non-blocking put with immediate drop if full
                try:
                    self._queue.put_nowait(event_data)
                except asyncio.QueueFull:
                    self._dropped_count += 1
                    logger.warning(
                        "AsyncEventBus queue full, dropping event (type=%s)",
                        event_type,
                    )
            elif self._config.backpressure_policy == BackpressurePolicy.ERROR:
                # Non-blocking put with exception if full
                self._queue.put_nowait(event_data)
            else:
                # BLOCK (default): wait until space available
                await self._queue.put(event_data)
        
        except asyncio.QueueFull:
            logger.error(
                "AsyncEventBus queue full and policy=ERROR (type=%s, size=%d)",
                event_type,
                self._queue.qsize(),
            )
            raise
    
    async def _dispatch_worker(self) -> None:
        """Main dispatch loop - processes events FIFO.
        
        This runs as a background task and continuously pulls events from
        the queue, dispatching them to all subscribed handlers.
        """
        logger.info("AsyncEventBus dispatch worker started")
        
        while self._running:
            try:
                # Get next event (blocks until available)
                item = await self._queue.get()
                
                # Sentinel received: stop worker
                if item is None:
                    self._queue.task_done()
                    break
                
                event_type, event_data = item
                
                # Create DomainEvent
                event = DomainEvent.now(
                    event_type=event_type,
                    payload=event_data["payload"],
                    symbol=event_data.get("symbol"),
                    source=event_data.get("source"),
                    correlation_id=event_data.get("correlation_id"),
                )
                
                # Dispatch to handlers
                await self._dispatch_event(event)
                
                self._event_count += 1
                self._queue.task_done()
            
            except Exception as exc:
                logger.error(
                    "AsyncEventBus dispatch worker error: %s",
                    exc,
                    exc_info=True,
                )
                self._error_count += 1
        
        logger.info("AsyncEventBus dispatch worker stopped")
    
    async def _dispatch_event(self, event: DomainEvent) -> None:
        """Dispatch an event to all subscribed handlers.
        
        Parameters
        ----------
        event:
            DomainEvent to dispatch.
        """
        with self._lock:
            handlers = list(self._subscribers.get(event.event_type, []))
        
        if not handlers:
            return
        
        logger.debug(
            "Dispatching %s to %d handlers",
            event.event_type,
            len(handlers),
        )
        
        for handler in handlers:
            try:
                await self._invoke_handler(handler, event)
            except Exception as exc:
                self._handle_handler_failure(event, handler, exc)
    
    async def _invoke_handler(self, handler: Callable, event: DomainEvent) -> None:
        """Invoke a single handler (sync or async).
        
        Parameters
        ----------
        handler:
            Handler function to invoke.
        event:
            Event to pass to handler.
        """
        if asyncio.iscoroutinefunction(handler):
            # Async handler: await directly
            await handler(event)
        else:
            # Sync handler: run in executor
            await asyncio.to_thread(handler, event)
    
    def _handle_handler_failure(
        self,
        event: DomainEvent,
        handler: Callable,
        exc: Exception,
    ) -> None:
        """Handle a handler failure (log, metrics, DLQ).
        
        Parameters
        ----------
        event:
            Event that caused the failure.
        handler:
            Handler that failed.
        exc:
            Exception that was raised.
        """
        self._error_count += 1
        
        # Log the failure
        logger.warning(
            "AsyncEventBus handler failed: event=%s, handler=%s, error=%s",
            event.event_type,
            handler.__name__ if hasattr(handler, "__name__") else str(handler),
            exc,
            exc_info=True,
        )
        
        # Metrics (if available) - use timestamped counter for rate-based alerting
        if self._metrics is not None:
            self._metrics.add_timestamped_counter(
                event.event_type,
                f"handler_error:{type(exc).__name__}",
            )
        
        # DLQ (if available)
        if self._dead_letter_queue is not None:
            self._dead_letter_queue.push(event, exc)
    
    async def wait_for_completion(self, timeout: float | None = None) -> bool:
        """Wait for all queued events to be processed.
        
        Parameters
        ----------
        timeout:
            Maximum time to wait (seconds). None = wait forever.
        
        Returns
        -------
        bool:
            True if all events processed, False if timeout.
        """
        try:
            await asyncio.wait_for(self._queue.join(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False
    
    def get_stats(self) -> dict[str, Any]:
        """Get bus statistics.
        
        Returns
        -------
        dict:
            Statistics including event count, error count, queue size, etc.
        """
        return {
            "event_count": self._event_count,
            "error_count": self._error_count,
            "dropped_count": self._dropped_count,
            "queue_size": self._queue.qsize(),
            "is_full": self._queue.full(),
            "is_running": self._running,
            "subscriber_count": sum(
                len(handlers) for handlers in self._subscribers.values()
            ),
        }


__all__ = [
    "AsyncEventBus",
    "BackpressurePolicy",
]
