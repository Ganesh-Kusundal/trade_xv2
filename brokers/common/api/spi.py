"""Service-provider interfaces for broker integrations.

This module mirrors Trade_J's SPI concepts while staying idiomatic for Python.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class BrokerSource(str, Enum):
    """Broker provider identity."""

    DHAN = "dhan"
    ICICI = "icici"
    UPSTOX = "upstox"
    PAPER = "paper"
    BINANCE = "binance"


@dataclass(frozen=True)
class CapabilityMetadata:
    """Metadata for one broker capability."""

    name: str
    supported: bool = True
    category: str = "other"
    version: str = "1.0"
    description: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", self.name or self.__class__.__name__)
        object.__setattr__(
            self,
            "category",
            self.category or "other",
        )
        object.__setattr__(self, "version", self.version or "1.0")


@dataclass(frozen=True)
class BrokerDescriptor:
    """Metadata describing a broker provider.

    Backward compatibility:
    - ``name`` remains the primary display name.
    - ``capabilities`` accepts either a tuple/list of names or a mapping of
      capability names to ``CapabilityMetadata``/booleans.
    """

    source: BrokerSource
    name: str
    capabilities: tuple[str, ...] | Mapping[str, CapabilityMetadata | bool] = ()
    metadata: dict[str, Any] | None = None
    supported_segments: tuple[str, ...] = ()
    rate_limit_info: str = ""
    version: str = "1.0"
    enabled: bool = True
    capability_metadata: Mapping[str, CapabilityMetadata] = field(default_factory=dict)

    def __post_init__(self) -> None:
        raw_capabilities = self.capabilities
        if isinstance(raw_capabilities, Mapping):
            names: tuple[str, ...]
            metadata: dict[str, CapabilityMetadata]
            names, metadata = _normalise_capability_mapping(raw_capabilities)
            object.__setattr__(self, "capabilities", names)
            merged = {**self.capability_metadata, **metadata}
            object.__setattr__(self, "capability_metadata", merged)
        else:
            object.__setattr__(self, "capabilities", tuple(raw_capabilities or ()))
            object.__setattr__(self, "capability_metadata", dict(self.capability_metadata))

        object.__setattr__(self, "name", self.name or self.source.value)
        object.__setattr__(self, "version", self.version or "1.0")
        object.__setattr__(self, "metadata", dict(self.metadata or {}))
        object.__setattr__(self, "supported_segments", tuple(self.supported_segments or ()))

    @property
    def display_name(self) -> str:
        return self.name

    def supports(self, capability: str) -> bool:
        if capability in self.capability_metadata:
            return self.metadata_for(capability).supported
        return capability in self.capabilities

    def metadata_for(self, capability: str) -> CapabilityMetadata:
        metadata = self.capability_metadata.get(capability)
        if metadata is not None:
            return metadata
        supported = capability in self.capabilities
        return CapabilityMetadata(
            name=capability,
            supported=supported,
            description="" if supported else "Not supported",
        )

    def supported_capabilities(self) -> tuple[str, ...]:
        return tuple(name for name in self.capabilities if self.metadata_for(name).supported)

    def supported_count(self) -> int:
        return len(self.supported_capabilities())

    def total_count(self) -> int:
        return len(self.capabilities)


class BrokerProvider:
    """Base class for broker provider factories."""

    descriptor: BrokerDescriptor

    def create(self, **kwargs: Any) -> Any:
        """Create a broker connection or adapter."""
        raise NotImplementedError


class BrokerRegistry:
    """In-memory broker provider registry."""

    def __init__(self, providers: Iterable[BrokerProvider] | None = None) -> None:
        self._providers: dict[BrokerSource, BrokerProvider] = {}
        if providers:
            for provider in providers:
                self.register(provider)

    def register(self, provider: BrokerProvider) -> None:
        self._providers[provider.descriptor.source] = provider

    def unregister(self, source: BrokerSource) -> None:
        self._providers.pop(source, None)

    def get(self, source: BrokerSource) -> BrokerProvider | None:
        return self._providers.get(source)

    def provider(self, source: BrokerSource) -> BrokerProvider | None:
        return self.get(source)

    def sources(self) -> Iterable[BrokerSource]:
        return self._providers.keys()

    def descriptors(self) -> list[BrokerDescriptor]:
        return [provider.descriptor for provider in self._providers.values()]

    def available_sources(self) -> set[BrokerSource]:
        return set(self._providers.keys())


def descriptor_from_capabilities(
    source: BrokerSource,
    name: str,
    capabilities: Iterable[str | CapabilityMetadata | tuple[str, CapabilityMetadata | bool]],
    *,
    metadata: Mapping[str, Any] | None = None,
    supported_segments: Iterable[str] = (),
    rate_limit_info: str = "",
    version: str = "1.0",
) -> BrokerDescriptor:
    """Build a ``BrokerDescriptor`` from mixed capability declarations."""

    capability_map: dict[str, CapabilityMetadata | bool] = {}
    for item in capabilities:
        if isinstance(item, str):
            capability_map[item] = True
        elif isinstance(item, CapabilityMetadata):
            capability_map[item.name] = item
        else:
            key, value = item
            capability_map[key] = value

    return BrokerDescriptor(
        source=source,
        name=name,
        capabilities=capability_map,
        metadata=dict(metadata or {}),
        supported_segments=tuple(supported_segments),
        rate_limit_info=rate_limit_info,
        version=version,
    )


def _normalise_capability_mapping(
    capabilities: Mapping[str, CapabilityMetadata | bool],
) -> tuple[tuple[str, ...], dict[str, CapabilityMetadata]]:
    names: list[str] = []
    metadata: dict[str, CapabilityMetadata] = {}
    for key, value in capabilities.items():
        names.append(key)
        if isinstance(value, CapabilityMetadata):
            metadata[key] = value
        else:
            metadata[key] = CapabilityMetadata(
                name=key,
                supported=bool(value),
                description="" if value else "Not supported",
            )
    return tuple(names), metadata


# Backwards-compatible alias used by earlier code.
CapabilityMetadataEntry = CapabilityMetadata


# ── BrokerConnection (moved from domain.py) ───────────────────────────────


class BrokerConnection(ABC):
    """Abstract broker connection with capability-based service discovery.

    New broker adapters should use the ``MarketDataGateway`` ABC from
    ``brokers.common.gateway`` directly; this class is retained for
    Upstox backward compatibility.
    """

    def __init__(
        self,
        name: str,
        broker_id: str,
        capabilities: set[Any] | None = None,
    ):
        from brokers.common.core.types import Capability, ConnectionStatus
        self._name = name
        self._broker_id = broker_id
        self._capabilities: set[Capability] = capabilities or set()
        self._capability_map: dict[Capability, Any] = {}
        self._status: ConnectionStatus = ConnectionStatus.DISCONNECTED

    @abstractmethod
    def connect(self) -> bool:
        ...

    @abstractmethod
    def disconnect(self) -> bool:
        ...

    @abstractmethod
    def reconnect(self) -> bool:
        ...

    @property
    def name(self) -> str:
        return self._name

    @property
    def broker_id(self) -> str:
        return self._broker_id

    @property
    def status(self) -> Any:
        return self._status

    def capabilities(self) -> set[Any]:
        return set(self._capabilities)

    def has_capability(self, capability: Any) -> bool:
        return capability in self._capabilities

    def get_capability(self, capability: Any) -> Any:
        return self._capability_map.get(capability)

    def _register_capability(self, capability: Any, provider: Any) -> None:
        self._capabilities.add(capability)
        self._capability_map[capability] = provider

    def _set_status(self, status: Any) -> None:
        self._status = status

    def __enter__(self) -> "BrokerConnection":
        self.connect()
        return self

    def __exit__(self, *args: Any) -> None:
        self.disconnect()
