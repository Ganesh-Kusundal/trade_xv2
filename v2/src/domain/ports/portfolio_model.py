"""PortfolioModel protocol — signal-to-order translation."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from domain.commands import PlaceOrderCommand
from domain.ports.types import PortfolioContext, Signal


@runtime_checkable
class PortfolioModel(Protocol):
    def rebalance(
        self, signals: list[Signal], context: PortfolioContext
    ) -> list[PlaceOrderCommand]: ...
    def optimize(
        self, signals: list[Signal], context: PortfolioContext
    ) -> list[PlaceOrderCommand]: ...
