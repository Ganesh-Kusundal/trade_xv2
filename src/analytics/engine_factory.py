"""Engine factory for the Analytics facade.

Holds the lazy construction and memoization of every analytics engine used by
:class:`~analytics.facade.Analytics`. Extracted from the facade so the facade
stays thin and the engine wiring has a single, testable home.

This module is a leaf: it must not import from ``analytics.facade`` (circular
import guard).
"""

from __future__ import annotations

import logging

from analytics.core.feature_builder import FeatureBuilder
from analytics.futures.futures_analytics import FuturesAnalytics
from analytics.market_breadth.breadth import BreadthAnalytics, SectorAnalytics
from analytics.options.options_analytics import OptionsAnalytics
from analytics.orderflow.orderflow import OrderFlowAnalytics
from analytics.probability.probability import ProbabilityEngine
from analytics.ranking.ranking import RankingEngine
from analytics.scanner import BreakoutScanner, MomentumScanner, RSScanner, VolumeScanner
from analytics.sector import SectorAnalyzer
from analytics.stocks.stock_analytics import StockAnalytics
from analytics.strategy.pipeline import StrategyPipeline
from analytics.volatility.volatility_analytics import VolatilityAnalytics
from analytics.volume_profile.volume_profile import VolumeProfileBuilder

logger = logging.getLogger(__name__)


class AnalyticsEngineFactory:
    """Lazily builds and caches the analytics engine instances.

    Mirrors the original facade's lazy-property behavior: each engine is created
    on first access and memoized in an internal cache. A single
    :meth:`build_engines` entry point is provided for callers that want every
    engine materialized up front.
    """

    def __init__(self, provider=None) -> None:
        # ``provider`` is accepted only to mirror Analytics.__init__'s signature.
        # The real consumer of provider is AnalyticsDataFetcher (data_fetcher.py);
        # every engine here is pure computation over DataFrames passed by callers
        # and has no data source of its own to inject.
        self.provider = provider
        self._feature_builder: FeatureBuilder | None = None
        self._cache: dict[str, object] = {}

    @property
    def feature_builder(self) -> FeatureBuilder:
        if self._feature_builder is None:
            self._feature_builder = FeatureBuilder()
        return self._feature_builder

    @property
    def stock_engine(self) -> StockAnalytics:
        if "stock" not in self._cache:
            self._cache["stock"] = StockAnalytics(self.feature_builder)
        return self._cache["stock"]  # type: ignore[return-value]

    @property
    def future_engine(self) -> FuturesAnalytics:
        if "future" not in self._cache:
            self._cache["future"] = FuturesAnalytics()
        return self._cache["future"]  # type: ignore[return-value]

    @property
    def options_engine(self) -> OptionsAnalytics:
        if "options" not in self._cache:
            self._cache["options"] = OptionsAnalytics()
        return self._cache["options"]  # type: ignore[return-value]

    @property
    def volatility_engine(self) -> VolatilityAnalytics:
        if "volatility" not in self._cache:
            self._cache["volatility"] = VolatilityAnalytics(self.feature_builder)
        return self._cache["volatility"]  # type: ignore[return-value]

    @property
    def _volume_profile_builder(self) -> VolumeProfileBuilder:
        if "volume_profile" not in self._cache:
            self._cache["volume_profile"] = VolumeProfileBuilder()
        return self._cache["volume_profile"]  # type: ignore[return-value]

    @property
    def _breadth(self) -> BreadthAnalytics:
        if "breadth" not in self._cache:
            self._cache["breadth"] = BreadthAnalytics()
        return self._cache["breadth"]  # type: ignore[return-value]

    @property
    def _sectors(self) -> SectorAnalytics:
        if "sectors" not in self._cache:
            self._cache["sectors"] = SectorAnalytics()
        return self._cache["sectors"]  # type: ignore[return-value]

    @property
    def _scanners(self) -> dict[str, type]:
        if "scanners" not in self._cache:
            # TOS-P6-001: default set is a registry dict; drop-in scanners
            # can extend this map without editing call sites that only read it.
            self._cache["scanners"] = {
                "momentum": MomentumScanner,
                "volume": VolumeScanner,
                "rs": RSScanner,
                "breakout": BreakoutScanner,
            }
            # Optional extension hook: analytics.scanner.plugins if present.
            try:
                from analytics.scanner import plugins as _scan_plugins  # type: ignore

                extra = getattr(_scan_plugins, "SCANNER_REGISTRY", None)
                if isinstance(extra, dict):
                    self._cache["scanners"].update(extra)  # type: ignore[union-attr]
            except ImportError:
                pass
        return self._cache["scanners"]  # type: ignore[return-value]

    @property
    def _ranker(self) -> RankingEngine:
        if "ranker" not in self._cache:
            self._cache["ranker"] = RankingEngine()
        return self._cache["ranker"]  # type: ignore[return-value]

    @property
    def _probability(self) -> ProbabilityEngine:
        if "probability" not in self._cache:
            self._cache["probability"] = ProbabilityEngine()
        return self._cache["probability"]  # type: ignore[return-value]

    @property
    def _orderflow(self) -> OrderFlowAnalytics:
        if "orderflow" not in self._cache:
            self._cache["orderflow"] = OrderFlowAnalytics()
        return self._cache["orderflow"]  # type: ignore[return-value]

    @property
    def _strategy_pipeline(self) -> StrategyPipeline:
        if "strategy_pipeline" not in self._cache:
            self._cache["strategy_pipeline"] = StrategyPipeline()
        return self._cache["strategy_pipeline"]  # type: ignore[return-value]

    @property
    def _sector_analyzer(self) -> SectorAnalyzer:
        if "sector_analyzer" not in self._cache:
            self._cache["sector_analyzer"] = SectorAnalyzer()
        return self._cache["sector_analyzer"]  # type: ignore[return-value]

    @classmethod
    def build_engines(cls, provider=None) -> dict[str, object]:
        """Materialize and return a dict of all engine instances.

        Engines are created through the lazy accessors so the memoization cache
        is populated exactly as it would be during normal facade use.
        """
        factory = cls(provider=provider)
        return {
            "feature_builder": factory.feature_builder,
            "stock": factory.stock_engine,
            "future": factory.future_engine,
            "options": factory.options_engine,
            "volatility": factory.volatility_engine,
            "volume_profile": factory._volume_profile_builder,
            "breadth": factory._breadth,
            "sectors": factory._sectors,
            "scanners": factory._scanners,
            "ranker": factory._ranker,
            "probability": factory._probability,
            "orderflow": factory._orderflow,
            "strategy_pipeline": factory._strategy_pipeline,
            "sector_analyzer": factory._sector_analyzer,
        }
