"""Extension Registry — runtime discovery of broker-specific capabilities.

Extensions are registered during startup.  Domain and application code
queries the registry to discover what capabilities are available for
a given instrument — without ever importing broker-specific code.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any

from domain.value_objects.capability import Capability, ExtensionInfo

if TYPE_CHECKING:
    from domain.instruments.instrument_id import InstrumentId


class ExtensionRegistry:
    """Registry for all broker-specific extensions.

    Usage::

        registry = ExtensionRegistry()
        registry.register(Depth200Extension(dhan_client))
        registry.register(ForeverOrderExtension(dhan_client))

        # Query by name
        ext = registry.get("depth200")

        # Query capabilities for an instrument
        caps = registry.capabilities_for(instrument_id)
    """

    def __init__(self) -> None:
        self._extensions: dict[str, Any] = {}
        self._lock = threading.Lock()

    # ── Registration ────────────────────────────────────────────────

    def register(self, extension: Any) -> None:
        """Register an extension.  Call during startup.

        Parameters
        ----------
        extension:
            An object implementing the Extension interface (name, broker,
            version, capabilities, is_available_for).
        """
        with self._lock:
            self._extensions[extension.name] = extension

    def unregister(self, name: str) -> bool:
        """Remove an extension by name.

        Returns True if the extension was found and removed.
        """
        with self._lock:
            return self._extensions.pop(name, None) is not None

    # ── Lookup ──────────────────────────────────────────────────────

    def get(self, name: str) -> Any | None:
        """Get an extension by name, or None if not found."""
        return self._extensions.get(name)

    def has(self, name: str) -> bool:
        """Check if an extension is registered."""
        return name in self._extensions

    # ── Discovery ───────────────────────────────────────────────────

    def available_for(self, instrument_id: InstrumentId) -> list[Any]:
        """Get all extensions available for a given instrument.

        Parameters
        ----------
        instrument_id:
            Canonical instrument identifier.
        """
        return [ext for ext in self._extensions.values() if ext.is_available_for(instrument_id)]

    def capabilities_for(self, instrument_id: InstrumentId) -> list[Capability]:
        """Get all capabilities available for a given instrument.

        Parameters
        ----------
        instrument_id:
            Canonical instrument identifier.
        """
        caps: list[Capability] = []
        for ext in self.available_for(instrument_id):
            caps.extend(ext.capabilities)
        return caps

    def info_for(self, instrument_id: InstrumentId) -> list[ExtensionInfo]:
        """Get lightweight descriptors for all extensions available for an instrument."""
        return [
            ExtensionInfo(
                name=ext.name,
                broker=ext.broker,
                version=ext.version,
                capabilities=ext.capabilities,
            )
            for ext in self.available_for(instrument_id)
        ]

    # ── Introspection ───────────────────────────────────────────────

    def list_names(self) -> list[str]:
        """List all registered extension names."""
        return list(self._extensions.keys())

    def list_by_broker(self, broker: str) -> list[Any]:
        """List all extensions for a given broker."""
        return [ext for ext in self._extensions.values() if ext.broker == broker]

    @property
    def count(self) -> int:
        """Number of registered extensions."""
        return len(self._extensions)

    def __repr__(self) -> str:
        return f"ExtensionRegistry({self.list_names()})"
