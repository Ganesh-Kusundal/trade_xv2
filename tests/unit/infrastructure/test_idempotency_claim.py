"""Atomic claim() on IdempotencyService — EventBus dedup spine."""

from __future__ import annotations

from infrastructure.idempotency.memory_cache import MemoryIdempotencyCache
from infrastructure.idempotency.service import IdempotencyService


def test_claim_first_succeeds_second_is_duplicate():
    svc = IdempotencyService(MemoryIdempotencyCache())
    assert svc.claim("evt-1", "evt-1") is True
    assert svc.claim("evt-1", "evt-1") is False
    assert svc.contains("evt-1") is True
