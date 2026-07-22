"""FillSource protocol — order submission and cancellation results."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from domain.commands import PlaceOrderCommand
from domain.ports.types import CancelResult, OrderResult
from domain.value_objects import OrderId


@runtime_checkable
class FillSource(Protocol):
    def submit(self, command: PlaceOrderCommand) -> OrderResult: ...
    def cancel(self, order_id: OrderId) -> CancelResult: ...
