"""Custom exceptions for the resilience module."""

from __future__ import annotations


class BrokerError(Exception):
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
