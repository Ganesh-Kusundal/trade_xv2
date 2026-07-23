"""Tests for the v2 IdempotencyCache port of the legacy reserve/commit protocol."""

from __future__ import annotations

from plugins.brokers.common.idempotency import IdempotencyCache


def test_reserve_then_dup_reserve_returns_false() -> None:
    cache: IdempotencyCache[int] = IdempotencyCache()
    assert cache.reserve("a") is True
    # Already reserved -> second reserve must fail.
    assert cache.reserve("a") is False


def test_commit_then_get_returns_value() -> None:
    cache: IdempotencyCache[str] = IdempotencyCache()
    assert cache.reserve("a") is True
    cache.commit("a", "result")
    assert cache.get("a") == "result"
    # After commit the cid is committed -> reserve must fail.
    assert cache.reserve("a") is False


def test_clear_reservation_allows_re_reserve() -> None:
    cache: IdempotencyCache[int] = IdempotencyCache()
    assert cache.reserve("a") is True
    # POST was never sent -> drop the reservation only.
    cache.clear_reservation("a")
    # Re-reserve now succeeds.
    assert cache.reserve("a") is True


def test_clear_reservation_does_not_drop_commit() -> None:
    cache: IdempotencyCache[int] = IdempotencyCache()
    assert cache.reserve("a") is True
    cache.commit("a", 42)
    # clear_reservation must NOT remove a committed value.
    cache.clear_reservation("a")
    assert cache.get("a") == 42


def test_reserve_expired_reservation_can_re_reserve() -> None:
    cache: IdempotencyCache[int] = IdempotencyCache(ttl=0.0)
    assert cache.reserve("a") is True
    # TTL of 0 means the reservation is immediately expired.
    assert cache.reserve("a") is True
