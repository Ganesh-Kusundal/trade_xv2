"""Public re-exports for the event-bus package."""
from brokers.common.event_bus.dead_letter_queue import DeadLetter, DeadLetterQueue
from brokers.common.event_bus.event_bus import DomainEvent, EventBus, EventHandler
from brokers.common.event_bus.event_types import EventType
from brokers.common.event_bus.models import (
    EVENT_PAYLOADS,
    EventPayload,
    canonical_event_types,
    make_payload,
)
from brokers.common.event_bus.processed_trade_repository import (
    ProcessedTradeRepository,
    TradeIdKey,
)

from brokers.common.event_bus.factory import (
    AsyncEventBusFactory,
    AsyncPublishAdapter,
    async_publish_wrapper,
)

__all__ = [
    "DeadLetter",
    "DeadLetterQueue",
    "DomainEvent",
    "EventBus",
    "EventHandler",
    "EventType",
    "EVENT_PAYLOADS",
    "EventPayload",
    "canonical_event_types",
    "make_payload",
    "ProcessedTradeRepository",
    "TradeIdKey",
    # AsyncEventBus integration
    "AsyncEventBusFactory",
    "AsyncPublishAdapter",
    "async_publish_wrapper",
]
