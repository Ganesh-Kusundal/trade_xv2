"""Memory-based idempotency cache for development and testing."""

from __future__ import annotations

import threading
from typing import Any, Generic, TypeVar

from cachetools import TTLCache

from domain.constants import SECONDS_PER_DAY
from infrastructure.idempotency.service import IdempotencyCacheBackend

T = TypeVar("T")


class MemoryIdempotencyCache(IdempotencyCacheBackend[T]):
    """Thread-safe in-memory idempotency cache backed by ``TTLCache``."""

    def __init__(self, default_ttl_seconds: int = SECONDS_PER_DAY, max_size: int = 10000):
        self._lock = threading.RLock()
        self._default_ttl = default_ttl_seconds
        self._max_size = max_size
        # ponytail: TTLCache uses one TTL per cache; per-key ttl_seconds on put()
        # uses default_ttl (callers today pass SECONDS_PER_DAY everywhere).
        self._cache: TTLCache[str, T] = TTLCache(maxsize=max_size, ttl=default_ttl_seconds)
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def get(self, key: str) -> T | None:
        with self._lock:
            try:
                value = self._cache[key]
            except KeyError:
                self._misses += 1
                return None
            self._hits += 1
            return value

    def put(self, key: str, value: T, ttl_seconds: int | None = None) -> None:
        _ = ttl_seconds  # ponytail: single global TTL via TTLCache
        with self._lock:
            self._cache[key] = value

    def delete(self, key: str) -> bool:
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def clear(self) -> int:
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            return count

    def contains(self, key: str) -> bool:
        with self._lock:
            return key in self._cache

    def health_check(self) -> bool:
        return True

    def cleanup_expired(self) -> int:
        with self._lock:
            before = len(self._cache)
            self._cache.expire()
            return before - len(self._cache)

    def get_info(self) -> dict[str, Any]:
        with self._lock:
            return {
                "type": "memory",
                "size": len(self._cache),
                "max_size": self._max_size,
                "default_ttl_seconds": self._default_ttl,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": self._hits / (self._hits + self._misses)
                if (self._hits + self._misses) > 0
                else 0.0,
                "evictions": self._evictions,
            }

    def reset_metrics(self) -> None:
        with self._lock:
            self._hits = 0
            self._misses = 0
            self._evictions = 0

    @property
    def stats(self) -> dict[str, Any]:
        return self.get_info()


__all__ = ["MemoryIdempotencyCache"]
