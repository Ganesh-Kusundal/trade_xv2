"""Domain event types — canonical event catalogue."""

from domain.events.types import (
    EventPayload,
    EventType,
    canonical_event_types,
    make_payload,
)

__all__ = [
    "EventType",
    "EventPayload",
    "canonical_event_types",
    "make_payload",
]
