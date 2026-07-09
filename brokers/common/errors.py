"""Broker error types — canonical definitions for common error classes.

These error classes were previously scattered across multiple modules and
are now consolidated here.  All broker-common code should import from
this module.  Domain-level error types live in ``domain.errors``.
"""

from __future__ import annotations

from typing import Any

from brokers.common.resilience.errors import BrokerError  # noqa: F401 — re-export


class BrokerUnavailableError(RuntimeError):
    """Raised when a broker is not registered or its health is not usable."""

    def __init__(self, broker_id: str, *, reason: str = "") -> None:
        self.broker_id = broker_id
        self.reason = reason
        super().__init__(f"Broker {broker_id!r} unavailable: {reason}" if reason else f"Broker {broker_id!r} unavailable")


class UnsupportedExtensionError(NotImplementedError):
    """Raised when a broker does not support a requested extension."""

    def __init__(
        self,
        broker_id: str,
        extension_name: str,
        alternatives: list[str] | None = None,
    ) -> None:
        self.broker_id = broker_id
        self.extension_name = extension_name
        self.alternatives = alternatives or []
        msg = f"Broker {broker_id!r} does not support {extension_name}"
        if self.alternatives:
            msg += f"; alternatives: {', '.join(self.alternatives)}"
        super().__init__(msg)


class MergeConflictError(ValueError):
    """Raised when overlapping historical data sources have irreconcilable conflicts."""

    def __init__(self, conflict_count: int, chunk_ids: list[str]) -> None:
        self.conflict_count = conflict_count
        self.chunk_ids = chunk_ids
        super().__init__(f"{conflict_count} merge conflict(s) in chunks: {chunk_ids}")


class RoutingError(RuntimeError):
    """Raised when no eligible broker can be selected for a routing request."""

    def __init__(self, operation: str, reason: str) -> None:
        self.operation = operation
        self.reason = reason
        super().__init__(f"Cannot route {operation}: {reason}")


class QuotaExhaustedError(RuntimeError):
    """Raised when API quota is exhausted and the wait deadline has passed."""

    def __init__(
        self,
        broker_id: str,
        endpoint_class: str,
        priority_class: str = "",
        retry_after_seconds: float | None = None,
    ) -> None:
        self.broker_id = broker_id
        self.endpoint_class = endpoint_class
        self.priority_class = priority_class
        self.retry_after_seconds = retry_after_seconds
        msg = f"Quota exhausted for {broker_id!r}/{endpoint_class}"
        if priority_class:
            msg += f" (priority={priority_class})"
        if retry_after_seconds:
            msg += f"; retry after {retry_after_seconds:.1f}s"
        super().__init__(msg)
