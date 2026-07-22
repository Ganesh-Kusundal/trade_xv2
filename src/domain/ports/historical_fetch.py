"""Historical fetch port — contract between datalake sync and broker federation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    import pandas as pd


class HistoricalFetchPort(Protocol):
    """Fetch OHLCV bars for one symbol over a lookback window from today.

    Implemented by ``application.data.sync_fetch_strategy.build_federated_fetch_fn``
    (production) or a single-broker gateway adapter (dev/ad-hoc). Injected into
    :func:`datalake.ingestion.auto_sync.sync_all` and
    :meth:`datalake.ingestion.loader.HistoricalDataLoader.download_symbol`.
    """

    def __call__(
        self,
        symbol: str,
        exchange: str,
        timeframe: str,
        lookback_days: int,
    ) -> "pd.DataFrame | Any": ...
