"""Pipeline-backed feature fetcher for the TradingOrchestrator."""

from __future__ import annotations

import logging
from collections import OrderedDict
from datetime import date, timedelta
from typing import Any

import pandas as pd

from analytics.pipeline.pipeline import FeaturePipeline
from domain.ports.market_data import GatewayMarketDataAdapter, MarketDataPort

logger = logging.getLogger(__name__)

_DEFAULT_CACHE_MAX = 256


class PipelineFeatureFetcher:
    """Fetch features for a symbol using FeaturePipeline + :class:`MarketDataPort`."""

    def __init__(
        self,
        pipeline: FeaturePipeline,
        market_data: MarketDataPort | Any | None = None,
        gateway: object | None = None,  # MarketDataGateway (avoid circular import)
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
        self._cache: OrderedDict[str, pd.DataFrame] = OrderedDict()
        self._cache_max = max(1, cache_max_entries)

    def fetch(self, symbol: str, exchange: str = "NSE") -> pd.DataFrame:
        """Return feature DataFrame for *symbol* (latest row used by orchestrator)."""
        cache_key = f"{symbol}:{exchange}"
        if cache_key in self._cache:
            self._cache.move_to_end(cache_key)
            return self._cache[cache_key]

        if self._market_data is None:
            logger.warning("PipelineFeatureFetcher: no market data source for %s", symbol)
            return pd.DataFrame()

        try:
            end = date.today()
            start = end - timedelta(days=30)
            df = self._market_data.history(symbol, start, end, interval="1m", exchange=exchange)
            if df is None or df.empty:
                return pd.DataFrame()
            df = df.tail(self._lookback_bars).copy()
            features = self._pipeline.run(df)
            self._cache[cache_key] = features
            if len(self._cache) > self._cache_max:
                self._cache.popitem(last=False)
            return features
        except Exception as exc:
            logger.error("PipelineFeatureFetcher failed for %s: %s", symbol, exc)
            return pd.DataFrame()
