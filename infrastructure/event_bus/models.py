"""Event bus domain models - EventType enum and related types.

This module provides a clean import path for event types. It re-exports
from event_types.py for backward compatibility and organization.

Usage:
    from infrastructure.event_bus.models import EventType
    
    event = DomainEvent(event_type=EventType.ORDER_UPDATED.value, ...)
    # OR (direct comparison works due to str,Enum):
    if event.event_type == EventType.ORDER_UPDATED:
        ...
"""

from __future__ import annotations

# Re-export EventType from the canonical location
from infrastructure.event_bus.event_types import (
    EVENT_PAYLOADS,
    EventPayload,
    EventType,
    canonical_event_types,
    make_payload,
)

__all__ = [
    "EVENT_PAYLOADS",
    "EventPayload",
    "EventType",
    "canonical_event_types",
    "make_payload",
]
