"""In-process typed MessageBus with metrics and dead-letter queue."""

from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Callable

from infrastructure.message_bus.log import MessageLog

MessageHandler = Callable[[Any], Any]


@dataclass(frozen=True)
class DeadLetter:
    original_message: object
    handler: str
    error: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class MessageBusMetrics:
    messages_published: int = 0
    messages_delivered: int = 0
    messages_failed: int = 0
    dlq_count: int = 0
    avg_latency_ns: int = 0


@dataclass
class Subscription:
    msg_type: type
    handler: MessageHandler
    _bus: MessageBus | None = field(default=None, repr=False, compare=False)

    def cancel(self) -> None:
        if self._bus is not None:
            self._bus.unsubscribe(self)


class MessageBus:
    def __init__(
        self,
        max_queue_size: int = 10_000,
        message_log: MessageLog | None = None,
    ) -> None:
        self.max_queue_size = max_queue_size
        self._message_log = message_log
        self._subscribers: dict[type, list[Subscription]] = defaultdict(list)
        self._inflight = 0
        self.metrics = MessageBusMetrics()
        self.dead_letters: deque[DeadLetter] = deque()
        self._stopped = False

    def subscribe(self, msg_type: type, handler: MessageHandler) -> Subscription:
        sub = Subscription(msg_type=msg_type, handler=handler, _bus=self)
        self._subscribers[msg_type].append(sub)
        return sub

    def unsubscribe(self, subscription: Subscription) -> None:
        subs = self._subscribers.get(subscription.msg_type)
        if not subs:
            return
        try:
            subs.remove(subscription)
        except ValueError:
            return

    def publish(self, message: object) -> None:
        if self._inflight >= self.max_queue_size:
            raise RuntimeError(
                f"backpressure: queue full (max_queue_size={self.max_queue_size})"
            )
        self._inflight += 1
        try:
            self.metrics.messages_published += 1
            if self._message_log is not None:
                self._message_log.append(message)
            for sub in list(self._subscribers.get(type(message), ())):
                self._deliver(sub, message)
        finally:
            self._inflight -= 1

    async def publish_async(self, message: object) -> None:
        """Optional async publish — runs sync dispatch in a thread."""
        await asyncio.to_thread(self.publish, message)

    def _deliver(self, sub: Subscription, message: object) -> None:
        try:
            sub.handler(message)
            self.metrics.messages_delivered += 1
        except Exception as exc:
            self.metrics.messages_failed += 1
            self.metrics.dlq_count += 1
            self.dead_letters.append(
                DeadLetter(
                    original_message=message,
                    handler=getattr(sub.handler, "__qualname__", repr(sub.handler)),
                    error=str(exc),
                )
            )

    async def run(self) -> None:
        """Run the message bus (for async consumers)."""
        self._stopped = False
        # In a real implementation, this would process messages from a queue
        pass

    def stop(self) -> None:
        """Stop the message bus."""
        self._stopped = True

    def replay(self, start: int, end: int) -> None:
        """Replay messages from the log within the given timestamp range."""
        if self._message_log is None:
            return
        for message in self._message_log.read(start, end):
            self.publish(message)
