"""Pipeline-backed feature fetcher for the TradingOrchestrator."""

from __future__ import annotations

import logging
from collections import OrderedDict
from datetime import date, timedelta
from typing import Any

import pandas as pd

from analytics.pipeline.pipeline import FeaturePipeline
from domain.historical import HistoricalSeries
from domain.models.features import FeatureSet
from domain.ports.market_data import MarketDataPort
from infrastructure.market_data_adapter import GatewayMarketDataAdapter

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
    """Fetch features for a symbol using FeaturePipeline + :class:`MarketDataPort`."""

    def __init__(
        self,
        pipeline: FeaturePipeline,
        market_data: MarketDataPort | Any | None = None,
        gateway: object | None = None,
        lookback_bars: int = 200,
        cache_max_entries: int = _DEFAULT_CACHE_MAX,
    ) -> None:
        self._pipeline = pipeline
        if market_data is not None:
            self._market_data = market_data
        elif gateway is not None:
            self._market_data = GatewayMarketDataAdapter(gateway)
        else:
            self._market_data = None
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
            df = _series_to_df(series).tail(self._lookback_bars).copy()
            features_df = self._pipeline.run(df)
            features = _df_to_feature_set(features_df)
            self._cache[cache_key] = features
            if len(self._cache) > self._cache_max:
                self._cache.popitem(last=False)
            return features
        except Exception as exc:
            logger.error("PipelineFeatureFetcher failed for %s: %s", symbol, exc)
            return FeatureSet.empty()


def _series_to_df(series: HistoricalSeries) -> pd.DataFrame:
    """Convert a HistoricalSeries back to a DataFrame for pipeline processing."""

    rows = []
    for bar in series.bars:
        rows.append({
            "date": bar.event_time,
            "open": float(bar.open),
            "high": float(bar.high),
            "low": float(bar.low),
            "close": float(bar.close),
            "volume": bar.volume,
        })
    return pd.DataFrame(rows)
