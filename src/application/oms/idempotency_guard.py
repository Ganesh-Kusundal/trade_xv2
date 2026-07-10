"""Idempotency guard for the OMS OrderManager.

Extracted from :class:`application.oms.order_manager.OrderManager` god class.
Owns the ``_pending_correlation`` set and provides atomic check/reserve/release
operations that prevent duplicate order placement for the same correlation id.
"""

from __future__ import annotations

import threading
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from application.oms.order_manager import OmsOrderCommand, OrderResult
    from domain.entities import Order


class IdempotencyGuard:
    """Thread-safe idempotency guard for order placement.

    Maintains a ``_pending_correlation`` set of correlation ids that are
    currently being placed.  Concurrent callers with the same id see an
    ``"already in-flight"`` error instead of double-submitting.

    The caller is responsible for acquiring and releasing the shared lock;
    the guard provides the check/reserve/release logic.
    """

    def __init__(self) -> None:
        self._pending_correlation: set[str] = set()

    def check_and_reserve(
        self,
        lock: threading.RLock,
        orders_by_correlation: dict[str, Order],
        correlation_id: str,
    ) -> tuple[str, OrderResult | None]:
        """Phase 1: Check idempotency and reserve the correlation ID (under lock).

        Returns (order_id, None) on success, or ('', OrderResult) if the
        order is a duplicate or already in-flight.
        """
        from application.oms.order_manager import OrderResult

        with lock:
            existing = orders_by_correlation.get(correlation_id)
            if existing is not None:
                return "", OrderResult(success=True, order=existing)
            if correlation_id in self._pending_correlation:
                return "", OrderResult(success=False, error="Order already in-flight")
            self._pending_correlation.add(correlation_id)
            order_id = f"OM-{uuid.uuid4().hex[:12]}"
        return order_id, None

    def release_pending(
        self,
        lock: threading.RLock,
        correlation_id: str,
    ) -> None:
        """Remove the correlation ID from the pending set (under lock)."""
        with lock:
            self._pending_correlation.discard(correlation_id)
