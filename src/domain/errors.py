"""Domain-level error types — clean-architecture root for error handling.

The root ``TradeXV2Error`` lives in :mod:`domain.exceptions`. This module
defines the platform error hierarchy. Infrastructure and application code
classify errors through these types — never by importing broker packages.
Runtime helpers re-export selected types from ``infrastructure.resilience.errors``.
"""

from __future__ import annotations

from domain.exceptions import TradeXV2Error
from domain.ports.bootstrap import BootstrapResult, BootstrapStatus


class BrokerError(TradeXV2Error):
    """Base exception for all broker communication errors."""


class RetryableError(BrokerError):
    """An error that can be retried (transient failure)."""


# Alias used by the retry framework and global exception handler
TradeXV2RecoverableError = RetryableError


class NonRetryableError(BrokerError):
    """An error that should NOT be retried (permanent failure)."""


class RateLimitError(BrokerError):
    """Rate limit exceeded (429 / throttled)."""


class CircuitBreakerOpenError(BrokerError):
    """The circuit breaker is open — request not allowed."""

    def __init__(self, name: str):
        self.circuit_name = name
        super().__init__(f"Circuit breaker '{name}' is open")


class AuthenticationError(BrokerError):
    """Authentication or authorization failure."""


class InstrumentError(BrokerError):
    """Instrument resolution or validation failure."""


class InstrumentNotFoundError(InstrumentError):
    """Requested instrument not found."""


class MappingError(BrokerError):
    """Symbol or security-id mapping failure."""


class NotSupportedError(BrokerError):
    """Feature not supported by broker."""


class OrderError(BrokerError):
    """Order placement, modification, or cancellation error."""


class RejectedOrderError(OrderError):
    """Order rejected by broker or exchange."""


class CapabilityError(NotSupportedError):
    """Broker capability unavailable or misconfigured."""


class ExitAllError(NotSupportedError):
    """Exit-all (kill switch) operation failed."""


class BrokerDegradedError(BrokerError):
    """All brokers are unavailable; system is in degraded mode."""

    def __init__(
        self,
        message: str = "All brokers are unavailable; system is in degraded mode",
        health_status: dict[str, dict] | None = None,
    ) -> None:
        super().__init__(message)
        self.health_status = health_status or {}


class NetworkError(RetryableError):
    """Network-level failure (connection reset, DNS, timeout)."""


class BrokerNotReadyError(TradeXV2Error):
    """Raised when a broker gateway is unavailable or not authenticated."""

    def __init__(
        self,
        message: str,
        *,
        broker: str,
        status: BootstrapStatus,
        bootstrap: BootstrapResult | None = None,
    ) -> None:
        super().__init__(message)
        self.broker = broker
        self.status = status
        self.bootstrap = bootstrap

    @classmethod
    def from_bootstrap(cls, result: BootstrapResult) -> BrokerNotReadyError:
        return cls(
            result.error or f"{result.broker} bootstrap failed: {result.status.value}",
            broker=result.broker,
            status=result.status,
            bootstrap=result,
        )


class NotConfiguredError(TradeXV2Error):
    """Raised when a domain object is used without required composition-root wiring."""


# ---------------------------------------------------------------------------
# Errors merged from tradex/runtime/errors.py (routing / quota / coordination)
# ---------------------------------------------------------------------------


class BrokerUnavailableError(TradeXV2Error, RuntimeError):
    """Raised when a broker is not registered or its health is not usable."""

    def __init__(self, broker_id: str, *, reason: str = "") -> None:
        self.broker_id = broker_id
        self.reason = reason
        super().__init__(
            f"Broker {broker_id!r} unavailable: {reason}"
            if reason
            else f"Broker {broker_id!r} unavailable"
        )


class UnsupportedExtensionError(TradeXV2Error, NotImplementedError):
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


class MergeConflictError(TradeXV2Error, ValueError):
    """Raised when overlapping historical data sources have irreconcilable conflicts."""

    def __init__(self, conflict_count: int, chunk_ids: list[str]) -> None:
        self.conflict_count = conflict_count
        self.chunk_ids = chunk_ids
        super().__init__(f"{conflict_count} merge conflict(s) in chunks: {chunk_ids}")


class RoutingError(TradeXV2Error, RuntimeError):
    """Raised when no eligible broker can be selected for a routing request."""

    def __init__(self, operation: str, reason: str) -> None:
        self.operation = operation
        self.reason = reason
        super().__init__(f"Cannot route {operation}: {reason}")


class QuotaExhaustedError(TradeXV2Error, RuntimeError):
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


# ---------------------------------------------------------------------------
# Errors merged from tradex/runtime/gateway_errors.py
# ---------------------------------------------------------------------------


class UnsupportedGatewayOperationError(NotImplementedError, TradeXV2Error):
    """Raised when a gateway does not implement a contract method."""

    def __init__(self, gateway: str, operation: str) -> None:
        super().__init__(f"{gateway} does not support {operation}")
        self.gateway = gateway
        self.operation = operation
