"""Capability and ExtensionInfo value objects.

Runtime-discoverable capability model that replaces the hardcoded
``Capability`` enum in ``domain.capabilities``.  Extensions register
their capabilities at startup; domain code queries by name.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class Capability:
    """A single capability that an instrument or provider supports.

    Replaces the hardcoded ``Capability`` enum with a runtime-discoverable
    model.  Each Capability is a simple name + supported flag + metadata bag.

    Examples::

        Capability(name="depth_200", supported=True)
        Capability(name="forever_orders", supported=True, metadata={"max_orders": 200})
    """

    name: str
    supported: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def __bool__(self) -> bool:
        """Capability is truthy when supported."""
        return self.supported


@dataclass(frozen=True, slots=True)
class ExtensionInfo:
    """Lightweight descriptor for a registered extension — Value Object.

    Carries identity and metadata about an extension without the
    extension's actual implementation.  Useful for listing available
    capabilities without importing broker-specific code.
    """

    name: str
    broker: str
    version: str = "1.0"
    capabilities: tuple[Capability, ...] = ()

    def has_capability(self, cap_name: str) -> bool:
        """Check if this extension provides a named capability."""
        return any(c.name == cap_name for c in self.capabilities)

    def capability_names(self) -> tuple[str, ...]:
        """Return just the capability names."""
        return tuple(c.name for c in self.capabilities)
