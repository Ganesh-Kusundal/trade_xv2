"""Value objects — capability and extension info types.

Re-exports rich broker capability model from ``brokers.common`` AND
provides the lightweight ``Capability`` enum and ``ExtensionInfo``
descriptor used throughout domain and application code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from brokers.common.broker_capabilities import (  # noqa: F401
    BrokerCapabilities,
    CapabilityDescriptor,
    HistoricalWindowConstraint,
    RateLimitProfile,
    StreamLimitProfile,
)
from domain.capabilities import Capability  # noqa: F401


@dataclass(frozen=True)
class ExtensionInfo:
    """Lightweight descriptor for a broker extension.

    Returned by ``ExtensionRegistry.info_for()`` so callers can
    discover what extensions are available without importing
    broker-specific code.

    Attributes
    ----------
    name:
        Unique extension identifier (e.g. ``"depth200"``).
    broker:
        Broker this extension belongs to (e.g. ``"dhan"``).
    version:
        Semantic version of the extension.
    capabilities:
        Tuple of capabilities this extension provides.
    """

    name: str
    broker: str
    version: str
    capabilities: tuple[Capability, ...] = field(default_factory=tuple)


__all__ = [
    "BrokerCapabilities",
    "Capability",
    "CapabilityDescriptor",
    "ExtensionInfo",
    "HistoricalWindowConstraint",
    "RateLimitProfile",
    "StreamLimitProfile",
]
