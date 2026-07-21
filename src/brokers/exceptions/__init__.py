"""Brokers exceptions — broker-access exception hierarchy.

Reuses the canonical domain error types and adds broker-scoped wrappers only
where the domain layer does not already cover the case.
"""

from __future__ import annotations

from domain.connect_errors import ConnectError
from domain.exceptions import BrokerError, CapabilityError, NotConfiguredError
from domain.exceptions import (
    ConfigError,
    DataError,
    ExchangeNotConfigured,
    LiveBrokerBlockedError,
    TradeXV2Error,
    ValidationError,
)


class BrokerNotAvailable(BrokerError):
    """Raised when a requested broker plugin is not registered/available."""


# Deprecated alias — use domain.errors.CapabilityError
CapabilityNotSupported = CapabilityError


__all__ = [
    "BrokerError",
    "BrokerNotAvailable",
    "CapabilityNotSupported",
    "ConfigError",
    "ConnectError",
    "DataError",
    "ExchangeNotConfigured",
    "LiveBrokerBlockedError",
    "NotConfiguredError",
    "TradeXV2Error",
    "ValidationError",
]
