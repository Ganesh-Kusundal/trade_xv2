"""Extension base class — broker-specific capabilities as composable plugins.

Each extension represents a single broker-specific feature (depth200,
forever_orders, etc.).  Extensions are registered at startup and
discovered at runtime via the ExtensionRegistry.

Domain code never imports broker-specific types — it queries extensions
by name and capability.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from domain.value_objects.capability import Capability

if TYPE_CHECKING:
    from domain.instruments.instrument_id import InstrumentId


class Extension(ABC):
    """Base class for broker-specific extensions.

    Every extension must declare:
    - ``name`` — unique identifier (e.g., ``"depth200"``)
    - ``broker`` — which broker it belongs to (e.g., ``"dhan"``)
    - ``version`` — semantic version for compatibility
    - ``capabilities`` — tuple of capabilities this extension provides
    - ``is_available_for()`` — runtime check for instrument compatibility

    Example::

        class Depth200Extension(Extension):
            name = "depth200"
            broker = "dhan"
            version = "1.0"
            capabilities = (Capability(name="depth_200", supported=True),)

            def is_available_for(self, instrument_id: object) -> bool:
                return True  # Available for all Dhan instruments
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique extension name (e.g., ``"depth200"``, ``"forever_orders"``)."""
        ...

    @property
    @abstractmethod
    def broker(self) -> str:
        """Broker this extension belongs to (e.g., ``"dhan"``, ``"upstox"``)."""
        ...

    @property
    @abstractmethod
    def version(self) -> str:
        """Extension version for compatibility checks."""
        ...

    @property
    @abstractmethod
    def capabilities(self) -> tuple[Capability, ...]:
        """Capabilities this extension provides."""
        ...

    @abstractmethod
    def is_available_for(self, instrument_id: InstrumentId) -> bool:
        """Check if this extension is available for a given instrument.

        Parameters
        ----------
        instrument_id:
            Canonical instrument identifier.

        Returns
        -------
        bool
            True if the extension can serve this instrument.
        """
        ...

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}("
            f"name={self.name!r}, broker={self.broker!r}, "
            f"version={self.version!r})"
        )
