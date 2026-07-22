"""In-memory IdempotencyGuard — NEW | PENDING | DUPLICATE; thread-safe dict."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from enum import Enum
from typing import Any

from domain.value_objects import CorrelationId


class IdempotencyStatus(Enum):
    NEW = "NEW"
    PENDING = "PENDING"
    DUPLICATE = "DUPLICATE"


@dataclass(frozen=True, slots=True)
class IdempotencyResult:
    status: IdempotencyStatus
    prior_result: Any | None = None


# Sentinel to distinguish "reserved, no result yet" from "completed with None"
_PENDING = object()


class IdempotencyGuard:
    """ponytail: process-local dict; ceiling = single node. Upgrade: Redis/shared store."""

    def __init__(self) -> None:
        self._store: dict[str, Any] = {}
        self._lock = threading.Lock()

    def check_and_reserve(self, correlation_id: CorrelationId) -> IdempotencyResult:
        key = self._key(correlation_id)
        with self._lock:
            if key in self._store:
                entry = self._store[key]
                if entry is _PENDING:
                    return IdempotencyResult(status=IdempotencyStatus.PENDING)
                return IdempotencyResult(
                    status=IdempotencyStatus.DUPLICATE,
                    prior_result=entry,
                )
            self._store[key] = _PENDING
            return IdempotencyResult(status=IdempotencyStatus.NEW)

    def record_result(self, correlation_id: CorrelationId, result: Any) -> None:
        key = self._key(correlation_id)
        with self._lock:
            if key not in self._store:
                raise ValueError(f"correlation_id not reserved: {key}")
            self._store[key] = result

    @staticmethod
    def _key(correlation_id: CorrelationId | None) -> str:
        if correlation_id is None:
            raise ValueError("correlation_id is mandatory")
        value = getattr(correlation_id, "value", None)
        if value is None:
            raise ValueError("correlation_id is mandatory")
        return str(value)
