"""AnalyticsService — pure, in-process analytics over historical series.

No top-level pandas. DataFrame export is opt-in via ``as_dataframe``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from domain.candles.historical import HistoricalSeries
    from domain.ports.protocols import DataProvider


class AnalyticsService:
    """Lightweight, dependency-free analytics over historical series."""

    def __init__(self, provider: "DataProvider | None" = None) -> None:
        self._provider = provider

    @property
    def provider(self) -> "DataProvider | None":
        return self._provider

    def daily_returns(
        self, series: "HistoricalSeries", *, as_dataframe: bool = False
    ) -> list[float] | Any:
        """Simple close-to-close returns. Pure list by default."""
        closes = [float(b.close) for b in series.bars]
        rets: list[float] = []
        for i in range(1, len(closes)):
            prev = closes[i - 1]
            rets.append((closes[i] / prev - 1.0) if prev else 0.0)
        if not as_dataframe:
            return rets
        import pandas as pd

        return pd.Series(rets, dtype=float)
