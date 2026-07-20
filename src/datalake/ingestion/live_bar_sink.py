"""Live aggregated bars → datalake parquet (MD-001 increment 2).

ponytail: increment 2 only — 1m bars, synchronous merge-write on each close,
no catalog refresh, no multi-timeframe fan-out. Upgrade path: batch writes +
catalog.register after bar close, wire StreamOrchestrator path in parallel.
"""

from __future__ import annotations

import logging

import pandas as pd

from datalake.core.symbols import normalize_symbol_for_storage
from datalake.ingestion.loader import HistoricalDataLoader, WriteResult
from datalake.ingestion.normalize import ensure_timestamp_dtype
from domain.candles.historical import HistoricalBar

logger = logging.getLogger(__name__)


def historical_bar_to_dataframe(bar: HistoricalBar) -> pd.DataFrame:
    """Convert one :class:`HistoricalBar` to a single-row canonical DataFrame."""
    df = pd.DataFrame(
        [
            {
                "timestamp": bar.event_time,
                "symbol": normalize_symbol_for_storage(bar.symbol),
                "exchange": bar.exchange,
                "open": float(bar.open),
                "high": float(bar.high),
                "low": float(bar.low),
                "close": float(bar.close),
                "volume": int(bar.volume),
                "oi": int(bar.open_interest),
            }
        ]
    )
    return ensure_timestamp_dtype(df)


class LiveBarSink:
    """Persist completed live candles via :class:`HistoricalDataLoader` merge-write."""

    def __init__(
        self,
        root: str | None = None,
        catalog=None,
        loader: HistoricalDataLoader | None = None,
    ) -> None:
        self._loader = loader or HistoricalDataLoader(root=root, catalog=catalog)

    def write_bar(self, bar: HistoricalBar) -> WriteResult:
        """Merge one closed bar into hive-partitioned parquet."""
        df = historical_bar_to_dataframe(bar)
        if df.empty:
            return WriteResult(0, 0, 0, None, None)
        result = self._loader.merge_live_bar(bar, df)
        catalog = getattr(self._loader, "_catalog", None)
        if catalog is not None and result.last_ts is not None:
            last_date = pd.Timestamp(result.last_ts).date()
            path = self._loader._parquet_path(bar.symbol, bar.timeframe)
            catalog.register_symbol(
                bar.symbol,
                exchange=bar.exchange,
                last_date=last_date,
                total_rows=result.total_rows,
                timeframe=bar.timeframe,
                parquet_path=str(path),
            )
        logger.debug(
            "live_bar_sink.wrote symbol=%s tf=%s rows=%d total=%d",
            bar.symbol,
            bar.timeframe,
            result.rows,
            result.total_rows,
        )
        return result
