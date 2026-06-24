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
import time
import traceback
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from infrastructure.event_bus.models import EventType
from infrastructure.correlation import get_current_correlation_id

if TYPE_CHECKING:
    from infrastructure.event_bus.dead_letter_queue import DeadLetterQueue
    from domain.ports.observability import AlertingEnginePort, EventMetricsPort

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DomainEvent:
    """An immutable domain event published on the bus.
    
    P4-Phase 4: Added sequence_number for deterministic replay ordering.
    When two events share the same timestamp, sequence_number provides
    a total order guarantee for replay determinism.
    """

    event_type: str
    timestamp: datetime
    payload: dict
    symbol: str | None = None
    source: str | None = None
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    correlation_id: str | None = None
    sequence_number: int = 0  # P4: Monotonic counter for deterministic ordering

    def __post_init__(self) -> None:
        # Fail-fast on naive timestamps — callers must provide timezone-aware datetimes.
        # Normalization responsibility moved to DomainEvent.now() factory.
        if self.timestamp.tzinfo is None:
            raise ValueError(
                f"DomainEvent requires timezone-aware timestamps. "
                f"Got naive datetime: {self.timestamp}. "
                f"Use DomainEvent.now() factory or provide tzinfo explicitly."
            )

    @classmethod
    def now(
        cls,
        event_type: str,
        payload: dict,
        symbol: str | None = None,
        source: str | None = None,
        correlation_id: str | None = None,
        sequence_number: int = 0,
    ) -> DomainEvent:
        """Factory using UTC now.

        If *correlation_id* is not provided, the current thread's active
        correlation ID (set via :func:`infrastructure.correlation.with_correlation`)
        is used.  This enables automatic end-to-end tracing without
        passing ``correlation_id=`` at every call site.

        Args:
            event_type: Type of the event
            payload: Event payload dictionary
            symbol: Optional symbol associated with the event
            source: Optional source identifier
            correlation_id: Optional correlation ID for tracing
            sequence_number: Optional sequence number for replay ordering (P4)
        """
        if correlation_id is None:
            cid = get_current_correlation_id()
            if cid is not None:
                correlation_id = cid
        return cls(
            event_type=event_type,
            timestamp=datetime.now(timezone.utc),
            payload=dict(payload),  # Defensive shallow copy — prevents handler mutation
            symbol=symbol,
            source=source,
            correlation_id=correlation_id,
            sequence_number=sequence_number,
        )


EventHandler = Callable[[DomainEvent], None]


class EventBus:
    """Thread-safe in-memory event bus with mandatory failure observability.

    P4-Phase 4: Added replay_mode for deterministic replay.
    When replay_mode=True:
    - Auto-persistence is disabled (no recursive writes to EventLog)
    - Events use original timestamps instead of datetime.now()
    - Sequence numbers are preserved for total ordering

    Alerting Integration
    --------------------
    When an ``alerting_engine`` is provided, the bus starts a background
    thread that periodically evaluates alert rules (default every 10 seconds).
    All metrics increments use timestamped counters to enable rate-based
    alerting.

    Example::

        metrics = EventMetrics()
        dlq = DeadLetterQueue()
        engine = AlertingEngine(metrics)
        bus = EventBus(metrics=metrics, dead_letter_queue=dlq, alerting_engine=engine)
        token = bus.subscribe("TICK", lambda e: print(e.payload))
        bus.publish(DomainEvent.now("TICK", {"ltp": 100.0}, symbol="RELIANCE"))
        bus.unsubscribe(token)
        bus.stop_alerting()  # Clean shutdown

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
    replay_mode:
        P4: If True, disables auto-persistence and preserves original
        event timestamps for deterministic replay.
    alerting_engine:
        Optional :class:`AlertingEngine` for threshold-based alerting.
        When provided, a background thread evaluates alert rules every
        ``alerting_interval_seconds`` seconds.
    alerting_interval_seconds:
        Interval between alert evaluations (default 10 seconds).
    """

    def __init__(
        self,
        event_log: Any | None = None,
        dead_letter_queue: DeadLetterQueue | None = None,
        metrics: EventMetricsPort | None = None,
        logging_enabled: bool = True,
        fail_fast: bool = False,
        replay_mode: bool = False,  # P4
        alerting_engine: AlertingEnginePort | None = None,
        alerting_interval_seconds: float = 10.0,
    ) -> None:
        self._lock = threading.RLock()
        self._subscribers: dict[str, dict[str, EventHandler]] = {}
        self._event_log = event_log
        self._dead_letter_queue = dead_letter_queue
        self._metrics = metrics
        self._logging_enabled = logging_enabled
        self._fail_fast = fail_fast
        self._replay_mode = replay_mode  # P4
        self._sequence_counter = 0  # P4
        self._alerting_engine = alerting_engine
        self._alerting_interval = alerting_interval_seconds
        self._alerting_thread: threading.Thread | None = None
        self._alerting_stop = threading.Event()

        # Start background alerting thread if engine is provided.
        if self._alerting_engine is not None:
            self._start_alerting()

    @property
    def replay_mode(self) -> bool:
        """True if bus is in replay mode (P4)."""
        return self._replay_mode

    def set_replay_mode(self, enabled: bool) -> None:
        """Enable or disable replay mode (P4).

        This is the public API for mutating replay_mode.  All callers
        (including TradingContext._replay_log_into_oms) must use this
        method instead of touching ``_replay_mode`` directly.
        """
        self._replay_mode = enabled

    @property
    def alerting_engine(self) -> AlertingEnginePort | None:
        """The alerting engine instance, if configured."""
        return self._alerting_engine

    def _start_alerting(self) -> None:
        """Start the background alerting evaluation thread."""
        if self._alerting_engine is None:
            return

        self._alerting_stop.clear()
        self._alerting_thread = threading.Thread(
            target=self._alerting_loop,
            name="EventBus-Alerting",
            daemon=True,
        )
        self._alerting_thread.start()
        logger.info(
            "EventBus alerting started (interval=%.1fs)",
            self._alerting_interval,
        )

    def _alerting_loop(self) -> None:
        """Background loop that periodically evaluates alert rules."""
        while not self._alerting_stop.is_set():
            try:
                if self._alerting_engine is not None:
                    alerts = self._alerting_engine.evaluate_all()
                    if alerts:
                        logger.info(
                            "EventBus alerting: %d alert(s) fired",
                            len(alerts),
                        )
            except Exception as exc:
                logger.error(
                    "EventBus alerting evaluation failed: %s",
                    exc,
                    exc_info=True,
                )
            # Sleep in small increments to allow fast shutdown.
            self._alerting_stop.wait(self._alerting_interval)

    def stop_alerting(self) -> None:
        """Stop the background alerting thread.

        Call this during graceful shutdown to ensure the thread exits cleanly.
        """
        if self._alerting_thread is None:
            return

        self._alerting_stop.set()
        self._alerting_thread.join(timeout=5.0)
        if self._alerting_thread.is_alive():
            logger.warning("EventBus alerting thread did not stop within timeout")
        else:
            logger.info("EventBus alerting stopped")

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

    # ── Internal helpers ──────────────────────────────────────────────────

    def _prepare_event(self, event: DomainEvent) -> DomainEvent:
        """Create a new event with infrastructure fields injected immutably.

        This is the copy-on-publish pattern: instead of mutating the frozen
        DomainEvent via object.__setattr__, we use dataclasses.replace() to
        create a new instance with injected correlation_id and sequence_number.

        Returns the original event if no changes are needed (optimization).
        """
        replacements: dict[str, Any] = {}

        # Inject correlation_id from thread-local context if missing
        if event.correlation_id is None:
            cid = get_current_correlation_id()
            if cid is not None:
                replacements["correlation_id"] = cid

        # P4: Assign sequence number in live mode only
        if not self._replay_mode:
            with self._lock:
                self._sequence_counter += 1
                seq_num = self._sequence_counter
            if event.sequence_number == 0:
                replacements["sequence_number"] = seq_num
        # Replay mode: preserve original sequence_number (no assignment)

        # Optimization: return original if no replacements needed
        if not replacements:
            return event

        return replace(event, **replacements)

    # ── Publishing ────────────────────────────────────────────────────────

    def publish(self, event: DomainEvent) -> None:
        """Publish an event to all subscribers of ``event.event_type``.

        If the event has no ``correlation_id``, the current thread's
        active correlation ID (set via
        :func:`brokers.common.correlation.with_correlation`) is injected
        before dispatch.  This ensures every published event carries a
        traceable ID without requiring explicit propagation at every
        call site.

        P4-Phase 4: In replay_mode, auto-persistence is disabled and
        sequence numbers are preserved for deterministic ordering.

        Handler failures are logged, counted, and dead-lettered — they
        never disappear silently.
        """
        # Prepare event: inject infrastructure fields immutably
        event = self._prepare_event(event)

        if self._metrics is not None:
            self._metrics.add_timestamped_counter(event.event_type, "published")

        # 1. Persist first (so a crash mid-dispatch can be recovered).
        # P4: Skip persistence in replay mode (no recursive writes)
        if self._event_log is not None and self._logging_enabled and not self._replay_mode:
            try:
                self._event_log.append(event)
            except Exception as exc:
                # Surface, never swallow.
                if self._metrics is not None:
                    self._metrics.add_timestamped_counter(
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
        # A3: Skip handler dispatch during replay to prevent TRADE_APPLIED re-publishing
        # which causes PositionManager to double-count trades.
        if self._replay_mode:
            return

        with self._lock:
            handlers = list(self._subscribers.get(event.event_type, {}).items())

        for handler_id, handler in handlers:
            if self._metrics is not None:
                self._metrics.add_timestamped_counter(event.event_type, "dispatched")
            try:
                handler(event)
            except Exception as exc:
                self._handle_handler_failure(event, handler_id, exc)
                if self._fail_fast:
                    raise

    def publish_sync(self, event: DomainEvent) -> None:
        """Alias for :meth:`publish`; kept for explicit synchronous semantics."""
        self.publish(event)

    def _handle_handler_failure(
        self, event: DomainEvent, handler_id: str, exc: BaseException
    ) -> None:
        """Mandatory failure-path: log, count, dead-letter."""
        error_type = type(exc).__name__

        if self._metrics is not None:
            self._metrics.add_timestamped_counter(
                event.event_type, f"handler_error:{error_type}"
            )
            self._metrics.add_timestamped_counter(event.event_type, "dead_letter")

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
