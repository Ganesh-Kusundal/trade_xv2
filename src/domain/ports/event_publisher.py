"""Event publisher port — domain services depend on this instead of concrete EventBus.

This protocol captures the publish/subscribe contract that every event bus
implementation (synchronous EventBus, AsyncEventBus, or test doubles) must
satisfy.  Domain-adjacent services (OrderManager, PositionManager, broker
adapters, analytics engines) depend on this protocol rather than importing
the concrete :class:`~infrastructure.event_bus.EventBus`.

Usage::

    from domain.ports import EventPublisher
    from domain.events import DomainEvent

    class MyService:
        def __init__(self, event_bus: EventPublisher | None = None):
            self._event_bus = event_bus

        def notify(self, order: Order) -> None:
            if self._event_bus is not None:
                self._event_bus.publish(
                    DomainEvent.now("ORDER_PLACED", {"order": order})
                )
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class EventPublisher(Protocol):
    """Minimal publish/subscribe port for domain events."""

    def publish(self, event: Any) -> None:
        """Publish a domain event to all subscribers.

        The *event* parameter is a :class:`~infrastructure.event_bus.DomainEvent`
        (or any duck-typed equivalent).  Using ``Any`` avoids a concrete import
        from the infrastructure layer.
        """
        ...

    def subscribe(self, event_type: str, handler: Any) -> str:
        """Register an event handler. Returns a token for later unsubscribe."""
        ...


class EventBusPort(EventPublisher):
    """Event-bus port with the replay / observability controls the OMS uses.

    :class:`~domain.ports.event_publisher.EventPublisher` covers publish /
    subscribe.  The OMS additionally toggles replay mode and logging during
    crash-recovery replay (see ``TradingContext._replay_log_into_oms``), so
    this port adds those controls.  The concrete
    :class:`~infrastructure.event_bus.EventBus` implements it; ``application``
    depends on the port, never the concrete class.
    """

    @property
    def replay_mode(self) -> bool:
        """Whether the bus is in replay mode (handler dispatch suppressed)."""
        ...

    def set_replay_mode(self, enabled: bool) -> None:
        """Enable / disable replay mode."""
        ...

    @property
    def logging_enabled(self) -> bool:
        """Whether events are persisted to the event log on publish."""
        ...

    def set_logging_enabled(self, enabled: bool) -> None:
        """Enable / disable event-log persistence on publish."""
        ...


__all__ = ["EventBusPort", "EventPublisher"]
