"""Shared broker-transport idempotency cache — one implementation, not two.

Previously Dhan and Upstox each had their own broker-level "cache an order
result by correlation_id so a retried placement call is safe" component:

- brokers.dhan.execution.order_placement.IdempotencyCache had a confirmed
  race condition: get() read self._cache without holding _lock, then
  deleted an expired entry under _lock — two threads racing an expired
  read could both pass the check and the second del raised KeyError.
  Its lock() method also acquired _pending_lock with no matching release.
- brokers.upstox.orders.idempotency.InMemoryIdempotencyCache's own
  docstring said "Mirrors brokers.dhan.orders.idempotency.InMemoryIdempotencyCache"
  — an explicit, self-documented duplicate.

This module replaces both with one component, built on top of the
already-correct (but previously unused) infrastructure.idempotency.memory_cache
.MemoryIdempotencyCache for storage — reusing existing, already-tested,
race-free locking instead of writing a third dict+lock cache by hand.

Two usage shapes are supported because the two brokers used the concept
differently:

- IdempotencyCache: the fuller reserve/commit/clear_reservation protocol
  Dhan's order placement needs, to stop two concurrent place_order calls
  with the same correlation_id both reaching the broker.
- get()/put() alone (via the same class) is sufficient for Upstox's
  simpler cache-aside usage — the reserve/commit protocol is optional to
  use, not required.
"""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING, Generic, Protocol, TypeVar, runtime_checkable

from infrastructure.idempotency.memory_cache import MemoryIdempotencyCache

T = TypeVar("T")

if TYPE_CHECKING:
    pass


@runtime_checkable
class IdempotencyCachePort(Protocol[T]):
    """What a broker order-command adapter needs from an idempotency cache."""

    def get(self, key: str) -> T | None: ...

    def put(self, key: str, value: T) -> None: ...


class IdempotencyCache(Generic[T]):
    """Thread-safe idempotency store keyed by correlation_id.

    Storage (get/put/expiry) delegates to MemoryIdempotencyCache, which
    already does the locked read-then-maybe-delete correctly in one
    critical section — no separate unlocked read followed by a locked
    delete, which is exactly the pattern that caused the original race.

    The reserve/commit/clear_reservation three-phase protocol (used by
    Dhan's OrderPlacer to stop two concurrent place_order calls with the
    same correlation_id from both reaching the broker) is layered on top
    with its own lock, independent of the results cache's lock.
    """

    def __init__(self, ttl: float = 300.0, max_size: int = 10_000) -> None:
        self._ttl = ttl
        self._results: MemoryIdempotencyCache[T] = MemoryIdempotencyCache(
            default_ttl_seconds=int(ttl), max_size=max_size
        )
        # pending reservations keyed by correlation_id
        self._pending: dict[str, float] = {}
        self._pending_lock = threading.Lock()

    def get(self, cid: str) -> T | None:
        return self._results.get(cid)

    def put(self, cid: str, value: T) -> None:
        self._results.put(cid, value)

    def reserve(self, cid: str) -> bool:
        """Atomically try to reserve *cid*. Returns True if we got it."""
        with self._pending_lock:
            now = time.monotonic()
            existing = self._pending.get(cid)
            if existing is not None and (now - existing) < self._ttl:
                return False  # another caller holds the reservation
            self._pending[cid] = now
            return True

    def commit(self, cid: str, value: T) -> None:
        self.put(cid, value)
        with self._pending_lock:
            self._pending.pop(cid, None)

    def clear_reservation(self, cid: str) -> None:
        with self._pending_lock:
            self._pending.pop(cid, None)

    def clear(self) -> None:
        """Clear all committed results and pending reservations."""
        self._results.clear()
        with self._pending_lock:
            self._pending.clear()


__all__ = ["IdempotencyCache", "IdempotencyCachePort"]
