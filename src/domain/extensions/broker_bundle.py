"""Broker extension bundle and factory registry.

Typed interfaces for broker-specific capabilities that are not part of the
universal ``BrokerAdapter`` contract.  Callers acquire them through
``BrokerExtensionRegistry.require()`` — never through downcasts or isinstance
checks — so broker-specific power stays available without infecting common code.

Note: This is distinct from ``domain.extensions.registry.ExtensionRegistry``,
which handles instrument-centric capability discovery.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from domain.errors import UnsupportedExtensionError

T = TypeVar("T")

# ── Extension factory registry (replaces lazy imports in adapters/) ──────
# Broker modules register their bundle-building functions here at import
# time.  ``build_extension_bundle`` in adapters/extensions.py looks up
# this dict instead of importing broker-specific code directly.

_extension_factories: dict[str, Callable[..., ExtensionBundle]] = {}


def register_extension_factory(
    broker_id: str,
    factory: Callable[..., ExtensionBundle],
) -> None:
    """Register a broker's extension bundle factory.

    Called by broker modules (e.g. brokers/dhan/common_extensions.py)
    at module level so the factory is available when bootstrap runs.
    """
    _extension_factories[broker_id] = factory


def get_extension_factory(broker_id: str) -> Callable[..., ExtensionBundle] | None:
    """Return the registered factory for *broker_id*, or None."""
    return _extension_factories.get(broker_id)


class ExtensionBundle:
    """Holds all extensions registered for a single broker.

    Populated at broker bootstrap time; queried by ``BrokerExtensionRegistry``.
    """

    def __init__(self, broker_id: str) -> None:
        self._broker_id = broker_id
        self._extensions: dict[type, object] = {}

    def register(self, extension_type: type[T], implementation: T) -> None:
        """Register an extension implementation for the given interface type."""
        self._extensions[extension_type] = implementation

    def resolve(self, extension_type: type[T]) -> T | None:
        """Return the implementation or None if not registered."""
        return self._extensions.get(extension_type)  # type: ignore[return-value]

    def registered_names(self) -> frozenset[str]:
        """Return set of registered extension type names."""
        return frozenset(t.__name__ for t in self._extensions)


class BrokerExtensionRegistry:
    """Global registry mapping (broker_id, ExtensionType) → implementation.

    Populated during broker bootstrap by registering ``ExtensionBundle``s.
    Used by application-layer code and the router to acquire typed extensions.

    Renamed from the legacy ``ExtensionRegistry`` name to avoid clashing with
    ``domain.extensions.registry.ExtensionRegistry`` (instrument capabilities).
    """

    def __init__(self) -> None:
        self._bundles: dict[str, ExtensionBundle] = {}

    def register_bundle(self, broker_id: str, bundle: ExtensionBundle) -> None:
        """Register the full extension bundle for a broker."""
        self._bundles[broker_id] = bundle

    def resolve(self, broker_id: str, extension_type: type[T]) -> T | None:
        """Return the extension or None if not registered for this broker."""
        bundle = self._bundles.get(broker_id)
        if bundle is None:
            return None
        return bundle.resolve(extension_type)

    def require(self, broker_id: str, extension_type: type[T]) -> T:
        """Return the extension or raise ``UnsupportedExtensionError``.

        Automatically populates ``alternatives`` with brokers that do support
        the requested extension, so callers can reroute without additional
        registry lookups.
        """
        impl = self.resolve(broker_id, extension_type)
        if impl is not None:
            return impl
        alternatives = [
            bid
            for bid, bundle in self._bundles.items()
            if bid != broker_id and bundle.resolve(extension_type) is not None
        ]
        raise UnsupportedExtensionError(
            broker_id=broker_id,
            extension_name=extension_type.__name__,
            alternatives=alternatives,
        )

    def brokers_supporting(self, extension_type: type) -> list[str]:
        """Return broker_ids that have registered the given extension type."""
        return [
            bid
            for bid, bundle in self._bundles.items()
            if bundle.resolve(extension_type) is not None
        ]


# Facade-compat alias — historical name used by domain.extensions.broker_bundle
ExtensionRegistry = BrokerExtensionRegistry

__all__ = [
    "BrokerExtensionRegistry",
    "ExtensionBundle",
    "ExtensionRegistry",
    "get_extension_factory",
    "register_extension_factory",
]
