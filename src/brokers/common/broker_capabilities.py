"""Backward-compat facade — canonical: ``domain.capabilities.broker_capabilities``."""

from domain.capabilities.broker_capabilities import (  # noqa: F401
    BrokerCapabilities,
    CapabilityDescriptor,
    HistoricalWindowConstraint,
    RateLimitProfile,
    StreamLimitProfile,
)

__all__ = [
    "BrokerCapabilities",
    "CapabilityDescriptor",
    "HistoricalWindowConstraint",
    "RateLimitProfile",
    "StreamLimitProfile",
]
