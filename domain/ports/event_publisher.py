"""Event publisher port — analytics depends on this instead of concrete EventBus."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class EventPublisher(Protocol):
    """Minimal publish/subscribe port for domain events."""

    def publish(self, event_type: str, payload: dict[str, Any], **kwargs: Any) -> None:
        """Publish a domain event."""
        ...

    def subscribe(self, event_type: str, handler: Any) -> None:
        """Register an event handler."""
        ...


__all__ = ["EventPublisher"]
