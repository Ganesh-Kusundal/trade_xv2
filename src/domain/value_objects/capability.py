"""Value objects — capability and extension info types.

Provides the lightweight ``Capability`` enum and ``ExtensionInfo``
descriptor used throughout domain and application code.

The rich broker capability matrix lives in
``domain.capabilities.broker_capabilities``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

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
    "Capability",
    "ExtensionInfo",
]
