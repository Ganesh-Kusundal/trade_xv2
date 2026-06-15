"""Lock-safe event bus for distributing market-data and OMS events.

Design notes (Dr. Venkat style)
-------------------------------
- Events are immutable value objects.
- Subscribers are snapshotted before iteration so a handler that mutates the
  subscription list cannot corrupt the dispatch loop.
- All public methods are protected by one ``threading.RLock``.
- The bus is intentionally synchronous; asynchronous consumers should push
  events into their own queue from the handler.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable


@dataclass(frozen=True)
class DomainEvent:
    """An immutable domain event published on the bus."""

    event_type: str
    timestamp: datetime
    payload: dict
    symbol: str | None = None
    source: str | None = None
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])

    def __post_init__(self) -> None:
        # Ensure timestamps are timezone-aware for deterministic ordering.
        if self.timestamp.tzinfo is None:
            object.__setattr__(
                self, "timestamp", self.timestamp.replace(tzinfo=timezone.utc)
            )

    @classmethod
    def now(
        cls,
        event_type: str,
        payload: dict,
        symbol: str | None = None,
        source: str | None = None,
    ) -> DomainEvent:
        """Factory using UTC now."""
        return cls(
            event_type=event_type,
            timestamp=datetime.now(timezone.utc),
            payload=payload,
            symbol=symbol,
            source=source,
        )


EventHandler = Callable[[DomainEvent], None]


class EventBus:
    """Thread-safe in-memory event bus.

    Example:
        bus = EventBus()
        token = bus.subscribe("TICK", lambda e: print(e.payload))
        bus.publish(DomainEvent.now("TICK", {"ltp": 100.0}, symbol="RELIANCE"))
        bus.unsubscribe(token)

    An optional ``EventLog`` can be attached so every published event is also
    persisted to an append-only JSONL log for crash recovery.
    """

    def __init__(self, event_log: Any | None = None, logging_enabled: bool = True) -> None:
        self._lock = threading.RLock()
        self._subscribers: dict[str, dict[str, EventHandler]] = {}
        self._event_log = event_log
        self._logging_enabled = logging_enabled

    def subscribe(self, event_type: str, handler: EventHandler) -> str:
        """Subscribe to ``event_type``. Returns a token for unsubscribe."""
        token = uuid.uuid4().hex
        with self._lock:
            self._subscribers.setdefault(event_type, {})[token] = handler
        return token

    def unsubscribe(self, token: str) -> bool:
        """Unsubscribe using the token returned by ``subscribe``."""
        with self._lock:
            for handlers in self._subscribers.values():
                if token in handlers:
                    del handlers[token]
                    return True
        return False

    def publish(self, event: DomainEvent) -> None:
        """Publish an event to all subscribers of ``event.event_type``.

        If an ``EventLog`` is attached, the event is persisted before dispatch.
        """
        if self._event_log is not None and self._logging_enabled:
            try:
                self._event_log.append(event)
            except Exception:
                # Logging must not stop event distribution.
                pass
        with self._lock:
            handlers = list(self._subscribers.get(event.event_type, {}).values())
        for handler in handlers:
            try:
                handler(event)
            except Exception:
                # A misbehaving handler must not stop other subscribers.
                # Log and continue. In production this should emit a metric.
                pass

    def publish_sync(self, event: DomainEvent) -> None:
        """Alias for ``publish``; kept for explicit synchronous semantics."""
        self.publish(event)

    def subscriber_count(self, event_type: str | None = None) -> int:
        """Return the number of subscribers (for tests / diagnostics)."""
        with self._lock:
            if event_type is not None:
                return len(self._subscribers.get(event_type, {}))
            return sum(len(h) for h in self._subscribers.values())

    def clear(self) -> None:
        """Remove all subscribers. Useful in tests."""
        with self._lock:
            self._subscribers.clear()
