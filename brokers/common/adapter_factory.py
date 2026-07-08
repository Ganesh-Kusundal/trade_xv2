"""Broker adapter factory (plan 9.4).

Resolves the correct data/execution provider adapter for a ``broker_id``
without any ``if broker == "..."`` branching. Brokers register their adapter
classes here at the composition root, keeping broker-specific construction
logic out of the runtime path and out of domain objects.

The registry lives in this single module (not as global mutable state on a
session object) and is the one sanctioned place for broker-name → class
mapping.
"""

from __future__ import annotations

from typing import Any


_DATA_ADAPTERS: dict[str, type] = {}
_EXECUTION_PROVIDERS: dict[str, type] = {}


def register_data_adapter(broker_id: str, cls: type) -> None:
    """Register a ``DataProvider`` adapter class for a broker (open for extension)."""
    _DATA_ADAPTERS[broker_id] = cls


def register_execution_provider(broker_id: str, cls: type) -> None:
    """Register an ``ExecutionProvider`` class for a broker (open for extension)."""
    _EXECUTION_PROVIDERS[broker_id] = cls


def _seed_defaults() -> None:
    """Populate the default registrations lazily to avoid import-time side effects."""
    if not _DATA_ADAPTERS:
        from brokers.dhan.adapter import DhanDataAdapter
        from brokers.upstox.adapter import UpstoxDataAdapter

        register_data_adapter("dhan", DhanDataAdapter)
        register_data_adapter("upstox", UpstoxDataAdapter)

    if not _EXECUTION_PROVIDERS:
        from providers.dhan.execution_provider import DhanExecutionProvider

        register_execution_provider("dhan", DhanExecutionProvider)


def create_data_adapter(gateway: Any, *, broker_id: str) -> Any:
    """Return a ``DataProvider`` adapter for ``broker_id``.

    Falls back to the generic ``BaseDataAdapter`` when no broker-specific
    adapter is registered (it normalizes via the generic gateway interface).
    """
    from brokers.common.adapter_base import BaseDataAdapter

    _seed_defaults()
    cls = _DATA_ADAPTERS.get(broker_id, BaseDataAdapter)
    return cls(gateway, broker_id=broker_id)


def create_execution_provider(gateway: Any, *, broker_id: str) -> Any | None:
    """Return an ``ExecutionProvider`` for ``broker_id``, or ``None`` if unsupported.

    Brokers without an execution provider (e.g. read-only configurations)
    resolve to ``None`` rather than raising — callers must handle a missing
    execution provider gracefully.
    """
    _seed_defaults()
    cls = _EXECUTION_PROVIDERS.get(broker_id)
    return cls(gateway) if cls is not None else None
