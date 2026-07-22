"""EventBusPort — publish/subscribe interface for domain events."""

from typing import Protocol, Callable, runtime_checkable
from dataclasses import dataclass, field
from uuid import UUID, uuid4


@dataclass
class Subscription:
    subscription_id: UUID = field(default_factory=uuid4)

    def cancel(self) -> None: ...


@runtime_checkable
class EventBusPort(Protocol):
    def subscribe(self, msg_type: type, handler: Callable) -> Subscription: ...
    def unsubscribe(self, subscription: Subscription) -> None: ...
    def publish(self, message: object) -> None: ...
