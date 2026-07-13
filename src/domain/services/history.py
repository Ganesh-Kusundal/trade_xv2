"""HistoryService — orchestration wrapper for historical OHLCV access.

Wraps a :class:`~domain.ports.protocols.DataProvider` so the ``Instrument``
never talks to a provider directly for historical data.  Pure domain layer:
no broker or transport imports. No top-level pandas.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from domain.candles.historical import HistoricalSeries
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
            series = HistoricalSeries(
                bars=[],
                coverage=None,
                instrument=InstrumentRef(
                    symbol=getattr(instrument_id, "underlying", str(instrument_id)),
                    exchange=getattr(instrument_id, "exchange", ""),
                ),
                timeframe=timeframe,
            )
            return series.to_dataframe() if as_dataframe else series

        try:
            series = self._provider.get_history_series(
                instrument_id,
                timeframe=timeframe,
                lookback_days=lookback_days,
                from_date=from_date,
                to_date=to_date,
            )
        except (AttributeError, NotImplementedError):
            raw = self._provider.get_history(
                instrument_id,
                timeframe=timeframe,
                lookback_days=lookback_days,
                from_date=from_date,
                to_date=to_date,
            )
            if isinstance(raw, HistoricalSeries):
                series = raw
            elif isinstance(raw, list):
                series = HistoricalSeries(
                    bars=raw,
                    coverage=None,
                    instrument=InstrumentRef(
                        symbol=getattr(instrument_id, "underlying", str(instrument_id)),
                        exchange=getattr(instrument_id, "exchange", ""),
                    ),
                    timeframe=timeframe,
                )
            else:
                series = HistoricalSeries.from_broker_df(
                    raw,
                    InstrumentRef(
                        symbol=instrument_id.underlying,
                        exchange=instrument_id.exchange,
                    ),
                    timeframe,
                    broker_id=getattr(self._provider, "name", "unknown"),
                    request_id="legacy_dataframe_fallback",
                )

        return series.to_dataframe() if as_dataframe else series
