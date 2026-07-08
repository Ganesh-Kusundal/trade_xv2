"""Null event bus — no-op implementation for tests."""

from __future__ import annotations

from collections.abc import Callable

from domain.events.bus import DomainEventBus


class NullEventBus(DomainEventBus):
    """No-op event bus. All operations are silently ignored."""

    def publish(self, event_type: str, payload: dict) -> None:
        pass

    def subscribe(self, event_type: str, handler: Callable) -> None:
        pass

    def unsubscribe(self, event_type: str, handler: Callable) -> None:
        pass
