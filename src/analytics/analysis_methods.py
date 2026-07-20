"""Analysis methods for the Analytics facade.

Extracts the high-level analysis entry points (volume profile, breadth,
sectors, scan, rank, probability, orderflow, strategy) from
:class:`~analytics.facade.Analytics`. These methods delegate to the engines
exposed by :class:`~analytics.engine_factory.AnalyticsEngineFactory`.

This module is a leaf: it must not import from ``analytics.facade`` (circular
import guard).
"""

from __future__ import annotations

import logging

import pandas as pd

from analytics.core.models import AnalysisResult
from analytics.engine_factory import AnalyticsEngineFactory
from analytics.ranking.ranking import RankingFacade
from analytics.scanner.models import ScanResult
from analytics.sector import SectorAnalyzer
from analytics.strategy.models import StrategyResult
from analytics.strategy.pipeline import StrategyPipeline

logger = logging.getLogger(__name__)


class AnalyticsAnalysisMethods:
    """High-level analysis entry points backed by the analytics engines.

    The engine factory is injected via the constructor; all analysis methods
    read their engines lazily through it, preserving the original facade's
    on-demand construction behavior.
    """

    def __init__(self, engines: AnalyticsEngineFactory) -> None:
        self._engines = engines

    def volume_profile(self, data: pd.DataFrame, *, symbol: str | None = None) -> AnalysisResult:
        logger.info("Building volume profile (%d bars)", len(data))
        return self._engines._volume_profile_builder.build(data, symbol=symbol)

    def breadth(self, snapshot: pd.DataFrame | dict[str, float]) -> AnalysisResult:
        logger.info("Analyzing market breadth")
        return self._engines._breadth.analyze(snapshot)

    def sectors(self, sectors: pd.DataFrame | None = None) -> AnalysisResult | SectorAnalyzer:
        """Sector analysis facade.

        If called with no arguments, returns the SectorAnalyzer for inspection.
        If called with data, runs full sector analysis and returns AnalysisResult.
        """
        if sectors is None:
            return self._engines._sector_analyzer
        logger.info("Analyzing %d sectors", len(sectors))
        result = self._engines._sector_analyzer.analyze(sectors)
        return self._engines._sector_analyzer.to_analysis_result(result)

    def scan(
        self, data: pd.DataFrame | None = None, scanner: str | None = None
    ) -> ScanResult | dict[str, type]:
        """Run a scanner on universe data.

        If called with no data, returns the dict of available scanners.
        If called with data, runs the specified scanner and returns ScanResult.
        """
        if data is None:
            return self._engines._scanners
        scanner_name = scanner or "momentum"
        scanner_cls = self._engines._scanners.get(scanner_name)
        if not scanner_cls:
            raise ValueError(
                f"Unknown scanner '{scanner_name}'. Available: {list(self._engines._scanners.keys())}"
            )
        logger.info("Running %s scanner on %d rows", scanner_name, len(data))
        s = scanner_cls()
        return s.scan(data)

    def rank(
        self, data: pd.DataFrame | None = None, *, name: str = "ranking"
    ) -> AnalysisResult | RankingFacade:
        if data is None:
            return RankingFacade(self._engines._ranker)
        logger.info("Ranking %d instruments", len(data))
        return self._engines._ranker.analyze(data, name=name)

    def probability(
        self, metrics: dict[str, float], *, symbol: str | None = None
    ) -> AnalysisResult:
        logger.info("Computing probability for %s", symbol or "unknown")
        return self._engines._probability.analyze(metrics, symbol=symbol)

    def orderflow(
        self,
        trades: pd.DataFrame | None = None,
        *,
        chain: pd.DataFrame | None = None,
    ) -> AnalysisResult:
        trade_count = len(trades) if trades is not None else 0
        chain_count = len(chain) if chain is not None else 0
        logger.info("Analyzing order flow (trades=%d, chain=%d)", trade_count, chain_count)
        return self._engines._orderflow.analyze(trades, chain=chain)

    def strategy(
        self,
        candidates: list | None = None,
        features_by_symbol: dict[str, pd.DataFrame] | None = None,
    ) -> StrategyPipeline | list[StrategyResult]:
        """Evaluate candidates through the strategy pipeline.

        If called with no arguments, returns the StrategyPipeline for inspection.
        If called with candidates and features, runs evaluation and returns results.
        """
        if candidates is None:
            return self._engines._strategy_pipeline
        logger.info("Running strategy pipeline on %d candidates", len(candidates))
        return self._engines._strategy_pipeline.evaluate(candidates, features_by_symbol or {})
