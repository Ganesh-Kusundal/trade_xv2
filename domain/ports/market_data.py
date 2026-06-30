"""Market data port for feature fetchers and orchestrators."""

from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

from domain.historical import HistoricalSeries


@runtime_checkable
class MarketDataPort(Protocol):
    """Read-only historical market data (gateway or datalake backed)."""

    def history(
        self,
        symbol: str,
        start: date,
        end: date,
        *,
        interval: str = "1m",
        exchange: str = "NSE",
    ) -> HistoricalSeries | None: ...
