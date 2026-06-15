"""Dhan broker exceptions."""

from __future__ import annotations


class DhanError(Exception):
    """Base exception for all Dhan broker errors."""


class InstrumentNotFoundError(DhanError):
    """Instrument not found in resolver cache."""


class MarketDataError(DhanError):
    """Market data fetch failure."""


class OrderError(DhanError):
    """Order placement/modification/cancellation failure."""


class AuthenticationError(DhanError):
    """Token expired or rejected."""


class RateLimitError(DhanError):
    """Rate limit exceeded."""


class ConfigurationError(DhanError):
    """Missing or invalid configuration."""
