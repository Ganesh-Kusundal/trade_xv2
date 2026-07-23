"""StrategyEngine — register strategies; route bars; emit orders via bus."""

from __future__ import annotations

from typing import Any

from domain.commands import PlaceOrderCommand
from domain.entities import Bar, Quote
from domain.events import Message, OrderFilled
from domain.ports import Strategy
from domain.ports.types import StartEvent, StopEvent
from domain.value_objects import StrategyId


class StrategyEngine:
    """Routes market events to registered strategies. Orders only via bus."""

    def __init__(self, bus: Any) -> None:
        self._bus = bus
        self._strategies: dict[StrategyId, Strategy] = {}

    def register(self, strategy: Strategy) -> None:
        self._strategies[strategy.strategy_id] = strategy

    def unregister(self, strategy_id: StrategyId) -> None:
        self._strategies.pop(strategy_id, None)

    def on_bar(self, bar: Bar, features: dict[str, float] | None = None) -> None:
        for strategy in self._strategies.values():
            strategy.on_bar(bar, features)

    def on_quote(self, quote: Quote) -> None:
        for strategy in self._strategies.values():
            strategy.on_quote(quote)

    def on_fill(self, fill: OrderFilled) -> None:
        for strategy in self._strategies.values():
            strategy.on_fill(fill)

    def on_event(self, event: Message) -> None:
        for strategy in self._strategies.values():
            strategy.on_event(event)

    def emit_order(self, command: PlaceOrderCommand) -> None:
        self._bus.publish(command)

    def start_strategy(self, strategy_id: StrategyId, event: StartEvent) -> None:
        strategy = self._strategies.get(strategy_id)
        if strategy is not None:
            strategy.on_start(event)

    def stop_strategy(self, strategy_id: StrategyId, event: StopEvent) -> None:
        strategy = self._strategies.get(strategy_id)
        if strategy is not None:
            strategy.on_stop(event)
