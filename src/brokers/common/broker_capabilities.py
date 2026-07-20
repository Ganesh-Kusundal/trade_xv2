"""Backward-compat facade — canonical: ``domain.capabilities.broker_capabilities``."""

from domain.capabilities.broker_capabilities import (
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
