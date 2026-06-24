"""Public re-exports for the event-bus package."""
from infrastructure.event_bus.dead_letter_queue import DeadLetter, DeadLetterQueue
from infrastructure.event_bus.persistent_dead_letter_queue import (
    PersistentDeadLetterQueue,
    create_default_dead_letter_queue,
)
from infrastructure.event_bus.event_bus import DomainEvent, EventBus, EventHandler
from infrastructure.event_bus.processed_trade_repository import (
    ProcessedTradeRepository,
    TradeIdKey,
)

from domain.events.types import EventType

__all__ = [
    "DeadLetter",
    "DeadLetterQueue",
    "PersistentDeadLetterQueue",
    "create_default_dead_letter_queue",
    "DomainEvent",
    "EventBus",
    "EventHandler",
    "EventType",
    "ProcessedTradeRepository",
    "TradeIdKey",
]
