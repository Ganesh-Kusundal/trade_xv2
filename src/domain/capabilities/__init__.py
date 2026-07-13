"""Domain capability types.

- :mod:`domain.capabilities.enums` — ``Capability``, ``ConnectionStatus``
- :mod:`domain.capabilities.broker_capabilities` — full broker capability matrix
"""

from domain.capabilities.broker_capabilities import (
    BrokerCapabilities,
    CapabilityDescriptor,
    HistoricalWindowConstraint,
    RateLimitProfile,
    StreamLimitProfile,
)
from domain.capabilities.enums import Capability, ConnectionStatus
from domain.capabilities.market_surface import MarketCoverage, MarketSurface

__all__ = [
    "BrokerCapabilities",
    "Capability",
    "CapabilityDescriptor",
    "ConnectionStatus",
    "HistoricalWindowConstraint",
    "MarketCoverage",
    "MarketSurface",
    "RateLimitProfile",
    "StreamLimitProfile",
]
