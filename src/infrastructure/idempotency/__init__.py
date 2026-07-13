"""Idempotency module for durable operation caching.

Canonical location: ``infrastructure.idempotency``.

Components:
- IdempotencyService: Main interface for idempotency operations
- MemoryIdempotencyCache: In-memory implementation (development/testing)

Usage:
    from infrastructure.idempotency import IdempotencyService, MemoryIdempotencyCache

    cache = MemoryIdempotencyCache()
    service = IdempotencyService(cache)
"""

from __future__ import annotations

from infrastructure.idempotency.memory_cache import MemoryIdempotencyCache
from infrastructure.idempotency.service import IdempotencyService

__all__ = [
    "IdempotencyService",
    "MemoryIdempotencyCache",
]
