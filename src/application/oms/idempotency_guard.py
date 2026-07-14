"""Idempotency guard for the OMS OrderManager.

Owns pending correlation ids during placement so concurrent callers with the
same id see an ``already in-flight`` error instead of double-submitting.

In-memory map is the hot cache. Durable recovery (F6) is via an optional
``durable_lookup`` that consults the execution ledger / order store so a
restart cannot double-submit the same correlation_id.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from domain.constants import SECONDS_PER_DAY

if TYPE_CHECKING:
    from application.oms.order_manager import OrderResult
    from domain.entities import Order

_PENDING_TTL = SECONDS_PER_DAY  # 24 hours — long enough for any real placement session


class _PendingStore:
    """Thread-safe TTL map for in-flight correlation ids (stdlib only)."""

    def __init__(self, default_ttl: float = _PENDING_TTL) -> None:
        self._default_ttl = default_ttl
        self._data: dict[str, tuple[Any, float]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return None
            value, expires = item
            if expires < time.monotonic():
                del self._data[key]
                return None
            return value

    def put(self, key: str, value: Any, ttl_seconds: float | None = None) -> None:
        ttl = self._default_ttl if ttl_seconds is None else float(ttl_seconds)
        with self._lock:
            self._data[key] = (value, time.monotonic() + ttl)

    def delete(self, key: str) -> bool:
        with self._lock:
            return self._data.pop(key, None) is not None


class IdempotencyGuard:
    """Thread-safe idempotency guard for order placement.

    The caller is responsible for acquiring and releasing the shared lock;
    the guard provides the check/reserve/release logic.
    """

    def __init__(
        self,
        pending: _PendingStore | None = None,
        durable_lookup: Callable[[str], Order | None] | None = None,
    ) -> None:
        self._pending = pending if pending is not None else _PendingStore()
        # F6: optional ledger/store lookup — returns a recovered Order or None.
        self._durable_lookup = durable_lookup

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
        from domain.execution_contracts import SubmissionState
        from domain.types import OrderStatus

        with lock:
            existing = orders_by_correlation.get(correlation_id)
            if existing is None and self._durable_lookup is not None:
                # Hot-cache miss: recover from durable ledger/store (F6).
                durable = self._durable_lookup(correlation_id)
                if durable is not None:
                    orders_by_correlation[correlation_id] = durable
                    existing = durable
            if existing is not None:
                if existing.status is OrderStatus.UNKNOWN:
                    return "", OrderResult(
                        success=False,
                        order=existing,
                        error="Order submission outcome is unknown; reconcile before retry",
                        state=SubmissionState.UNKNOWN,
                    )
                return "", OrderResult(
                    success=True,
                    order=existing,
                    state=SubmissionState.ACCEPTED,
                )
            if self._pending.get(correlation_id) is not None:
                return "", OrderResult(success=False, error="Order already in-flight")
            self._pending.put(correlation_id, True, ttl_seconds=_PENDING_TTL)
            order_id = f"OM-{uuid.uuid4().hex[:12]}"
        return order_id, None

    def release_pending(
        self,
        lock: threading.RLock,
        correlation_id: str,
    ) -> None:
        """Remove the correlation ID from the pending set (under lock)."""
        with lock:
            self._pending.delete(correlation_id)
