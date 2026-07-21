"""Backward-compat facade — canonical: ``domain.capabilities.broker_capabilities``.

.. deprecated::
    Import from ``domain.capabilities.broker_capabilities`` directly.
"""

from __future__ import annotations

import warnings

warnings.warn(
    "brokers.common.broker_capabilities is deprecated; "
    "import from domain.capabilities.broker_capabilities",
    DeprecationWarning,
    stacklevel=2,
)

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
