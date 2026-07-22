"""IdempotencyGuard protocol — duplicate command detection."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from domain.ports.types import IdempotencyResult, OrderResult
from domain.value_objects import CorrelationId


@runtime_checkable
class IdempotencyGuard(Protocol):
    def check_and_reserve(self, correlation_id: CorrelationId) -> IdempotencyResult: ...
    def record_result(
        self, correlation_id: CorrelationId, result: OrderResult
    ) -> None: ...
