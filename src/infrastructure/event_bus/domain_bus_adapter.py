"""Bridge domain ``DomainEventBus`` (str, dict) API to infrastructure ``EventBus``.

Markets-layer code publishes ``(event_type, payload)``; the load-bearing bus
expects frozen :class:`domain.events.types.DomainEvent` instances.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from domain.events.bus import DomainEventBus
from domain.events.types import DomainEvent, to_typed_event
from domain.ports import EventBusPort

# ``to_typed_event`` is re-exported here as a convenience so subscribers can
# call ``to_typed_event(event)`` from the adapter namespace instead of
# reaching into the domain module. Keeps the core event_bus.py untouched.
__all__ = ["InfrastructureEventBusAdapter", "to_typed_event"]


class InfrastructureEventBusAdapter(DomainEventBus):
    """Adapt infrastructure EventBus to the domain DomainEventBus port."""

    def __init__(self, bus: EventBusPort) -> None:
        self._bus = bus

    def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        correlation_id = payload.get("candidate_id") or payload.get("correlation_id")
        symbol = payload.get("symbol")
        self._bus.publish(
            DomainEvent.now(
                event_type,
                payload,
                symbol=str(symbol) if symbol is not None else None,
                correlation_id=str(correlation_id) if correlation_id else None,
            )
        )

    def subscribe(self, event_type: str, handler: Callable) -> None:
        self._bus.subscribe(event_type, handler)

    def unsubscribe(self, event_type: str, handler: Callable) -> None:
        if hasattr(self._bus, "unsubscribe"):
            self._bus.unsubscribe(event_type, handler)
