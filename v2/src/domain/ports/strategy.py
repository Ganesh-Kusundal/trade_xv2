"""Strategy protocol — event-driven strategy interface."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from domain.entities import Bar, Quote
from domain.events import Message, OrderFilled
from domain.ports.types import StartEvent, StopEvent
from domain.value_objects import StrategyId


@runtime_checkable
class Strategy(Protocol):
    strategy_id: StrategyId

    def on_start(self, event: StartEvent) -> None: ...
    def on_stop(self, event: StopEvent) -> None: ...
    def on_quote(self, quote: Quote) -> None: ...
    def on_bar(self, bar: Bar) -> None: ...
    def on_fill(self, fill: OrderFilled) -> None: ...
    def on_event(self, event: Message) -> None: ...
