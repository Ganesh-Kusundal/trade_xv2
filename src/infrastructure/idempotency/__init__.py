"""Idempotency module for durable operation caching.

Canonical location: ``infrastructure.idempotency``.

Components:
- IdempotencyService: Main interface for idempotency operations
- RedisIdempotencyCache: Primary implementation using Redis (production)
- FileIdempotencyCache: Fallback implementation using file system
- MemoryIdempotencyCache: In-memory implementation (development/testing)

Usage:
    from infrastructure.idempotency import IdempotencyService, RedisIdempotencyCache

    cache = RedisIdempotencyCache(host='localhost', port=6379)
    service = IdempotencyService(cache)
"""

from __future__ import annotations

from infrastructure.idempotency.file_cache import FileIdempotencyCache
from infrastructure.idempotency.memory_cache import MemoryIdempotencyCache
from infrastructure.idempotency.redis_cache import RedisIdempotencyCache
from infrastructure.idempotency.service import IdempotencyService

__all__ = [
    "IdempotencyService",
    "RedisIdempotencyCache",
    "FileIdempotencyCache",
    "MemoryIdempotencyCache",
]
