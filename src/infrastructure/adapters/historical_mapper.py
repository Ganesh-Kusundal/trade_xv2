"""Map canonical OHLCV DataFrames to HistoricalBar domain objects."""

from __future__ import annotations

import pandas as pd

from domain.candles.historical import HistoricalBar, HistoricalSeries, InstrumentRef


def dataframe_to_historical_bars(
    df: pd.DataFrame,
    instrument: InstrumentRef,
    timeframe: str,
    broker_id: str,
    request_id: str,
) -> list[HistoricalBar]:
    """Convert a broker history DataFrame to normalized HistoricalBar list."""
    series = HistoricalSeries.from_broker_df(
        df,
        instrument,
        timeframe,
        broker_id=broker_id,
        request_id=request_id,
    )
    return series.bars
