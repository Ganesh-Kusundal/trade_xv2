"""Pandas-dependent market data adapters.

These adapters convert pandas DataFrames to domain ``HistoricalSeries``
objects.  They live in the infrastructure layer (not the domain port)
so the domain protocol stays free of pandas.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from domain.candles.historical import HistoricalSeries, InstrumentRef
from domain.symbols import make_instrument_key


def _df_to_historical_series(
    df: Any,
    symbol: str,
    exchange: str,
    interval: str,
    start: date,
    end: date,
    *,
    broker_id: str = "adapter",
    request_id: str = "adapter-history",
) -> HistoricalSeries | None:
    """Convert a pandas DataFrame of OHLCV bars to a HistoricalSeries."""
    import pandas as pd

    if df is None or (isinstance(df, pd.DataFrame) and df.empty):
        return None

    instrument = InstrumentRef(symbol=symbol, exchange=exchange)
    series = HistoricalSeries.from_broker_df(
        df,
        instrument,
        interval,
        broker_id=broker_id,
        request_id=request_id,
    )
    if not series.bars:
        return None
    return series


class GatewayMarketDataAdapter:
    """Wraps a broker gateway ``history`` method as :class:`MarketDataPort`."""

    def __init__(self, gateway: Any) -> None:
        self._gateway = gateway

    def history(
        self,
        symbol: str,
        start: date,
        end: date,
        *,
        interval: str = "1m",
        exchange: str = "NSE",
    ) -> HistoricalSeries | None:
        history_fn = getattr(self._gateway, "history", None)
        if history_fn is None:
            return None
        df = history_fn(symbol, start, end, interval=interval, exchange=exchange)
        return _df_to_historical_series(df, symbol, exchange, interval, start, end)


class DataFrameMarketDataAdapter:
    """Serves pre-loaded OHLCV for replay/backtest parity tests."""

    def __init__(self, frames: dict[tuple[str, str], Any]) -> None:
        self._frames = frames

    def history(
        self,
        symbol: str,
        start: date,
        end: date,
        *,
        interval: str = "1m",
        exchange: str = "NSE",
    ) -> HistoricalSeries | None:
        import pandas as pd

        key = make_instrument_key(symbol, exchange)
        df = self._frames.get(key)
        if df is None:
            return None
        if isinstance(df, pd.DataFrame) and "date" in df.columns:
            mask = (df["date"] >= start) & (df["date"] <= end)
            df = df.loc[mask].copy()
        elif isinstance(df, pd.DataFrame):
            df = df.copy()
        return _df_to_historical_series(df, symbol, exchange, interval, start, end)
