"""Runtime facade for historical data (composition-root-safe re-export)."""

from __future__ import annotations

from infrastructure.historical_data import (
    GapRange,
    HistoricalDataRequest,
    HistoricalDataService,
    SupportsHistoricalCandles,
)

__all__ = [
    "GapRange",
    "HistoricalDataRequest",
    "HistoricalDataService",
    "SupportsHistoricalCandles",
]
