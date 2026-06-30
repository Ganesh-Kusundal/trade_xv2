"""Custom exceptions for the resilience module and TradeXV2 core."""

from __future__ import annotations


class TradeXV2Error(Exception):
    """Root exception for all TradeXV2 errors."""


class BrokerError(TradeXV2Error):
    """Base exception for all broker errors."""


class RetryableError(BrokerError):
    """An error that can be retried (transient failure)."""


# Alias used by the centralized retry framework (infrastructure.retry)
# and the global exception handler to distinguish retryable (transient)
# errors from fatal ones.
TradeXV2RecoverableError = RetryableError


class NonRetryableError(BrokerError):
    """An error that should NOT be retried (permanent failure)."""


class RateLimitError(BrokerError):
    """Rate limit exceeded."""


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
    """Feature not supported by broker (replaces NotImplementedError at boundaries)."""


class ExitAllError(NotSupportedError):
    """Exit-all (kill switch) operation failed."""


class DataError(TradeXV2Error):
    """Base exception for datalake and data processing errors."""


class ConfigError(TradeXV2Error):
    """Configuration error (missing or invalid settings)."""


class ValidationError(TradeXV2Error):
    """Input validation error."""


class BrokerDegradedError(BrokerError):
    """All brokers are unavailable and the system is in degraded mode.

    Raised when a write operation (e.g. order placement) is attempted
    while every configured broker is unhealthy. Read operations may
    return stale cached data instead of raising, depending on the
    caller's tolerance for stale data.
    """

    def __init__(
        self,
        message: str = "All brokers are unavailable; system is in degraded mode",
        health_status: dict[str, dict] | None = None,
    ) -> None:
        super().__init__(message)
        self.health_status = health_status or {}
