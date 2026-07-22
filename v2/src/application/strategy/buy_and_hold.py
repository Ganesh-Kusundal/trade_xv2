"""Minimal buy-and-hold strategy — one BUY on first bar (for tests)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import uuid4

from domain.commands import PlaceOrderCommand
from domain.entities import Bar, Quote
from domain.enums import OrderSide, OrderType, TimeInForce
from domain.events import Message, OrderFilled
from domain.value_objects import CorrelationId, Quantity, StrategyId


class BuyAndHold:
    """Buys once on the first bar at bar.close (LIMIT)."""

    strategy_id = StrategyId(value="buy_and_hold")

    def __init__(
        self,
        bus: Any,
        *,
        quantity: Quantity | None = None,
        correlation_id: CorrelationId | None = None,
    ) -> None:
        self._bus = bus
        self._quantity = quantity or Quantity(value=Decimal("1"))
        self._correlation_id = correlation_id
        self._bought = False

    def on_start(self, event: Message) -> None:
        return None

    def on_stop(self, event: Message) -> None:
        return None

    def on_quote(self, quote: Quote) -> None:
        return None

    def on_fill(self, fill: OrderFilled) -> None:
        return None

    def on_event(self, event: Message) -> None:
        return None

    def on_bar(self, bar: Bar) -> None:
        if self._bought:
            return
        self._bought = True
        self._bus.publish(
            PlaceOrderCommand(
                instrument_id=bar.instrument_id,
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                quantity=self._quantity,
                price=bar.close,
                time_in_force=TimeInForce.DAY,
                correlation_id=self._correlation_id
                or CorrelationId(value=uuid4()),
            )
        )
