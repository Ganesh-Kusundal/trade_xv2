"""Null event bus — no-op implementation for tests."""

from __future__ import annotations

from typing import Any

from domain.events.bus import DomainEventBus


class NullEventBus(DomainEventBus):
    """No-op event bus. All operations are silently ignored."""

    def publish(self, event: Any) -> None:
        pass

    def subscribe(self, event_type: str, handler: Any) -> str:
        return ""

    def unsubscribe(self, token: str) -> bool:
        return True
