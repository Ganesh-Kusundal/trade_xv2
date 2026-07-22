"""IdempotencyGuard: NEW / PENDING / DUPLICATE lifecycle; fail closed on None."""

from __future__ import annotations

import threading
from uuid import uuid4

import pytest

from domain.value_objects import CorrelationId
from domain.ports.types import OrderResult
from domain.value_objects import OrderId
from infrastructure.idempotency import IdempotencyGuard, IdempotencyResult, IdempotencyStatus


def _cid() -> CorrelationId:
    return CorrelationId(value=uuid4())


# --- NEW / PENDING / DUPLICATE lifecycle ---


def test_new_returns_new() -> None:
    guard = IdempotencyGuard()
    r = guard.check_and_reserve(_cid())
    assert r.status is IdempotencyStatus.NEW
    assert r.prior_result is None


def test_reserved_returns_pending() -> None:
    guard = IdempotencyGuard()
    cid = _cid()
    guard.check_and_reserve(cid)
    r = guard.check_and_reserve(cid)
    assert r.status is IdempotencyStatus.PENDING


def test_completed_returns_duplicate() -> None:
    guard = IdempotencyGuard()
    cid = _cid()
    guard.check_and_reserve(cid)
    prior = OrderResult(order_id=OrderId(value="o-1"), success=True, message="filled")
    guard.record_result(cid, prior)
    r = guard.check_and_reserve(cid)
    assert r.status is IdempotencyStatus.DUPLICATE
    assert r.prior_result == prior


def test_duplicate_includes_prior_result() -> None:
    guard = IdempotencyGuard()
    cid = _cid()
    guard.check_and_reserve(cid)
    prior = {"order_id": "o-99", "ok": True}
    guard.record_result(cid, prior)
    r = guard.check_and_reserve(cid)
    assert r.prior_result == prior


def test_record_result_stores_result() -> None:
    guard = IdempotencyGuard()
    cid = _cid()
    guard.check_and_reserve(cid)
    prior = OrderResult(order_id=OrderId(value="o-42"), success=False, message="rejected")
    guard.record_result(cid, prior)
    r = guard.check_and_reserve(cid)
    assert r.prior_result == prior
    assert r.prior_result.message == "rejected"


# --- Missing / invalid correlation_id ---


def test_none_raises() -> None:
    guard = IdempotencyGuard()
    with pytest.raises((ValueError, TypeError)):
        guard.check_and_reserve(None)  # type: ignore[arg-type]


def test_record_before_reserve_raises() -> None:
    guard = IdempotencyGuard()
    cid = _cid()
    with pytest.raises(ValueError):
        guard.record_result(cid, "result")


# --- Thread safety ---


def test_concurrent_check_and_reserve() -> None:
    guard = IdempotencyGuard()
    cid = _cid()
    results: list[IdempotencyResult] = []
    barrier = threading.Barrier(10)

    def worker() -> None:
        barrier.wait()
        results.append(guard.check_and_reserve(cid))

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    new_count = sum(1 for r in results if r.status is IdempotencyStatus.NEW)
    pending_count = sum(1 for r in results if r.status is IdempotencyStatus.PENDING)
    assert new_count == 1, f"expected exactly 1 NEW, got {new_count}"
    assert pending_count == 9, f"expected 9 PENDING, got {pending_count}"
