"""Domain-level event bus port (abstract interface).

This is the PORT that domain code depends on — not infrastructure.
The actual EventBus lives in ``infrastructure.event_bus``; this ABC
lets domain layers publish/subscribe without importing infrastructure.

The signature matches :class:`~domain.ports.event_publisher.EventBusPort`
so that any concrete ``EventBus`` satisfies both interfaces without an
adapter.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class DomainEventBus(ABC):
    """Abstract event bus that domain code depends on.

    Publishes :class:`~domain.events.types.DomainEvent` instances.
    Subscribe returns a token (``str``) for later unsubscribe — matching
    the concrete :class:`~infrastructure.event_bus.EventBus` contract.
    """

    @abstractmethod
    def publish(self, event: Any) -> None:
        ...

    @abstractmethod
    def subscribe(self, event_type: str, handler: Any) -> str:
        ...

    @abstractmethod
    def unsubscribe(self, token: str) -> bool:
        ...
