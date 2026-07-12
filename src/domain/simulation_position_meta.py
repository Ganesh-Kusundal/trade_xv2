"""Simulation-only position metadata (SL/TP/entry time) — not qty/avg."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class PositionMeta:
    """Per-symbol exit rules and audit fields; qty/avg live in PortfolioProjector."""

    entry_time: datetime
    stop_loss: float | None = None
    target: float | None = None
    strategy: str = ""

    @property
    def take_profit(self) -> float | None:
        return self.target

    def with_take_profit(self, value: float | None) -> PositionMeta:
        return PositionMeta(
            entry_time=self.entry_time,
            stop_loss=self.stop_loss,
            target=value,
            strategy=self.strategy,
        )