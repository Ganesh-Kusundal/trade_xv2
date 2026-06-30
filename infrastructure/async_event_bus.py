# Backward compat — moved to infrastructure.event_bus.async_event_bus
from infrastructure.event_bus.async_event_bus import CRITICAL_EVENT_TYPES, AsyncEventBus

__all__ = [
    "CRITICAL_EVENT_TYPES",
    "AsyncEventBus",
]
