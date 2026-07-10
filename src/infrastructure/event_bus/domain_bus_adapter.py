"""Bridge domain ``DomainEventBus`` (str, dict) API to infrastructure ``EventBus``.

Markets-layer code publishes ``(event_type, payload)``; the load-bearing bus
expects frozen :class:`domain.events.types.DomainEvent` instances.
"""

from __future__ import annotations

from typing import Any, Callable

from domain.events.bus import DomainEventBus
from domain.events.types import DomainEvent
from domain.ports import EventBusPort


class InfrastructureEventBusAdapter(DomainEventBus):
    """Adapt infrastructure EventBus to the domain DomainEventBus port."""

    def __init__(self, bus: EventBusPort) -> None:
        self._bus = bus

    def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        self._bus.publish(DomainEvent.now(event_type, payload))

    def subscribe(self, event_type: str, handler: Callable) -> None:
        self._bus.subscribe(event_type, handler)

    def unsubscribe(self, event_type: str, handler: Callable) -> None:
        if hasattr(self._bus, "unsubscribe"):
            self._bus.unsubscribe(event_type, handler)
