"""Lock-safe event bus for distributing market-data and OMS events.

Design notes
------------
- Events are immutable value objects.
- Subscribers are snapshotted before iteration so a handler that mutates the
  subscription list cannot corrupt the dispatch loop.
- Sequence numbering uses a lock-free ``itertools.count(1)`` (atomic under CPython GIL).
- Subscriber mutations/snapshots use a dedicated ``threading.Lock`` (not RLock)
  to minimise contention on the publish hot-path.
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

import itertools
import logging
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from domain.events import DomainEvent
from domain.events.types import canonical_event_types
from infrastructure.event_bus.event_dispatch_hook import EventDispatchHook
from infrastructure.event_bus.event_idempotency_guard import EventIdempotencyGuard
from infrastructure.event_bus.event_persistence_hook import EventPersistenceHook

if TYPE_CHECKING:
    from domain.ports.observability import AlertingEnginePort, EventMetricsPort
    from infrastructure.event_bus.dead_letter_queue import DeadLetterQueue
    from infrastructure.idempotency import IdempotencyService

logger = logging.getLogger(__name__)


EventHandler = Callable[[DomainEvent], None]


@dataclass
class EventBusConfig:
    """Configuration for EventBus behaviour and resource limits."""

    logging_enabled: bool = True
    fail_fast: bool = False
    replay_mode: bool = False
    alerting_interval_seconds: float = 10.0
    max_processed_events: int = 10_000
    enforce_event_types: bool = True
    idempotency_ttl_seconds: int = 86_400


class EventBus:
    """Thread-safe in-memory event bus with mandatory failure observability.

    Added replay_mode for deterministic replay.
    When replay_mode=True:
    - Auto-persistence is disabled (no recursive writes to EventLog)
    - Events use original timestamps instead of datetime.now()
    - Sequence numbers are preserved for total ordering

    Alerting Integration
    --------------------
    When an ``alerting_engine`` is provided, register
    ``bus.as_managed_service()`` with LifecycleManager to start the background
    evaluation thread (default interval 10 seconds). ``stop_alerting()`` stops
    it during graceful shutdown.

    Example::

        metrics = EventMetrics()
        dlq = DeadLetterQueue()
        engine = AlertingEngine(metrics)
        bus = EventBus(metrics=metrics, dead_letter_queue=dlq, alerting_engine=engine)
        # Or with custom config:
        bus = EventBus(config=EventBusConfig(fail_fast=True), metrics=metrics)
        token = bus.subscribe("TICK", lambda e: logger.debug("tick", extra={"payload": e.payload}))
        bus.publish(DomainEvent.now("TICK", {"ltp": 100.0}, symbol="RELIANCE"))
        bus.unsubscribe(token)
        bus.stop_alerting()  # Clean shutdown

    Parameters
    ----------
    config:
        Optional :class:`EventBusConfig` with behavioural tuning. When
        ``None``, sensible defaults are used (equivalent to
        ``EventBusConfig()``).
    event_log:
        Optional append-only :class:`EventLog` used for crash recovery.
    dead_letter_queue:
        Optional :class:`DeadLetterQueue` that receives failed handler
        invocations. **Required in production** — the bus will warn loudly
        if it is missing and a handler raises.
    metrics:
        Optional :class:`EventMetrics` that the bus increments for every
        publish / dispatch / failure. Required in production.
    alerting_engine:
        Optional :class:`AlertingEngine` for threshold-based alerting.
    idempotency:
        Optional :class:`IdempotencyService` for event dedup.
    """

    def __init__(
        self,
        config: EventBusConfig | None = None,
        event_log: Any | None = None,
        dead_letter_queue: DeadLetterQueue | None = None,
        metrics: EventMetricsPort | None = None,
        alerting_engine: AlertingEnginePort | None = None,
        idempotency: IdempotencyService | None = None,
    ) -> None:
        self._config = config or EventBusConfig()
        # Lock sharding — separate lightweight Lock for subscriber
        # management from the (now lock-free) sequence counter.
        # RLock -> Lock downgrade is safe: no call-site requires reentrancy.
        self._subscribers_lock = threading.Lock()
        self._sequence: itertools.count[int] = itertools.count(1)
        self._subscribers: dict[str, dict[str, EventHandler]] = {}
        self._event_log = event_log
        self._dead_letter_queue = dead_letter_queue
        self._metrics = metrics
        self._logging_enabled = self._config.logging_enabled
        self._fail_fast = self._config.fail_fast
        self._replay_mode = self._config.replay_mode
        # self._sequence_counter replaced by lock-free self._sequence
        self._alerting_engine = alerting_engine
        self._alerting_interval = self._config.alerting_interval_seconds
        self._managed_alerting: EventBusAlertingService | None = None

        self._idempotency_guard = EventIdempotencyGuard(
            idempotency=idempotency,
            ttl_seconds=self._config.idempotency_ttl_seconds,
            max_processed_events=self._config.max_processed_events,
        )
        self._persistence = EventPersistenceHook(
            event_log,
            logging_enabled=self._logging_enabled,
            replay_mode=self._replay_mode,
            dead_letter_queue=dead_letter_queue,
            metrics=metrics,
            fail_fast=self._fail_fast,
        )
        self._dispatch = EventDispatchHook(
            dead_letter_queue=dead_letter_queue,
            metrics=metrics,
            fail_fast=self._fail_fast,
        )
        self._enforce_event_types = self._config.enforce_event_types
        self._known_event_types = canonical_event_types()

        # Alerting starts via LifecycleManager (EventBusAlertingService), not ctor.

    @property
    def replay_mode(self) -> bool:
        """True if bus is in replay mode."""
        return self._replay_mode

    @property
    def event_log(self) -> Any | None:
        """Public accessor for the attached event log."""
        return self._event_log

    def set_replay_mode(self, enabled: bool) -> None:
        """Enable or disable replay mode.

        This is the public API for mutating replay_mode.  All callers
        (including TradingContext._replay_log_into_oms) must use this
        method instead of touching ``_replay_mode`` directly.
        """
        self._replay_mode = enabled
        self._persistence.set_replay_mode(enabled)

    @property
    def logging_enabled(self) -> bool:
        """True if event persistence to the event log is enabled."""
        return self._logging_enabled

    def set_logging_enabled(self, enabled: bool) -> None:
        """Enable or disable event persistence to the event log.

        During crash-recovery replay this is used to suppress recursive
        log writes that would corrupt the event stream.  All callers
        (including TradingContext._replay_log_into_oms) must use this
        method instead of touching ``_logging_enabled`` directly.

        Args:
            enabled: True to persist events, False to suppress persistence.
        """
        self._logging_enabled = enabled
        self._persistence.set_logging_enabled(enabled)

    def set_event_log(self, event_log: Any | None) -> None:
        """Attach or replace the persistent event log (ENG-010).

        Composition roots often build the bus before the log. Calling this
        once after both exist enables crash-recovery persistence without
        reconstructing the bus (which would drop subscribers).
        """
        self._event_log = event_log
        self._persistence.set_event_log(event_log)

    @property
    def alerting_engine(self) -> AlertingEnginePort | None:
        """The alerting engine instance, if configured."""
        return self._alerting_engine

    @property
    def has_alerting(self) -> bool:
        """True if an alerting engine is configured."""
        return self._alerting_engine is not None

    @property
    def alerting_alive(self) -> bool:
        """True if the background alerting thread is running."""
        svc = self._managed_alerting
        return svc is not None and svc.alive

    def stop_alerting(self) -> None:
        """Stop the background alerting thread (via :class:`EventBusAlertingService`)."""
        if self._managed_alerting is not None:
            self._managed_alerting.stop()

    # ── LifecycleManager integration (TOS-P7-003) ─────────────────────────

    def as_managed_service(self) -> EventBusAlertingService:
        """Return a ManagedService wrapper for LifecycleManager registration."""
        if self._managed_alerting is None:
            self._managed_alerting = EventBusAlertingService(self)
        return self._managed_alerting

    # ── Subscription management ────────────────────────────────────────────

    def subscribe(self, event_type: str, handler: EventHandler) -> str:
        """Subscribe to ``event_type``. Returns a token for unsubscribe."""
        token = uuid.uuid4().hex
        with self._subscribers_lock:
            self._subscribers.setdefault(event_type, {})[token] = handler
        return token

    def unsubscribe(self, token: str) -> bool:
        """Unsubscribe using the token returned by ``subscribe``."""
        with self._subscribers_lock:
            for handlers in self._subscribers.values():
                if token in handlers:
                    del handlers[token]
                    return True
        return False

    def subscribe_all(self, handler: EventHandler) -> list[str]:
        """Subscribe ``handler`` to every event type currently registered.

        Mirrors the capability previously provided by the deleted
        ``brokers.common.event_bus`` implementation, used by
        ``EventBusService`` to mirror the canonical OMS bus for the CLI
        ``events`` command without fabricating events. Returns a list of
        tokens (one per event type) so the caller can unsubscribe cleanly.
        Event types added after this call will NOT receive this handler —
        call ``subscribe_all`` again to pick up newly-registered types.

        Snapshots the event-type list under the lock, then releases it
        before calling :meth:`subscribe` per type. ``subscribe`` acquires
        the same ``_subscribers_lock`` itself, and ``threading.Lock`` is
        not reentrant — holding the lock for the whole loop (the previous
        implementation) self-deadlocked on every call, since the lock was
        never actually free once acquired. Confirmed: this made
        ``subscribe_all`` hang forever whenever ``_subscribers`` was
        non-empty at call time, i.e. on every real invocation once
        anything else had already subscribed to any event type.
        """
        with self._subscribers_lock:
            event_types = list(self._subscribers.keys())
        tokens: list[str] = []
        for event_type in event_types:
            token = self.subscribe(event_type, handler)
            tokens.append(token)
        return tokens

    def subscriber_count(self, event_type: str | None = None) -> int:
        """Return the number of subscribers (for tests / diagnostics)."""
        with self._subscribers_lock:
            if event_type is not None:
                return len(self._subscribers.get(event_type, {}))
            return sum(len(h) for h in self._subscribers.values())

    def clear(self) -> None:
        """Remove all subscribers. Useful in tests."""
        with self._subscribers_lock:
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
            from infrastructure.correlation import get_current_correlation_id

            cid = get_current_correlation_id()
            if cid is not None:
                replacements["correlation_id"] = cid

        # Assign sequence number in live mode only
        # Lock-free — ``next(itertools.count(1))`` is atomic under
        # the CPython GIL (single bytecode: CALL_FUNCTION on a C-level iterator).
        if not self._replay_mode:
            seq_num = next(self._sequence)
            if event.sequence_number == 0:
                replacements["sequence_number"] = seq_num
        # Replay mode: preserve original sequence_number (no assignment)

        # Optimization: return original if no replacements needed
        if not replacements:
            return event

        return replace(event, **replacements)

    # ── Idempotency ─────────────────────────────────────────────────────

    def _is_duplicate_event(self, event: DomainEvent) -> bool:
        return self._idempotency_guard.is_duplicate(event)

    # ── Publishing ────────────────────────────────────────────────────────

    def publish(self, event: DomainEvent) -> None:
        """Publish an event to all subscribers of ``event.event_type``.

        If the event has no ``correlation_id``, the current thread's
        active correlation ID (set via
        :func:`infrastructure.correlation.with_correlation`) is injected
        before dispatch.  This ensures every published event carries a
        traceable ID without requiring explicit propagation at every
        call site.

        In replay_mode, auto-persistence is disabled and
        sequence numbers are preserved for deterministic ordering.

        Handler failures are logged, counted, and dead-lettered — they
        never disappear silently.

        Idempotency - duplicate events (same event_id) are silently
        skipped to prevent double-processing under at-least-once delivery.
        """
        if self._enforce_event_types and event.event_type not in self._known_event_types:
            logger.warning(
                "EventBus: unknown event_type=%r (not in EventType enum); "
                "publish anyway but subscribers may never see it",
                event.event_type,
            )

        # Prepare event: inject infrastructure fields immutably
        event = self._prepare_event(event)

        # Idempotency: skip fully processed ids; claim before dispatch so retries
        # after handler failure (DLQ replay) can reuse the same event_id.
        if self._is_duplicate_event(event):
            if self._metrics is not None:
                self._metrics.add_timestamped_counter(event.event_type, "duplicate_skipped")
            logger.debug(
                "EventBus: skipping duplicate event_id=%s (type=%s, symbol=%s)",
                event.event_id,
                event.event_type,
                event.symbol,
            )
            return

        if not self._idempotency_guard.try_claim(event):
            if self._metrics is not None:
                self._metrics.add_timestamped_counter(event.event_type, "duplicate_skipped")
            logger.debug(
                "EventBus: skipping in-flight/duplicate event_id=%s (type=%s, symbol=%s)",
                event.event_id,
                event.event_type,
                event.symbol,
            )
            return

        if self._metrics is not None:
            self._metrics.add_timestamped_counter(event.event_type, "published")

        try:
            # 1. Persist first (so a crash mid-dispatch can be recovered).
            self._persistence.persist(event)

            # 2. Dispatch (snapshot handlers to be lock-safe).
            # Skip handler dispatch during replay to prevent TRADE_APPLIED re-publishing
            # which causes PositionManager to double-count trades.
            handler_failures = 0
            if not self._replay_mode:
                with self._subscribers_lock:
                    handlers = list(self._subscribers.get(event.event_type, {}).items())
                handler_failures = self._dispatch.dispatch(event, handlers)
        except Exception:
            self._idempotency_guard.release(event)
            raise

        if handler_failures:
            self._idempotency_guard.release(event)
        else:
            self._idempotency_guard.commit(event)

    def _handle_handler_failure(
        self, event: DomainEvent, handler_id: str, exc: BaseException
    ) -> None:
        """Backward-compat delegate to :class:`EventDispatchHook`."""
        self._dispatch.handle_failure(event, handler_id, exc)

    @property
    def _processed_event_ids(self) -> set[str]:
        """Backward-compat property exposing set of seen event IDs."""
        return self._idempotency_guard._processed_event_ids

    @property
    def _processed_events(self) -> set[str]:
        """Backward-compat property alias for _processed_event_ids."""
        return self._idempotency_guard._processed_event_ids


class EventBusAlertingService:
    """LifecycleManager-compatible wrapper for EventBus alerting (TOS-P7-003 / GC-01).

    Owns the daemon alerting thread and evaluation loop. Register with
    LifecycleManager so alerting starts and stops with the rest of the process.
    """

    name: str = "event_bus_alerting"

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    @property
    def alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if not self._bus.has_alerting or self.alive:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._alerting_loop,
            name="EventBus-Alerting",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "EventBus alerting started (interval=%.1fs)",
            self._bus._alerting_interval,
        )

    def _alerting_loop(self) -> None:
        """Background loop that periodically evaluates alert rules."""
        while not self._stop.is_set():
            try:
                engine = self._bus._alerting_engine
                if engine is not None:
                    alerts = engine.evaluate_all()
                    if alerts:
                        logger.info(
                            "EventBus alerting: %d alert(s) fired",
                            len(alerts),
                        )
            except Exception as exc:
                logger.exception(
                    "EventBus alerting evaluation failed: %s",
                    exc,
                )
            self._stop.wait(self._bus._alerting_interval)

    def stop(self, timeout_seconds: float = 5.0) -> None:
        if self._thread is None:
            return
        self._stop.set()
        self._thread.join(timeout=timeout_seconds)
        if self._thread.is_alive():
            logger.warning("EventBus alerting thread did not stop within timeout")
        else:
            logger.info("EventBus alerting stopped")
            self._thread = None

    def health(self) -> Any:
        from domain.lifecycle_health import HealthState, HealthStatus
        from domain.ports.time_service import get_current_clock

        alive = self.alive
        return HealthStatus(
            state=HealthState.HEALTHY
            if alive or not self._bus.has_alerting
            else HealthState.DEGRADED,
            service=self.name,
            last_check=get_current_clock().now(),
            detail="alerting_thread_alive" if alive else "alerting_idle",
        )
