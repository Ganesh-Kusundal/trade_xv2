"""Pipeline-backed feature fetcher for the TradingOrchestrator."""

from __future__ import annotations

import logging
from collections import OrderedDict
from datetime import date, timedelta
from typing import Any

import pandas as pd

from domain.candles.historical import HistoricalSeries
from domain.models.features import FeatureSet
from domain.ports import MarketDataPort

logger = logging.getLogger(__name__)

_DEFAULT_CACHE_MAX = 256


def _df_to_feature_set(df: pd.DataFrame) -> FeatureSet:
    """Convert a pandas DataFrame to a FeatureSet domain type."""
    columns: dict[str, list] = {}
    for col in df.columns:
        columns[col] = df[col].tolist()
    index = df.index.tolist()
    return FeatureSet(columns=columns, index=index)


class PipelineFeatureFetcher:
    """Fetch features for a symbol using FeaturePipeline + :class:`GatewayMarketDataAdapter`."""

    def __init__(
        self,
        pipeline: Any,
        market_data: MarketDataPort | None = None,
        gateway: object | None = None,
        lookback_bars: int = 200,
        cache_max_entries: int = _DEFAULT_CACHE_MAX,
    ) -> None:
        self._pipeline = pipeline
        self._market_data = market_data
        self._lookback_bars = lookback_bars
        self._cache: OrderedDict[str, FeatureSet] = OrderedDict()
        self._cache_max = max(1, cache_max_entries)

    def fetch(self, symbol: str, exchange: str = "NSE") -> FeatureSet:
        """Return FeatureSet for *symbol* (latest row used by orchestrator)."""
        cache_key = f"{symbol}:{exchange}"
        if cache_key in self._cache:
            self._cache.move_to_end(cache_key)
            return self._cache[cache_key]

        if self._market_data is None:
            logger.warning("PipelineFeatureFetcher: no market data source for %s", symbol)
            return FeatureSet.empty()

        try:
            end = date.today()
            start = end - timedelta(days=30)
            series = self._market_data.history(symbol, start, end, interval="1m", exchange=exchange)
            if series is None or series.bar_count == 0:
                return FeatureSet.empty()
            df = series.to_dataframe().tail(self._lookback_bars).copy()
            features_df = self._pipeline.run(df)
            features = _df_to_feature_set(features_df)
            self._cache[cache_key] = features
            if len(self._cache) > self._cache_max:
                self._cache.popitem(last=False)
            return features
        except Exception as exc:
            logger.error("PipelineFeatureFetcher failed for %s: %s", symbol, exc)
            return FeatureSet.empty()

