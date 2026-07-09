"""Broker adapter factory (plan 9.4).

Resolves the correct data/execution provider adapter for a ``broker_id``
without any ``if broker == "..."`` branching. Brokers register their adapter
classes here **on package import** (see ``brokers.dhan`` / ``brokers.upstox``
``__init__.py``), keeping broker-specific construction logic out of the runtime
path, out of domain objects, AND out of ``brokers.common`` entirely (ADR-007).

This module intentionally never imports a concrete broker package. The
broker → class mapping lives in the registries below, populated by the broker
packages themselves at import time. To add a broker, have its package register
its adapter classes via the ``register_*`` functions — no change to this file
or to any consumer is required.

The registries live in this single module (not as global mutable state on a
session object) and are the one sanctioned place for broker-name → class
mapping.
"""

from __future__ import annotations

from typing import Any


_DATA_ADAPTERS: dict[str, type] = {}
_EXECUTION_PROVIDERS: dict[str, type] = {}
_BROKER_EXTENSION_CLASSES: dict[str, list[type]] = {}
_BROKER_ADAPTERS: dict[str, type] = {}


# ── Registration (brokers self-register on import; see ADR-007) ────────────


def register_broker_extensions(broker_id: str, classes: list[type]) -> None:
    """Register the broker-specific ``Extension`` classes for a broker."""
    _BROKER_EXTENSION_CLASSES[broker_id] = list(classes)


def register_data_adapter(broker_id: str, cls: type) -> None:
    """Register a ``DataProvider`` adapter class for a broker (open for extension)."""
    _DATA_ADAPTERS[broker_id] = cls


def register_execution_provider(broker_id: str, cls: type) -> None:
    """Register an ``ExecutionProvider`` class for a broker (open for extension)."""
    _EXECUTION_PROVIDERS[broker_id] = cls


def register_broker_adapter(broker_id: str, cls: type) -> None:
    """Register a unified ``BrokerAdapter`` class for a broker (open for extension)."""
    _BROKER_ADAPTERS[broker_id] = cls


# ── Resolution ─────────────────────────────────────────────────────────────


def get_broker_extension_classes(broker_id: str) -> list[type]:
    """Return the registered broker-specific ``Extension`` classes for a broker."""
    return list(_BROKER_EXTENSION_CLASSES.get(broker_id, []))


def create_data_adapter(gateway: Any, *, broker_id: str) -> Any:
    """Return a ``DataProvider`` adapter for ``broker_id``.

    Falls back to passing the gateway directly when no broker-specific
    adapter is registered.
    """
    cls = _DATA_ADAPTERS.get(broker_id)
    if cls is not None:
        return cls(gateway, broker_id=broker_id)
    return gateway


def create_execution_provider(gateway: Any, *, broker_id: str) -> Any | None:
    """Return an ``ExecutionProvider`` for ``broker_id``, or ``None`` if unsupported.

    Brokers without an execution provider (e.g. read-only configurations)
    resolve to ``None`` rather than raising — callers must handle a missing
    execution provider gracefully.
    """
    cls = _EXECUTION_PROVIDERS.get(broker_id)
    return cls(gateway) if cls is not None else None


def create_broker_adapter(gateway: Any, *, broker_id: str) -> Any | None:
    """Return a unified ``BrokerAdapter`` for ``broker_id``, or ``None`` if unknown.

    The resolved class is constructed with the gateway and the broker id,
    e.g. ``DhanBrokerAdapter(gateway, broker_id="dhan")``. Unknown broker ids
    resolve to ``None`` rather than raising — callers may fall back to the
    separate data/execution adapters.
    """
    cls = _BROKER_ADAPTERS.get(broker_id)
    return cls(gateway, broker_id=broker_id) if cls is not None else None
