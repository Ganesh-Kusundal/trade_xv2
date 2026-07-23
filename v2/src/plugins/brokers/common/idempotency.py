"""Shared broker-transport idempotency cache — v2 port.

This is the v2 port of ``src/brokers/common/idempotency.py``
``IdempotencyCache``. It keeps the same reserve/commit/clear_reservation
three-phase protocol Dhan's order placement relies on to stop two
concurrent ``place_order`` calls sharing a correlation_id from both
reaching the broker.

Key invariants (mirrored from the legacy implementation):

- ``get()`` reads committed results under the storage lock and lazily
  evicts an expired entry without dropping the lock first — no read/
  delete race.
- ``reserve()`` is atomic under its own lock: it returns ``False`` if the
  cid is already reserved (unexpired) **or** already committed (unexpired).
- ``commit()`` moves a reservation into the committed store (so a later
  ``reserve`` returns ``False``) and drops the pending reservation.
- ``clear_reservation()`` removes only a pending reservation (used when a
  POST was never sent), never a committed value — so a successful POST
  whose response parse fails keeps the commit, preventing a duplicate on
  retry.

Storage is self-contained here (``dict`` + ``threading.Lock``) with TTL
eviction and a ``max_size`` LRU-style cap, rather than delegating to an
infrastructure backend that does not exist in v2. Reusing a hand-rolled
dict+lock cache is fine so long as every read/delete of an expired entry
happens while still holding the lock, which is what ``get`` does below.
"""

from __future__ import annotations

import threading
import time
from typing import Generic, TypeVar

T = TypeVar("T")


class IdempotencyCache(Generic[T]):
    """Thread-safe idempotency store keyed by correlation_id.

    The committed results cache and the pending reservation set each have
    their own lock, matching the legacy layering where the results cache
    and the reservation protocol were independently synchronized.
    """

    def __init__(self, ttl: float = 300.0, max_size: int = 10_000) -> None:
        self._ttl = ttl
        self._max_size = max_size
        # cid -> (value, expiry_monotonic)
        self._committed: dict[str, tuple[T, float]] = {}
        self._committed_lock = threading.Lock()
        # cid -> expiry_monotonic
        self._pending: dict[str, float] = {}
        self._pending_lock = threading.Lock()

    def get(self, cid: str) -> T | None:
        """Return the committed value for *cid* if present and unexpired.

        Lazily evicts an expired entry while still holding the storage
        lock so two threads racing an expired read cannot both pass the
        check and then collide on deletion.
        """
        with self._committed_lock:
            entry = self._committed.get(cid)
            if entry is None:
                return None
            value, expiry = entry
            if time.monotonic() < expiry:
                return value
            # Expired — evict under the lock before returning.
            self._committed.pop(cid, None)
            return None

    def put(self, cid: str, value: T) -> None:
        """Store *value* for *cid* with the configured TTL."""
        with self._committed_lock:
            self._store_committed(cid, value)

    def reserve(self, cid: str) -> bool:
        """Atomically try to reserve *cid*. Returns True if we got it.

        Returns ``False`` if the cid is already reserved (unexpired) or
        already committed (unexpired).
        """
        now = time.monotonic()
        # Committed and unexpired? Refuse — a finished placement owns this
        # correlation_id.
        with self._committed_lock:
            entry = self._committed.get(cid)
            if entry is not None and now < entry[1]:
                return False
        # Otherwise try to grab the pending reservation atomically.
        with self._pending_lock:
            pending_expiry = self._pending.get(cid)
            if pending_expiry is not None and now < pending_expiry:
                return False  # another caller holds the reservation
            self._pending[cid] = now + self._ttl
            return True

    def commit(self, cid: str, value: T) -> None:
        """Move a reservation into the committed store."""
        with self._committed_lock:
            self._store_committed(cid, value)
        with self._pending_lock:
            self._pending.pop(cid, None)

    def clear_reservation(self, cid: str) -> None:
        """Drop only a pending reservation for *cid* (never a commit)."""
        with self._pending_lock:
            self._pending.pop(cid, None)

    def clear(self) -> None:
        """Clear all committed results and pending reservations."""
        with self._committed_lock:
            self._committed.clear()
        with self._pending_lock:
            self._pending.clear()

    # -- internal helpers -------------------------------------------------

    def _store_committed(self, cid: str, value: T) -> None:
        """Store committed value under ``_committed_lock`` with TTL + LRU.

        Caller must already hold ``_committed_lock``. Enforces
        ``max_size`` by evicting the least-recently-stored entry (FIFO on
        insertion order, which under insertion-ordered dicts is the
        oldest) when over capacity.
        """
        expiry = time.monotonic() + self._ttl
        if cid in self._committed:
            self._committed.pop(cid)
        elif len(self._committed) >= self._max_size and self._max_size > 0:
            # Evict the oldest entry (first inserted).
            oldest = next(iter(self._committed))
            self._committed.pop(oldest)
        self._committed[cid] = (value, expiry)


__all__ = ["IdempotencyCache"]
