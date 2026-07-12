"""EventBusFacade — brokers-scoped facade over the canonical OMS event bus.

Thin read/emit coordinator. The real bus lives in ``infrastructure.event_bus``;
this just adapts it for the broker layer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from infrastructure.event_bus.event_bus import EventBus

if TYPE_CHECKING:
    pass


class EventBusFacade:
    """Facade over the canonical event bus for broker-layer events."""

    def __init__(self, bus: EventBus | None = None) -> None:
        self._bus = bus or EventBus()

    def publish(self, event_type: str, payload: Any) -> None:
        self._bus.publish(event_type, payload)

    def subscribe(self, event_type: str, handler: Callable[[Any], None]) -> Any:
        return self._bus.subscribe(event_type, handler)

    def get_bus(self) -> EventBus:
        return self._bus