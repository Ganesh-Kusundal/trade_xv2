"""PortfolioModel port — rebalancing interface."""

from typing import Protocol, runtime_checkable
from dataclasses import dataclass


@dataclass(frozen=True)
class Signal:
    instrument_id: object
    direction: int  # 1=buy, -1=sell, 0=neutral
    strength: float  # 0.0 to 1.0


@dataclass(frozen=True)
class PortfolioContext:
    account: object
    positions: dict
    quotes: dict


@runtime_checkable
class PortfolioModel(Protocol):
    def rebalance(self, signals: list[Signal], context: PortfolioContext) -> list: ...
