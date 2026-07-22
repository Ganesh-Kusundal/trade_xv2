"""FeaturePipeline — returns/sma on each bar before strategy callbacks."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from domain.entities import Bar


@dataclass(frozen=True, slots=True)
class EnrichedBar:
    bar: Bar
    features: dict[str, float]


class FeaturePipeline:
    """Compute simple bar features. Call before StrategyEngine.on_bar."""

    def __init__(self, bus: Any | None = None, *, sma_window: int = 3) -> None:
        self._bus = bus
        self._sma_window = max(1, sma_window)
        self._closes: list[Decimal] = []
        self.last_features: dict[str, float] = {}

    def on_bar(self, bar: Bar) -> dict[str, float]:
        close = bar.close.value
        if self._closes:
            prev = self._closes[-1]
            ret = float((close - prev) / prev) if prev != 0 else 0.0
        else:
            ret = 0.0
        self._closes.append(close)
        window = self._closes[-self._sma_window :]
        sma = float(sum(window) / len(window))
        features = {"returns": ret, "sma": sma}
        self.last_features = features
        if self._bus is not None:
            self._bus.publish(EnrichedBar(bar=bar, features=dict(features)))
        return features
