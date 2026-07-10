"""In-memory idempotency cache for order placement safety.

Now shared with Dhan via brokers.common.idempotency (see that module's
docstring for why: this class used to be a hand-mirrored duplicate of
brokers.dhan.execution.order_placement.IdempotencyCache, and the Dhan
version had a confirmed race condition this consolidation fixes).

``InMemoryIdempotencyCache`` is kept as a name-compatible alias so existing
call sites (``InMemoryIdempotencyCache()``) are unaffected — it accepts no
constructor args, matching the old class, and uses the shared cache's
defaults.
"""

from __future__ import annotations

from typing import TypeVar

from brokers.common.idempotency import IdempotencyCache, IdempotencyCachePort

T = TypeVar("T")


class InMemoryIdempotencyCache(IdempotencyCache[T]):
    """Backward-compatible name for brokers.common.idempotency.IdempotencyCache.

    The old version had no TTL/reservation protocol (bare dict + RLock);
    the shared cache adds both but they are optional to use — get()/put()
    alone (this class's original surface) still works unchanged.
    """


__all__ = ["InMemoryIdempotencyCache", "IdempotencyCachePort"]
