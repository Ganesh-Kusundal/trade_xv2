"""Domain-level event bus port (abstract interface).

This is the PORT that domain code depends on — not infrastructure.
The actual EventBus lives in ``infrastructure.event_bus``; this ABC
lets domain layers publish/subscribe without importing infrastructure.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable


class DomainEventBus(ABC):
    """Abstract event bus that domain code depends on."""

    @abstractmethod
    def publish(self, event_type: str, payload: dict) -> None:
        ...

    @abstractmethod
    def subscribe(self, event_type: str, handler: Callable) -> None:
        ...

    @abstractmethod
    def unsubscribe(self, event_type: str, handler: Callable) -> None:
        ...
