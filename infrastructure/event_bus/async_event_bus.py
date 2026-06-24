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
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import TYPE_CHECKING, Any

from domain.lifecycle_health import HealthState, HealthStatus
from infrastructure.event_bus.event_bus import DomainEvent
from infrastructure.lifecycle.lifecycle import build_health

if TYPE_CHECKING:
    from infrastructure.event_bus.dead_letter_queue import DeadLetterQueue
    from domain.ports.observability import AlertingEnginePort, EventMetricsPort

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
        metrics: EventMetricsPort | None = None,
        dead_letter_queue: DeadLetterQueue | None = None,
        alerting_engine: AlertingEnginePort | None = None,
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
        self._supervisor_task: asyncio.Task | None = None
        self._running = False
        self._event_count = 0
        self._error_count = 0
        self._dropped_count = 0
        
        # Supervisor state (A7: supervisor pattern)
        self._restart_count = 0
        self._consecutive_restarts = 0
        self._last_restart_at: datetime | None = None
        self._max_consecutive_restarts = 5
        self._restart_cooldown_seconds = 5.0
    
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
    def name(self) -> str:
        """ManagedService protocol: service name for LifecycleManager."""
        return "AsyncEventBus"
    
    @property
    def alerting_engine(self) -> AlertingEnginePort | None:
        """The alerting engine instance, if configured."""
        return self._alerting_engine
    
    async def start(self) -> None:
        """Start the dispatch worker, supervisor, and alerting task.
        
        Must be called before publish(). Creates a background task that
        continuously processes events from the queue, monitored by a
        supervisor task that restarts the worker on crash.
        """
        if self._running:
            logger.warning("AsyncEventBus already running")
            return
        
        # Reset supervisor state
        self._restart_count = 0
        self._consecutive_restarts = 0
        self._last_restart_at = None
        
        self._running = True
        
        # Create worker task FIRST
        self._worker_task = asyncio.create_task(
            self._dispatch_worker(),
            name=self._config.worker_name,
        )
        
        # Create supervisor task (monitors worker)
        self._supervisor_task = asyncio.create_task(
            self._supervisor_loop(),
            name="AsyncEventBus-Supervisor",
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
        """Stop the dispatch worker, supervisor, and alerting task.
        
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
        
        # Cancel supervisor task
        if self._supervisor_task is not None:
            self._supervisor_task.cancel()
            try:
                await asyncio.wait_for(self._supervisor_task, timeout=5.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
        
        # Wait for alerting task to finish
        if self._alerting_task is not None:
            self._alerting_task.cancel()
            try:
                await asyncio.wait_for(self._alerting_task, timeout=5.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
        
        logger.info(
            "AsyncEventBus stopped: events=%d, errors=%d, dropped=%d, restarts=%d",
            self._event_count,
            self._error_count,
            self._dropped_count,
            self._restart_count,
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
        
        A7 Fix: Wrapped in outer try-except so supervisor can detect
        crashes outside the inner event-processing loop.
        """
        logger.info("AsyncEventBus dispatch worker started")
        
        try:
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
                    
                    # P2: Persist FIRST (crash recovery) — mirror sync bus pattern
                    if self._event_log is not None:
                        try:
                            self._event_log.append(event)
                        except Exception as log_exc:
                            logger.error(
                                "AsyncEventBus: failed to persist %s to log: %s",
                                event.event_type,
                                log_exc,
                                exc_info=True,
                            )
                            if self._metrics is not None:
                                self._metrics.add_timestamped_counter(
                                    event.event_type, f"log_error:{type(log_exc).__name__}"
                                )
                            if self._dead_letter_queue is not None:
                                import traceback as _tb
                                self._dead_letter_queue.push_failure(
                                    event=event,
                                    handler_id="<event_log>",
                                    exc=log_exc,
                                    traceback=_tb.format_exc(),
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
        except asyncio.CancelledError:
            # Clean shutdown requested
            logger.info("AsyncEventBus dispatch worker cancelled")
            raise
        except Exception as exc:
            # CRITICAL: Worker crash outside inner loop - supervisor will restart
            logger.critical(
                "AsyncEventBus dispatch worker CRASH: %s",
                exc,
                exc_info=True,
            )
            raise
        finally:
            logger.info("AsyncEventBus dispatch worker stopped")
    
    # ── Supervisor Pattern (A7 Fix) ──────────────────────────────────────
    
    async def _supervisor_loop(self) -> None:
        """Monitor dispatch worker and restart on crash.
        
        Implements exponential backoff with crash-loop detection:
        - Backoff: 0.1s → 5s max
        - Crash loop: 5 restarts within 5s window → suppress and log CRITICAL
        
        A7 Fix: Eliminates single point of failure in dispatch worker.
        """
        logger.info("AsyncEventBus supervisor started")
        
        while self._running:
            try:
                # Wait for worker task to complete (crash or stop)
                if self._worker_task is not None:
                    try:
                        await self._worker_task
                    except Exception:
                        # Worker crashed - exception is expected, we'll restart below
                        pass
                
                # Worker completed - check if we should restart
                if not self._running:
                    # Clean shutdown requested
                    logger.info("AsyncEventBus supervisor: clean shutdown, not restarting")
                    break
                
                # Worker crashed - decide whether to restart
                now = datetime.now(timezone.utc)
                
                if self._should_suppress_restart(now):
                    logger.critical(
                        "AsyncEventBus supervisor: CRASH LOOP DETECTED - "
                        "%d restarts in %.1fs window, suppressing restart",
                        self._consecutive_restarts,
                        self._restart_cooldown_seconds,
                    )
                    # Wait for stop or external intervention
                    while self._running:
                        await asyncio.sleep(1.0)
                    break
                
                # Calculate backoff delay
                delay = self._calculate_restart_delay()
                logger.warning(
                    "AsyncEventBus supervisor: worker crashed, restarting in %.2fs "
                    "(restart #%d, consecutive #%d)",
                    delay,
                    self._restart_count + 1,
                    self._consecutive_restarts + 1,
                )
                
                await asyncio.sleep(delay)
                
                if not self._running:
                    break
                
                # Restart worker
                self._restart_count += 1
                self._consecutive_restarts += 1
                self._last_restart_at = now
                
                logger.info(
                    "AsyncEventBus supervisor: restarting worker (attempt #%d)",
                    self._restart_count,
                )
                
                self._worker_task = asyncio.create_task(
                    self._dispatch_worker(),
                    name=f"{self._config.worker_name}-restart-{self._restart_count}",
                )
            
            except asyncio.CancelledError:
                logger.info("AsyncEventBus supervisor cancelled")
                raise
            except Exception as exc:
                logger.critical(
                    "AsyncEventBus supervisor error: %s",
                    exc,
                    exc_info=True,
                )
                # Don't let supervisor crash - wait and retry
                await asyncio.sleep(1.0)
        
        logger.info("AsyncEventBus supervisor stopped")
    
    def _should_suppress_restart(self, now: datetime) -> bool:
        """Check if we should suppress restart due to crash loop.
        
        Parameters
        ----------
        now:
            Current timestamp.
        
        Returns
        -------
        bool:
            True if restart should be suppressed (crash loop detected).
        """
        if self._consecutive_restarts < self._max_consecutive_restarts:
            return False
        
        if self._last_restart_at is None:
            return False
        
        # Check if we're still within the cooldown window
        time_since_last = (now - self._last_restart_at).total_seconds()
        return time_since_last < self._restart_cooldown_seconds
    
    def _calculate_restart_delay(self) -> float:
        """Calculate exponential backoff delay for restart.
        
        Returns
        -------
        float:
            Delay in seconds (0.1s → 5.0s max).
        """
        # Exponential backoff: 0.1 * 2^(consecutive_restarts)
        delay = 0.1 * (2 ** self._consecutive_restarts)
        return min(delay, 5.0)  # Cap at 5 seconds
    
    # ── Health Check (ManagedService protocol) ───────────────────────────
    
    def health(self) -> HealthStatus:
        """Return a point-in-time health snapshot.
        
        Implements ManagedService protocol for LifecycleManager integration.
        
        Returns
        -------
        HealthStatus:
            - STOPPED: Not running
            - HEALTHY: Running, no recent restarts
            - DEGRADED: Running but has restarted recently
            - UNHEALTHY: Running but in crash loop (suppressed)
            - FAILED: Supervisor or worker task not alive
        """
        if not self._running:
            return build_health(
                self.name,
                HealthState.STOPPED,
                detail="not running",
                metrics=self._health_metrics(),
            )
        
        # Check if tasks are alive
        supervisor_alive = (
            self._supervisor_task is not None
            and not self._supervisor_task.done()
        )
        worker_alive = (
            self._worker_task is not None
            and not self._worker_task.done()
        )
        
        if not supervisor_alive or not worker_alive:
            return build_health(
                self.name,
                HealthState.FAILED,
                detail=f"supervisor_alive={supervisor_alive}, worker_alive={worker_alive}",
                metrics=self._health_metrics(),
            )
        
        # Check for crash loop
        if self._consecutive_restarts >= self._max_consecutive_restarts:
            return build_health(
                self.name,
                HealthState.UNHEALTHY,
                detail=f"crash loop detected ({self._consecutive_restarts} consecutive restarts)",
                metrics=self._health_metrics(),
            )
        
        # Check if degraded (recent restarts)
        if self._consecutive_restarts > 0:
            return build_health(
                self.name,
                HealthState.DEGRADED,
                detail=f"running with {self._consecutive_restarts} consecutive restart(s)",
                metrics=self._health_metrics(),
            )
        
        # Healthy
        return build_health(
            self.name,
            HealthState.HEALTHY,
            detail="running normally",
            metrics=self._health_metrics(),
        )
    
    def _health_metrics(self) -> dict[str, Any]:
        """Collect metrics for health snapshot."""
        return {
            "restart_count": self._restart_count,
            "consecutive_restarts": self._consecutive_restarts,
            "queue_size": self._queue.qsize(),
            "event_count": self._event_count,
            "error_count": self._error_count,
            "dropped_count": self._dropped_count,
            "is_running": self._running,
            "supervisor_task_alive": (
                self._supervisor_task is not None
                and not self._supervisor_task.done()
            ),
            "worker_task_alive": (
                self._worker_task is not None
                and not self._worker_task.done()
            ),
        }
    
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
            import traceback as _tb
            handler_id = handler.__name__ if hasattr(handler, "__name__") else str(handler)
            self._dead_letter_queue.push_failure(
                event=event,
                handler_id=handler_id,
                exc=exc,
                traceback=_tb.format_exc(),
            )
    
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
