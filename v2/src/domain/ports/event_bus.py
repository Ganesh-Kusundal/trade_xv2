"""EventBusPort protocol — publish/subscribe message bus."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

from domain.events import Message
from domain.ports.types import Subscription


@runtime_checkable
class EventBusPort(Protocol):
    def subscribe(self, msg_type: type, handler: Callable[..., Any]) -> Subscription: ...
    def publish(self, message: Message) -> None: ...
