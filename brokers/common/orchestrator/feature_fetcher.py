"""Pipeline-backed feature fetcher for the TradingOrchestrator."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

import pandas as pd

from analytics.pipeline.pipeline import FeaturePipeline

logger = logging.getLogger(__name__)


class PipelineFeatureFetcher:
    """Fetch features for a symbol using FeaturePipeline + gateway history."""

    def __init__(
        self,
        pipeline: FeaturePipeline,
        gateway: Any | None = None,
        lookback_bars: int = 200,
    ) -> None:
        self._pipeline = pipeline
        self._gateway = gateway
        self._lookback_bars = lookback_bars
        self._cache: dict[str, pd.DataFrame] = {}

    def fetch(self, symbol: str, exchange: str = "NSE") -> pd.DataFrame:
        """Return feature DataFrame for *symbol* (latest row used by orchestrator)."""
        cache_key = f"{symbol}:{exchange}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        if self._gateway is None:
            logger.warning("PipelineFeatureFetcher: no gateway for %s", symbol)
            return pd.DataFrame()

        try:
            end = date.today()
            start = end - timedelta(days=30)
            history_fn = getattr(self._gateway, "history", None)
            if history_fn is None:
                return pd.DataFrame()
            df = history_fn(symbol, start, end, interval="1m", exchange=exchange)
            if df is None or df.empty:
                return pd.DataFrame()
            df = df.tail(self._lookback_bars).copy()
            features = self._pipeline.run(df)
            self._cache[cache_key] = features
            return features
        except Exception as exc:
            logger.error("PipelineFeatureFetcher failed for %s: %s", symbol, exc)
            return pd.DataFrame()
