"""Domain-level error types — clean-architecture root for error handling.

The root ``TradeXV2Error`` lives in :mod:`domain.exceptions`. This module
defines the full error hierarchy that was previously scattered across
``brokers.common.resilience.errors``. Infrastructure and application code
classify errors through these types — never by importing broker modules.

The broker module (``brokers.common.resilience.errors``) re-exports these
classes for backward compatibility, so existing ``except BrokerError`` clauses
continue to work. The import direction is now correct: domain defines,
infrastructure imports.
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


class InstrumentNotFoundError(BrokerError):
    """Requested instrument not found."""


class OrderError(BrokerError):
    """Order placement, modification, or cancellation error."""


class NotSupportedError(BrokerError):
    """Feature not supported by broker."""


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
