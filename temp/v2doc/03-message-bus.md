# 03 — Message Bus Design

## 1. Purpose

The `MessageBus` is the central nervous system of TradeXV2. Every inter-component
communication flows through it. This enables:

- **Decoupling** — Components never call each other directly
- **Zero-parity** — Same bus code for backtest, paper, and live
- **Observability** — Every message is traced, counted, and can be logged
- **Replay** — Events can be recorded and replayed for debugging

## 2. Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                        MessageBus                            │
│                                                              │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────┐  │
│  │  Sync       │  │  Async       │  │  Dead Letter       │  │
│  │  Dispatcher │  │  Dispatcher  │  │  Queue (DLQ)       │  │
│  └──────┬──────┘  └──────┬───────┘  └────────┬───────────┘  │
│         │                │                    │              │
│  ┌──────▼──────────────▼────────────────────▼───────────┐  │
│  │              Subscriber Registry                      │  │
│  │   {MessageType: [handler_fn, handler_fn, ...]}       │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              Metrics Collector                        │   │
│  │   messages_published, messages_delivered, latency     │   │
│  └──────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

## 3. Core Implementation

```python
# shared/messaging/message_bus.py

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable
from uuid import UUID

from domain.events.base import DomainEvent
from domain.ports.event_bus import EventBusPort, Subscription


logger = logging.getLogger(__name__)


@dataclass
class MessageBusMetrics:
    messages_published: int = 0
    messages_delivered: int = 0
    messages_failed: int = 0
    total_latency_ns: int = 0
    dlq_count: int = 0

    @property
    def avg_latency_ns(self) -> int:
        if self.messages_delivered == 0:
            return 0
        return self.total_latency_ns // self.messages_delivered


class MessageBus(EventBusPort):
    """
    In-process message bus for typed event dispatch.

    Supports both synchronous and asynchronous handlers.
    Failed deliveries go to a dead-letter queue for inspection.
    """

    def __init__(self, max_dlq_size: int = 1000) -> None:
        self._sync_subscribers: dict[type, list[Callable]] = defaultdict(list)
        self._async_subscribers: dict[type, list[Callable]] = defaultdict(list)
        self._metrics = MessageBusMetrics()
        self._dlq: list[DeadLetterEntry] = []
        self._max_dlq_size = max_dlq_size
        self._logger = logging.getLogger(f"{__name__}.MessageBus")

    @property
    def metrics(self) -> MessageBusMetrics:
        return self._metrics

    @property
    def dead_letters(self) -> list[DeadLetterEntry]:
        return list(self._dlq)

    # ── Publish ────────────────────────────────────────────────

    def publish(self, event: Any) -> None:
        """Publish event to all sync subscribers."""
        msg_type = type(event)
        self._metrics.messages_published += 1
        t0 = time.perf_counter_ns()

        for handler in self._sync_subscribers.get(msg_type, []):
            try:
                handler(event)
                self._metrics.messages_delivered += 1
            except Exception as exc:
                self._metrics.messages_failed += 1
                self._send_to_dlq(event, handler, exc)
                self._logger.exception(
                    "Handler %s failed for %s", handler, msg_type.__name__
                )

        elapsed = time.perf_counter_ns() - t0
        self._metrics.total_latency_ns += elapsed

    async def publish_async(self, event: Any) -> None:
        """Publish event to all async subscribers concurrently."""
        msg_type = type(event)
        self._metrics.messages_published += 1
        t0 = time.perf_counter_ns()

        handlers = self._async_subscribers.get(msg_type, [])
        if handlers:
            tasks = [self._safe_call(h, event, msg_type) for h in handlers]
            await asyncio.gather(*tasks)

        elapsed = time.perf_counter_ns() - t0
        self._metrics.total_latency_ns += elapsed

    # ── Subscribe ──────────────────────────────────────────────

    def subscribe(self, msg_type: type, handler: Callable) -> Subscription:
        """Register a sync handler for a message type."""
        self._sync_subscribers[msg_type].append(handler)
        return Subscription(msg_type=msg_type, handler=handler, _bus=self)

    def subscribe_async(self, msg_type: type, handler: Callable) -> Subscription:
        """Register an async handler for a message type."""
        self._async_subscribers[msg_type].append(handler)
        return Subscription(msg_type=msg_type, handler=handler, _bus=self)

    def _remove(self, msg_type: type, handler: Callable) -> None:
        """Remove a handler (called by Subscription.unsubscribe)."""
        try:
            self._sync_subscribers[msg_type].remove(handler)
        except ValueError:
            pass
        try:
            self._async_subscribers[msg_type].remove(handler)
        except ValueError:
            pass

    # ── DLQ ────────────────────────────────────────────────────

    def _send_to_dlq(self, event: Any, handler: Callable, error: Exception) -> None:
        entry = DeadLetterEntry(
            event=event,
            handler_name=f"{handler.__module__}.{handler.__qualname__}",
            error=error,
        )
        self._dlq.append(entry)
        if len(self._dlq) > self._max_dlq_size:
            self._dlq.pop(0)  # Drop oldest

    def replay_dlq(self) -> int:
        """Re-attempt delivery of dead-lettered events. Returns count retried."""
        retried = 0
        for entry in list(self._dlq):
            try:
                entry.event  # re-dispatch
                self.publish(entry.event)
                self._dlq.remove(entry)
                retried += 1
            except Exception:
                pass
        return retried

    # ── Internals ──────────────────────────────────────────────

    async def _safe_call(
        self, handler: Callable, event: Any, msg_type: type
    ) -> None:
        try:
            await handler(event)
            self._metrics.messages_delivered += 1
        except Exception as exc:
            self._metrics.messages_failed += 1
            self._send_to_dlq(event, handler, exc)
            self._logger.exception(
                "Async handler %s failed for %s", handler, msg_type.__name__
            )


@dataclass
class DeadLetterEntry:
    event: Any
    handler_name: str
    error: Exception
    timestamp: float = field(default_factory=time.time)
```

## 4. Message Types

### 4.1 Domain Events (Application → All)

| Event | Emitted By | Consumed By |
|---|---|---|
| `OrderPlaced` | ExecutionEngine | OrderManager, RiskManager, Analytics |
| `OrderAccepted` | OrderManager | StrategyEngine, Analytics |
| `OrderRejected` | OrderManager / RiskManager | StrategyEngine, Analytics |
| `OrderFilled` | OrderManager | PositionManager, StrategyEngine, RiskManager |
| `OrderCancelled` | OrderManager | StrategyEngine, Analytics |
| `PositionChanged` | PositionManager | RiskManager, StrategyEngine, Analytics |
| `RiskBreached` | RiskManager | KillSwitch, StrategyEngine, Analytics |
| `KillSwitchActivated` | KillSwitch | ExecutionEngine, Interface |

### 4.2 Commands (Interface → Application)

| Command | Source | Target |
|---|---|---|
| `PlaceOrderCommand` | Strategy / CLI / API | ExecutionEngine |
| `CancelOrderCommand` | Strategy / CLI / API | ExecutionEngine |
| `ModifyOrderCommand` | Strategy / CLI / API | ExecutionEngine |
| `MassStatusCommand` | CLI / API | ExecutionEngine |

### 4.3 System Events (Runtime → All)

| Event | Emitted By | Consumed By |
|---|---|---|
| `ComponentStarted` | LifecycleManager | HealthMonitor |
| `ComponentStopped` | LifecycleManager | HealthMonitor |
| `ComponentError` | LifecycleManager | HealthMonitor, AlertManager |
| `BrokerConnected` | BrokerGateway | StreamOrchestrator |
| `BrokerDisconnected` | BrokerGateway | StreamOrchestrator, AlertManager |
| `DataIngested` | DataCatalog | Analytics |

### 4.4 Market Data Events (Infrastructure → Application)

| Event | Emitted By | Consumed By |
|---|---|---|
| `TickReceived` | StreamingAdapter | StrategyEngine, LiveTickPipeline |
| `DepthUpdated` | StreamingAdapter | StrategyEngine |
| `HistoricalBarReady` | DataCatalog | StrategyEngine (backtest) |

## 5. Routing Rules

```
1. One-to-many:  A single event can have multiple subscribers.
2. Type-exact:   Subscribers receive only events of the exact type they subscribed to.
                 (No polymorphic dispatch — subscribe to OrderFilled, not DomainEvent.)
3. Sync-first:   Sync handlers run in publish() call, in registration order.
4. Async-separate: Async handlers run in publish_async(), concurrently via gather().
5. Fire-and-forget: Publishers do not wait for or receive results from handlers.
6. Failure-isolation: One handler failure does not prevent other handlers from running.
7. DLQ on failure: Failed deliveries are captured in the dead-letter queue.
```

## 6. Tracing & Correlation

Every event carries a `correlation_id: UUID`. The flow:

```
1. Strategy creates PlaceOrderCommand(correlation_id=uuid4())
2. ExecutionEngine publishes OrderPlaced(correlation_id=command.correlation_id)
3. OrderManager publishes OrderAccepted(correlation_id=same)
4. PositionManager publishes PositionChanged(correlation_id=same)
```

This allows tracing an entire order lifecycle across components using a single UUID.

```python
# Tracing helper
class CorrelationContext:
    """Thread-local correlation ID context."""

    _local = threading.local()

    @classmethod
    def set(cls, correlation_id: UUID) -> None:
        cls._local.current = correlation_id

    @classmethod
    def get(cls) -> UUID | None:
        return getattr(cls._local, "current", None)

    @classmethod
    def tag(cls, event: DomainEvent) -> DomainEvent:
        """Tag an event with the current correlation ID if not already tagged."""
        if event.correlation_id is None:
            cid = cls.get()
            if cid is not None:
                return event.with_correlation(cid)
        return event
```

## 7. Performance Characteristics

| Metric | Target | Rationale |
|---|---|---|
| Sync publish latency | < 1 µs per handler | In-process, no serialization |
| Async publish latency | < 10 µs per handler | asyncio.gather overhead |
| Memory per event | ~200 bytes | Frozen dataclass, no payload bloat |
| DLQ max size | 1000 entries | Prevent unbounded memory growth |
| Subscriber lookup | O(1) | Dict keyed by type |

## 8. Comparison with Alternatives

| Alternative | Rejected Because |
|---|---|
| Direct method calls | Tight coupling, no zero-parity, no audit trail |
| Redis pub/sub | External dependency, serialization overhead, not needed for in-process |
| RabbitMQ/Kafka | Overkill for single-process; adds ops burden |
| `asyncio.Queue` per component | No type routing, no multi-subscriber, harder to trace |
| Signal/slot (blinker) | No async support, no DLQ, no metrics |

## 9. Testing Strategy

```python
# tests/unit/test_message_bus.py

def test_sync_publish_delivers_to_all_handlers():
    bus = MessageBus()
    received = []
    bus.subscribe(OrderPlaced, lambda e: received.append(e))
    bus.subscribe(OrderPlaced, lambda e: received.append(e))
    bus.publish(OrderPlaced())
    assert len(received) == 2

def test_failed_handler_does_not_block_others():
    bus = MessageBus()
    received = []
    def bad_handler(e): raise ValueError("boom")
    bus.subscribe(OrderPlaced, bad_handler)
    bus.subscribe(OrderPlaced, lambda e: received.append(e))
    bus.publish(OrderPlaced())
    assert len(received) == 1
    assert bus.metrics.messages_failed == 1
    assert len(bus.dead_letters) == 1

def test_unsubscribe_stops_delivery():
    bus = MessageBus()
    received = []
    sub = bus.subscribe(OrderPlaced, lambda e: received.append(e))
    bus.publish(OrderPlaced())
    assert len(received) == 1
    sub.unsubscribe()
    bus.publish(OrderPlaced())
    assert len(received) == 1  # no new delivery
```
