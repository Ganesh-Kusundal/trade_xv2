"""Acceptance test: idempotent place (spec §11.3).

Double place with same correlation_id must produce only one venue submit.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from domain import Order
from domain.enums import OrderStatus
from domain.types import OrderType, ProductType, Side, Validity


def _make_order(correlation_id: str = "corr-1") -> Order:
    return Order(
        order_id="",
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        quantity=10,
        price=2500.0,
        trigger_price=0.0,
        product_type=ProductType.CNC,
        validity=Validity.DAY,
        status=OrderStatus.OPEN,
        timestamp=datetime.now(timezone.utc),
        correlation_id=correlation_id,
    )


def test_idempotency_guard_prevents_double_submit():
    """IdempotencyGuard.check_and_reserve rejects duplicate correlation_id."""
    import threading

    from application.oms.idempotency_guard import IdempotencyGuard

    guard = IdempotencyGuard()
    lock = threading.RLock()
    orders_by_corr: dict = {}

    order_id_1, result_1 = guard.check_and_reserve(lock, orders_by_corr, "corr-1")
    assert result_1 is None
    assert order_id_1 != ""

    order_id_2, result_2 = guard.check_and_reserve(lock, orders_by_corr, "corr-1")
    assert order_id_2 == ""
    assert result_2 is not None
    assert "in-flight" in result_2.error


def test_idempotency_guard_returns_existing_order():
    """When an order already exists for correlation_id, guard returns it."""
    import threading

    from application.oms.idempotency_guard import IdempotencyGuard

    guard = IdempotencyGuard()
    lock = threading.RLock()

    existing_order = MagicMock()
    existing_order.status = OrderStatus.OPEN
    orders_by_corr = {"corr-1": existing_order}

    order_id, result = guard.check_and_reserve(lock, orders_by_corr, "corr-1")
    assert order_id == ""
    assert result is not None
    assert result.success is True
    assert result.order is existing_order


def test_idempotency_guard_blocks_concurrent_inflight():
    """While a correlation_id is in-flight, a second attempt is rejected."""
    import threading

    from application.oms.idempotency_guard import IdempotencyGuard

    guard = IdempotencyGuard()
    lock = threading.RLock()
    orders_by_corr: dict = {}

    order_id_1, result_1 = guard.check_and_reserve(lock, orders_by_corr, "corr-1")
    assert result_1 is None

    order_id_2, result_2 = guard.check_and_reserve(lock, orders_by_corr, "corr-1")
    assert order_id_2 == ""
    assert result_2 is not None
    assert "in-flight" in result_2.error


def test_idempotency_guard_release_allows_retry():
    """After release_pending, the same correlation_id can be re-reserved."""
    import threading

    from application.oms.idempotency_guard import IdempotencyGuard

    guard = IdempotencyGuard()
    lock = threading.RLock()
    orders_by_corr: dict = {}

    order_id_1, _ = guard.check_and_reserve(lock, orders_by_corr, "corr-1")
    guard.release_pending(lock, "corr-1")

    order_id_2, result_2 = guard.check_and_reserve(lock, orders_by_corr, "corr-1")
    assert result_2 is None
    assert order_id_2 != ""


def test_different_correlation_ids_are_independent():
    """Different correlation_ids don't interfere with each other."""
    import threading

    from application.oms.idempotency_guard import IdempotencyGuard

    guard = IdempotencyGuard()
    lock = threading.RLock()
    orders_by_corr: dict = {}

    id_1, r1 = guard.check_and_reserve(lock, orders_by_corr, "corr-A")
    id_2, r2 = guard.check_and_reserve(lock, orders_by_corr, "corr-B")

    assert r1 is None
    assert r2 is None
    assert id_1 != id_2
