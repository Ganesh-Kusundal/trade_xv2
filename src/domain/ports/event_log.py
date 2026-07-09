"""Event-log and event-store ports.

The OMS depends on these protocols instead of the concrete
``infrastructure.event_log`` / ``infrastructure.event_bus`` classes.  This keeps
``application`` free of any ``infrastructure`` import (the
``Application infrastructure separation`` lint contract) while still letting the
OMS persist, replay, and de-duplicate events.

The concrete implementations live in ``infrastructure`` and are injected by the
composition root (cli / api / runtime).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Iterator, Protocol, runtime_checkable

if TYPE_CHECKING:
    from domain.events.types import TradeIdKey


@runtime_checkable
class EventLogPort(Protocol):
    """Persistence / replay port for domain events."""

    @property
    def errors(self) -> int:
        """Count of append/serialization errors encountered."""
        ...

    def append(self, event: Any) -> None:
        """Persist a domain event."""
        ...

    def replay(self, event_types: set[str]) -> Iterator[Any]:
        """Yield persisted events of the given types, oldest first."""
        ...

    def flush(self) -> None:
        """Flush buffered events to durable storage."""
        ...

    def close(self) -> None:
        """Close the log, releasing resources."""
        ...


@runtime_checkable
class DeadLetterQueuePort(Protocol):
    """Dead-letter queue port for failed event-handler dispatches."""

    def drain(self) -> list[Any]:
        """Return and clear all currently-queued dead letters."""
        ...

    def stats(self) -> dict[str, int]:
        """Return queue depth / dropped counters."""
        ...


@runtime_checkable
class ProcessedTradeRepositoryPort(Protocol):
    """Idempotency ledger port for trade events."""

    def is_processed(self, key: TradeIdKey) -> bool:
        """Return True if the trade key was already accepted."""
        ...

    def mark_processed(self, key: TradeIdKey) -> None:
        """Record a trade key as accepted."""
        ...

    def attach_auto_cleanup(self, *args: Any, **kwargs: Any) -> None:
        """Start the background eviction thread (implementation-defined)."""
        ...

    def stop_auto_cleanup(self, timeout_seconds: float = 30.0) -> None:
        """Stop the background eviction thread."""
        ...

    def stats(self) -> dict[str, int]:
        """Return ledger size / evicted counters."""
        ...
