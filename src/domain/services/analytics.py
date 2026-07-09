"""AnalyticsService — pure, in-process analytics over historical series.

Wraps a :class:`~domain.ports.protocols.DataProvider` for parity with the other
services, but its analytics are computed locally on a :class:`HistoricalSeries`.
Pure domain layer: no broker or transport imports.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from domain.candles.historical import HistoricalSeries
    from domain.ports.protocols import DataProvider


class AnalyticsService:
    """Lightweight, dependency-free analytics over historical series."""

    def __init__(self, provider: DataProvider | None = None) -> None:
        self._provider = provider

    @property
    def provider(self) -> DataProvider | None:
        return self._provider

    def daily_returns(self, series: HistoricalSeries) -> pd.Series:
        try:
            df = series.to_dataframe()
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df = df.set_index("timestamp")
            return df["close"].pct_change().dropna()
        except Exception:
            return pd.Series(dtype=float)
