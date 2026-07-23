"""StrategyEngine routes bars; strategies publish PlaceOrderCommand via bus."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from application.strategy.buy_and_hold import BuyAndHold
from application.strategy.strategy_engine import StrategyEngine
from domain.commands import PlaceOrderCommand
from domain.entities import Bar
from domain.value_objects import InstrumentId, Price, Quantity, TimeFrame
from infrastructure.message_bus.bus import MessageBus


def _bar(close: str = "2500") -> Bar:
    c = Price(value=Decimal(close))
    return Bar(
        instrument_id=InstrumentId.parse("NSE:RELIANCE"),
        open=c,
        high=c,
        low=c,
        close=c,
        volume=Quantity(value=Decimal("10")),
        timeframe=TimeFrame(value="1d"),
        timestamp=datetime(2024, 6, 1, tzinfo=UTC),
    )


def test_strategy_receives_bar_and_publishes_order_command() -> None:
    bus = MessageBus()
    commands: list[PlaceOrderCommand] = []
    bus.subscribe(PlaceOrderCommand, commands.append)

    engine = StrategyEngine(bus=bus)
    engine.register(BuyAndHold(bus=bus, quantity=Quantity(value=Decimal("1"))))
    engine.on_bar(_bar())

    assert len(commands) == 1
    assert isinstance(commands[0], PlaceOrderCommand)
    assert commands[0].instrument_id.value == "NSE:RELIANCE"
