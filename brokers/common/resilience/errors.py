"""Custom exceptions for the resilience module and TradeXV2 core."""

from __future__ import annotations


class TradeXV2Error(Exception):
    """Root exception for all TradeXV2 errors."""


class BrokerError(TradeXV2Error):
    """Base exception for all broker errors."""


class RetryableError(BrokerError):
    """An error that can be retried (transient failure)."""


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
