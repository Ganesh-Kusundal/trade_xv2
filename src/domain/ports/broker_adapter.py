"""BrokerAdapter — unified broker adapter protocol (composition root).

Phase 9.1 of the Instrument-Centric SDK Redesign.

This is the composition-root contract that unifies market-data access and
order execution behind a single interface.  A ``BrokerAdapter`` is simply a
class that satisfies both :class:`DataProvider` and :class:`ExecutionProvider`
and additionally exposes connection lifecycle operations.

Because ``DataProvider`` and ``ExecutionProvider`` are ``runtime_checkable``
protocols, any concrete class implementing the union of their members (plus
``authenticate`` / ``close`` and the ``broker_id`` / ``is_connected``
attributes) is structurally a ``BrokerAdapter`` — no explicit subclassing
required.  This lets live brokers, fakes, and replay engines all plug into
the same wiring point.

This is a pure domain port: it contains no broker-specific logic, no
implementation, and imports nothing from ``brokers.*`` or ``providers.*``.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from domain.ports.protocols import DataProvider, ExecutionProvider


@runtime_checkable
class BrokerAdapter(DataProvider, ExecutionProvider, Protocol):
    """Unified broker interface: data + execution + lifecycle in one object."""

    broker_id: str
    is_connected: bool

    def authenticate(self) -> bool:
        """Authenticate against the broker; return True on success."""
        ...

    def close(self) -> None:
        """Tear down the connection and release resources."""
        ...
