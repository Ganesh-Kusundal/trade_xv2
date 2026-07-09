"""HistoryService — orchestration wrapper for historical OHLCV access.

Wraps a :class:`~domain.ports.protocols.DataProvider` so the ``Instrument``
never talks to a provider directly for historical data.  Pure domain layer:
no broker or transport imports.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pandas as pd

if TYPE_CHECKING:
    from domain.candles.historical import HistoricalSeries, InstrumentRef
    from domain.instruments.instrument_id import InstrumentId
    from domain.ports.protocols import DataProvider


class HistoryService:
    """Thin historical-data accessor over a :class:`DataProvider` port."""

    def __init__(self, provider: DataProvider | None = None) -> None:
        self._provider = provider

    @property
    def provider(self) -> DataProvider | None:
        return self._provider

    def get_history(
        self,
        instrument_id: Any,
        *,
        timeframe: str = "1D",
        lookback_days: int = 120,
        from_date: Any = None,
        to_date: Any = None,
        as_dataframe: bool = False,
    ) -> Any:
        from domain.candles.historical import HistoricalSeries, InstrumentRef

        if self._provider is None:
            if as_dataframe:
                return pd.DataFrame()
            return HistoricalSeries(
                bars=[],
                coverage=None,
                instrument=InstrumentRef(
                    symbol=getattr(instrument_id, "underlying", str(instrument_id)),
                    exchange=getattr(instrument_id, "exchange", ""),
                ),
                timeframe=timeframe,
            )

        try:
            series = self._provider.get_history_series(
                instrument_id,
                timeframe=timeframe,
                lookback_days=lookback_days,
                from_date=from_date,
                to_date=to_date,
            )
        except (AttributeError, NotImplementedError):
            df = self._provider.get_history(
                instrument_id,
                timeframe=timeframe,
                lookback_days=lookback_days,
                from_date=from_date,
                to_date=to_date,
            )
            series = HistoricalSeries.from_dataframe(
                df,
                InstrumentRef(
                    symbol=instrument_id.underlying,
                    exchange=instrument_id.exchange,
                ),
                timeframe,
            )

        return series.df if as_dataframe else series
