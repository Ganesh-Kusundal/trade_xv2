"""Event idempotency guard — single dedup authority for EventBus."""

from __future__ import annotations

import logging
import threading
from collections import deque
from typing import TYPE_CHECKING

from domain.events import DomainEvent

if TYPE_CHECKING:
    from infrastructure.idempotency import IdempotencyService

logger = logging.getLogger(__name__)


class EventIdempotencyGuard:
    """Deduplicate events by event_id (IdempotencyService or bounded local set)."""

    def __init__(
        self,
        *,
        idempotency: IdempotencyService | None = None,
        ttl_seconds: int = 86_400,
        max_processed_events: int = 10_000,
    ) -> None:
        self._idempotency = idempotency
        self._ttl_seconds = ttl_seconds
        self._processed_events: deque[str] = deque(maxlen=max_processed_events)
        self._processed_event_ids: set[str] = set()
        self._in_flight_event_ids: set[str] = set()
        self._lock = threading.Lock()

    def try_claim(self, event: DomainEvent) -> bool:
        """Claim event_id for processing. False if already completed or in-flight."""
        event_id = event.event_id
        if not event_id:
            return True

        if self._idempotency is not None:
            return self._idempotency.claim(event_id, event_id, self._ttl_seconds)

        with self._lock:
            if event_id in self._processed_event_ids or event_id in self._in_flight_event_ids:
                return False
            self._in_flight_event_ids.add(event_id)
            return True

    def release(self, event: DomainEvent) -> None:
        """Release a failed claim so DLQ replay can re-dispatch the same event_id."""
        event_id = event.event_id
        if not event_id:
            return

        if self._idempotency is not None:
            self._idempotency.delete(event_id)
            return

        with self._lock:
            self._in_flight_event_ids.discard(event_id)

    def commit(self, event: DomainEvent) -> None:
        """Mark event_id as successfully processed."""
        event_id = event.event_id
        if not event_id:
            return

        if self._idempotency is not None:
            return

        with self._lock:
            self._in_flight_event_ids.discard(event_id)
            if event_id in self._processed_event_ids:
                return
            self._processed_event_ids.add(event_id)
            self._processed_events.append(event_id)
            if len(self._processed_events) == self._processed_events.maxlen:
                oldest = self._processed_events.popleft()
                self._processed_event_ids.discard(oldest)

    def is_duplicate(self, event: DomainEvent) -> bool:
        """Return True if this event_id was already processed (skip dispatch)."""
        event_id = event.event_id
        if not event_id:
            return False

        if self._idempotency is not None:
            return self._idempotency.contains(event_id)

        with self._lock:
            return event_id in self._processed_event_ids
