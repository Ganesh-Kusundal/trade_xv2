"""HistoricalManager — coordinates historical-series retrieval + caching.

Thin coordinator over ``Instrument.history`` (which talks to the provider and
an optional cache). No series computation lives here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from domain.candles.historical import HistoricalSeries
    from domain.instruments.instrument import Instrument


class HistoricalManager:
    """Coordinates history downloads/refreshes for instruments."""

    def series(
        self,
        instrument: Instrument,
        timeframe: str = "1D",
        days: int = 120,
    ) -> HistoricalSeries:
        return instrument.history(timeframe=timeframe, days=days)

    def refresh(
        self,
        instrument: Instrument,
        timeframe: str | None = None,
        days: int | None = None,
    ) -> HistoricalSeries:
        return instrument.history.refresh(timeframe=timeframe, days=days)

    def resample(self, instrument: Instrument, target_timeframe: str) -> HistoricalSeries:
        return instrument.history.resample(target_timeframe)