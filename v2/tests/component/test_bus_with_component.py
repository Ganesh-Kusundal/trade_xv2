"""Component subscribes on start, unsubscribes on stop."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from infrastructure.component.base import Component, ComponentState
from infrastructure.message_bus.bus import MessageBus


@dataclass(frozen=True)
class Tick:
    price: float
    timestamp: datetime = datetime(2024, 1, 1, tzinfo=UTC)


class MarketListener(Component):
    def __init__(self, bus: MessageBus) -> None:
        super().__init__("market-listener")
        self._bus = bus
        self.ticks: list[Tick] = []
        self._subscription = None

    def _on_initialize(self, config: object | None = None) -> None:
        pass

    def _on_start(self) -> None:
        self._subscription = self._bus.subscribe(Tick, self._on_tick)

    def _on_stop(self) -> None:
        if self._subscription is not None:
            self._bus.unsubscribe(self._subscription)
            self._subscription = None

    def _on_reset(self) -> None:
        self.ticks.clear()

    def _on_tick(self, msg: Tick) -> None:
        self.ticks.append(msg)


def test_component_subscribes_on_start_unsubscribes_on_stop() -> None:
    bus = MessageBus()
    listener = MarketListener(bus)

    bus.publish(Tick(100.0))
    assert listener.ticks == []

    listener.initialize()
    listener.start()
    assert listener.state is ComponentState.RUNNING

    bus.publish(Tick(101.5))
    assert listener.ticks == [Tick(101.5)]

    listener.stop()
    assert listener.state is ComponentState.STOPPED

    bus.publish(Tick(102.0))
    assert listener.ticks == [Tick(101.5)]
