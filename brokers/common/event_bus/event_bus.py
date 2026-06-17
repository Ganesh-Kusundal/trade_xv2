"""Lock-safe event bus for distributing market-data and OMS events.

Design notes
------------
- Events are immutable value objects.
- Subscribers are snapshotted before iteration so a handler that mutates the
  subscription list cannot corrupt the dispatch loop.
- All public methods are protected by one ``threading.RLock``.
- The bus is intentionally synchronous; asynchronous consumers should push
  events into their own queue from the handler.
- **Handler failures are NEVER silently swallowed.** Each failure is:

  1. Logged at WARNING level with the event type, handler id, and error.
  2. Counted in :class:`EventMetrics` under
     ``(event_type, handler_error:<exception_type>)``.
  3. Captured in the attached :class:`DeadLetterQueue` for later replay.

  A misbehaving handler does not stop other subscribers from running.
"""

from __future__ import annotations

import logging
import threading
import traceback
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from brokers.common.event_bus.dead_letter_queue import DeadLetterQueue
    from brokers.common.observability.event_metrics import EventMetrics

logger = logging.getLogger(__name__)

# Optional correlation ID support — always available but guarded so the
# event bus is usable even if brokers/common/correlation.py is removed.
try:
    from brokers.common.correlation import get_current_correlation_id
except ImportError:  # pragma: no cover
    get_current_correlation_id = lambda: None


@dataclass(frozen=True)
class DomainEvent:
    """An immutable domain event published on the bus."""

    event_type: str
    timestamp: datetime
    payload: dict
    symbol: str | None = None
    source: str | None = None
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    correlation_id: str | None = None

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
        correlation_id: str | None = None,
    ) -> DomainEvent:
        """Factory using UTC now.

        If *correlation_id* is not provided, the current thread's active
        correlation ID (set via :func:`brokers.common.correlation.with_correlation`)
        is used.  This enables automatic end-to-end tracing without
        passing ``correlation_id=`` at every call site.

        Args:
            event_type: Type of the event
            payload: Event payload dictionary
            symbol: Optional symbol associated with the event
            source: Optional source identifier
            correlation_id: Optional correlation ID for tracing
        """
        if correlation_id is None:
            cid = get_current_correlation_id()
            if cid is not None:
                correlation_id = cid
        return cls(
            event_type=event_type,
            timestamp=datetime.now(timezone.utc),
            payload=payload,
            symbol=symbol,
            source=source,
            correlation_id=correlation_id,
        )


EventHandler = Callable[[DomainEvent], None]


class EventBus:
    """Thread-safe in-memory event bus with mandatory failure observability.

    Example::

        metrics = EventMetrics()
        dlq = DeadLetterQueue()
        bus = EventBus(metrics=metrics, dead_letter_queue=dlq)
        token = bus.subscribe("TICK", lambda e: print(e.payload))
        bus.publish(DomainEvent.now("TICK", {"ltp": 100.0}, symbol="RELIANCE"))
        bus.unsubscribe(token)

    Parameters
    ----------
    event_log:
        Optional append-only :class:`EventLog` used for crash recovery.
    dead_letter_queue:
        Optional :class:`DeadLetterQueue` that receives failed handler
        invocations. **Required in production** — the bus will warn loudly
        if it is missing and a handler raises.
    metrics:
        Optional :class:`EventMetrics` that the bus increments for every
        publish / dispatch / failure. Required in production.
    logging_enabled:
        If True (default), the bus forwards every event to the attached
        ``event_log`` before dispatch. Used during crash-recovery replay
        to suppress recursive log writes.
    fail_fast:
        If True, the bus re-raises handler exceptions after capturing them.
        Defaults to False (the bus never stops the dispatch loop on a bad
        handler) but tests use True to assert on failures.
    """

    def __init__(
        self,
        event_log: Any | None = None,
        dead_letter_queue: DeadLetterQueue | None = None,
        metrics: EventMetrics | None = None,
        logging_enabled: bool = True,
        fail_fast: bool = False,
    ) -> None:
        self._lock = threading.RLock()
        self._subscribers: dict[str, dict[str, EventHandler]] = {}
        self._event_log = event_log
        self._dead_letter_queue = dead_letter_queue
        self._metrics = metrics
        self._logging_enabled = logging_enabled
        self._fail_fast = fail_fast

    # ── Subscription management ────────────────────────────────────────────

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

    # ── Publishing ────────────────────────────────────────────────────────

    def publish(self, event: DomainEvent) -> None:
        """Publish an event to all subscribers of ``event.event_type``.

        If the event has no ``correlation_id``, the current thread's
        active correlation ID (set via
        :func:`brokers.common.correlation.with_correlation`) is injected
        before dispatch.  This ensures every published event carries a
        traceable ID without requiring explicit propagation at every
        call site.

        Handler failures are logged, counted, and dead-lettered — they
        never disappear silently.
        """
        # Auto-inject correlation_id from thread-local context if missing.
        if event.correlation_id is None:
            cid = get_current_correlation_id()
            if cid is not None:
                # DomainEvent is frozen, so use object.__setattr__
                object.__setattr__(event, "correlation_id", cid)

        if self._metrics is not None:
            self._metrics.inc(event.event_type, "published")

        # 1. Persist first (so a crash mid-dispatch can be recovered).
        if self._event_log is not None and self._logging_enabled:
            try:
                self._event_log.append(event)
            except Exception as exc:
                # Surface, never swallow.
                if self._metrics is not None:
                    self._metrics.inc(
                        event.event_type, f"log_error:{type(exc).__name__}"
                    )
                logger.error(
                    "EventBus: failed to persist %s to log: %s",
                    event.event_type,
                    exc,
                    exc_info=True,
                )
                if self._dead_letter_queue is not None:
                    self._dead_letter_queue.push_failure(
                        event=event,
                        handler_id="<event_log>",
                        exc=exc,
                        traceback=traceback.format_exc(),
                    )
                if self._fail_fast:
                    raise

        # 2. Dispatch (snapshot handlers to be lock-safe).
        with self._lock:
            handlers = list(self._subscribers.get(event.event_type, {}).items())

        for handler_id, handler in handlers:
            if self._metrics is not None:
                self._metrics.inc(event.event_type, "dispatched")
            try:
                handler(event)
            except Exception as exc:
                self._handle_handler_failure(event, handler_id, exc)
                if self._fail_fast:
                    raise

    def publish_sync(self, event: DomainEvent) -> None:
        """Alias for :meth:`publish`; kept for explicit synchronous semantics."""
        self.publish(event)

    # ── Internal helpers ──────────────────────────────────────────────────

    def _handle_handler_failure(
        self, event: DomainEvent, handler_id: str, exc: BaseException
    ) -> None:
        """Mandatory failure-path: log, count, dead-letter."""
        error_type = type(exc).__name__

        if self._metrics is not None:
            self._metrics.inc(event.event_type, f"handler_error:{error_type}")
            self._metrics.inc(event.event_type, "dead_letter")

        logger.warning(
            "EventBus: handler %s failed on %s (event_id=%s, symbol=%s): %s: %s",
            handler_id,
            event.event_type,
            event.event_id,
            event.symbol,
            error_type,
            exc,
        )

        if self._dead_letter_queue is not None:
            self._dead_letter_queue.push_failure(
                event=event,
                handler_id=handler_id,
                exc=exc,
                traceback=traceback.format_exc(),
            )
        else:
            # Loud, visible warning so missing DLQ is impossible to miss.
            logger.error(
                "EventBus: handler %s failed on %s but no DeadLetterQueue is "
                "attached. The failure is only visible in logs. "
                "This is a configuration error in production.",
                handler_id,
                event.event_type,
            )
