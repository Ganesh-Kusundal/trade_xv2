"""Brokers events — re-export of domain event types for the broker layer.

The canonical event definitions live in ``domain.events``; this package is a
convenience surface so broker-layer code imports events from one place.
"""

from __future__ import annotations

from domain.events import (
    DomainEvent,
    EventPayload,
    EventType,
    canonical_event_types,
    make_payload,
)

__all__ = [
    "DomainEvent",
    "EventPayload",
    "EventType",
    "canonical_event_types",
    "make_payload",
]