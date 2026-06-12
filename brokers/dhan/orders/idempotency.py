"""In-memory idempotency cache for broker order placement."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Generic, TypeVar

from brokers.common.api.ports import IdempotencyCachePort

T = TypeVar("T")


class InMemoryIdempotencyCache(IdempotencyCachePort[T], Generic[T]):
    """Small TTL-backed idempotency cache."""

    def __init__(self, ttl_seconds: int = 300) -> None:
        self._ttl = timedelta(seconds=ttl_seconds)
        self._values: dict[str, tuple[T, datetime]] = {}

    def get(self, key: str) -> T | None:
        item = self._values.get(key)
        if item is None:
            return None
        value, expires_at = item
        if expires_at <= datetime.now():
            self._values.pop(key, None)
            return None
        return value

    def put(self, key: str, value: T) -> None:
        self._values[key] = (value, datetime.now() + self._ttl)

    def clear(self) -> None:
        self._values.clear()
