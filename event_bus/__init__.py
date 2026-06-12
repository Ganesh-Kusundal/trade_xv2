"""Event Bus module -- domain event publishing and subscription.

Provides a lightweight, in-memory event bus for decoupled communication
between trading system components (OMS, risk, portfolio, etc.).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Type

from brokers.common.core.domain import Order

# -- Domain Events -----------------------------------------------------------


@dataclass(frozen=True)
class DomainEvent:
    """Base class for all domain events."""

    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = ""


@dataclass(frozen=True)
class OrderPlacedEvent(DomainEvent):
    """Published when a new order is successfully placed."""

    order: Order = field(default=None)  # type: ignore[assignment]


@dataclass(frozen=True)
class OrderFilledEvent(DomainEvent):
    """Published when an order is completely filled."""

    order: Order = field(default=None)  # type: ignore[assignment]


@dataclass(frozen=True)
class PositionChangedEvent(DomainEvent):
    """Published when a position quantity changes."""

    symbol: str = ""
    exchange: str = ""
    delta: int = 0


# -- Event Bus ABC & In-Memory Implementation --------------------------------


class EventBus(ABC):
    """Abstract event bus interface."""

    @abstractmethod
    def publish(self, event: DomainEvent) -> None:
        """Publish an event to all registered handlers for its type."""
        ...

    @abstractmethod
    def subscribe(
        self, event_type: type[DomainEvent], handler: Callable[[DomainEvent], None]
    ) -> None:
        """Register a handler for a specific event type."""
        ...


class InMemoryEventBus(EventBus):
    """Simple in-memory event bus using a dict of type -> handlers."""

    def __init__(self) -> None:
        self._handlers: dict[type[DomainEvent], list[Callable[[DomainEvent], None]]] = {}

    def publish(self, event: DomainEvent) -> None:
        """Dispatch *event* to every handler subscribed to its type."""
        for handler in self._handlers.get(type(event), []):
            handler(event)

    def subscribe(
        self, event_type: type[DomainEvent], handler: Callable[[DomainEvent], None]
    ) -> None:
        """Register *handler* to be called when *event_type* is published."""
        self._handlers.setdefault(event_type, []).append(handler)
