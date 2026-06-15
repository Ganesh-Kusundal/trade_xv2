"""Analytics Layer public API."""

from __future__ import annotations

import logging

import pandas as pd

from analytics.core.feature_builder import FeatureBuilder
from analytics.core.models import AnalysisResult
from analytics.core.providers import MarketDataProvider
from analytics.features.relative_strength import RelativeStrengthAnalyzer
from analytics.futures.futures_analytics import FuturesAnalytics
from analytics.market_breadth.breadth import BreadthAnalytics, SectorAnalytics
from analytics.options.options_analytics import OptionsAnalytics
from analytics.orderflow.orderflow import OrderFlowAnalytics
from analytics.probability.probability import ProbabilityEngine
from analytics.ranking.ranking import RankingEngine, RankingFacade
from analytics.scanner import MomentumScanner, VolumeScanner, RSScanner, BreakoutScanner
from analytics.scanner.models import ScanResult
from analytics.sector import SectorAnalyzer, SectorMapper
from analytics.stocks.stock_analytics import StockAnalytics
from analytics.strategy.models import Signal, SignalType, StrategyResult
from analytics.strategy.pipeline import StrategyPipeline
from analytics.replay import ReplayEngine, ReplayConfig, ReplayResult
from analytics.backtest import BacktestEngine, BacktestConfig, BacktestResult, PerformanceMetrics, TradeAnalysis
from analytics.paper import PaperTradingEngine, PaperConfig, PaperResult
from analytics.volatility.volatility_analytics import VolatilityAnalytics
from analytics.volume_profile.volume_profile import VolumeProfileBuilder

logger = logging.getLogger(__name__)


class Analytics:
    """Notebook-friendly facade for TradeXV2 analytics."""

    def __init__(self, provider: MarketDataProvider | None = None) -> None:
        self.provider = provider
        self.feature_builder = FeatureBuilder()
        self.stock_engine = StockAnalytics(self.feature_builder)
        self.future_engine = FuturesAnalytics()
        self.options_engine = OptionsAnalytics()
        self.volatility_engine = VolatilityAnalytics(self.feature_builder)
        self._volume_profile_builder = VolumeProfileBuilder()
        self._breadth = BreadthAnalytics()
        self._sectors = SectorAnalytics()
        self._scanners = {
            "momentum": MomentumScanner,
            "volume": VolumeScanner,
            "rs": RSScanner,
            "breakout": BreakoutScanner,
        }
        self._ranker = RankingEngine()
        self._probability = ProbabilityEngine()
        self._orderflow = OrderFlowAnalytics()
        self._strategy_pipeline = StrategyPipeline()
        self._sector_analyzer = SectorAnalyzer()

    @classmethod
    def from_provider(cls, provider: MarketDataProvider) -> Analytics:
        return cls(provider=provider)

    def fetch_history(
        self,
        symbol: str,
        *,
        timeframe: str = "1D",
        lookback_days: int = 120,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> AnalysisResult:
        if self.provider is None:
            return AnalysisResult(name="history", symbol=symbol, summary="No market-data provider configured.")
        data = self.provider.history(symbol, timeframe=timeframe, lookback_days=lookback_days, from_date=from_date, to_date=to_date)
        return AnalysisResult(
            name="history",
            symbol=symbol,
            summary=f"Fetched {len(data)} bars for {symbol}.",
            metrics={"bars": len(data), "columns": list(data.columns)},
            charts=[{"type": "history", "data": data.to_dict("records")[:1000]}],
        )

    def fetch_option_chain(self, underlying: str, *, expiry: str | None = None) -> AnalysisResult:
        if self.provider is None:
            return AnalysisResult(name="option_chain", symbol=underlying, summary="No market-data provider configured.")
        chain = self.provider.option_chain(underlying, expiry=expiry)
        strikes = chain.get("strikes", [])
        return AnalysisResult(
            name="option_chain",
            symbol=underlying,
            summary=f"Fetched {len(strikes)} option-chain strikes for {underlying}.",
            metrics={"strikes": len(strikes), "underlying": chain.get("underlying", underlying), "expiry": chain.get("expiry", expiry)},
            charts=[{"type": "option_chain", "data": strikes}],
        )

    def stock(
        self,
        symbol: str,
        prices: pd.DataFrame,
        benchmark_prices: pd.DataFrame | None = None,
        benchmark_symbol: str = "NIFTY",
        sector_prices: pd.DataFrame | None = None,
    ) -> AnalysisResult:
        logger.info("Analyzing stock %s (%d bars)", symbol, len(prices))
        return self.stock_engine.analyze(symbol, prices, benchmark_prices, benchmark_symbol, sector_prices)

    def future(
        self,
        symbol: str,
        *,
        spot_price: float | None = None,
        future_price: float | None = None,
        current_oi: float | None = None,
        next_oi: float | None = None,
        price_change: float = 0.0,
        oi_change: float = 0.0,
    ) -> AnalysisResult:
        logger.info("Analyzing future %s (spot=%s, future=%s)", symbol, spot_price, future_price)
        return self.future_engine.analyze(
            symbol,
            spot_price=spot_price,
            future_price=future_price,
            current_oi=current_oi,
            next_oi=next_oi,
            price_change=price_change,
            oi_change=oi_change,
        )

    def options(
        self,
        underlying: str,
        chain: pd.DataFrame | dict,
        *,
        spot_price: float | None = None,
        iv_history: list[float] | pd.Series | None = None,
    ) -> AnalysisResult:
        chain_len = len(chain) if isinstance(chain, pd.DataFrame) else len(chain.get("strikes", [])) if isinstance(chain, dict) else 0
        logger.info("Analyzing options %s (%d strikes)", underlying, chain_len)
        return self.options_engine.analyze(underlying, chain, spot_price=spot_price, iv_history=iv_history)

    def volatility(
        self,
        symbol: str,
        prices: pd.DataFrame,
        *,
        implied_volatility: float | None = None,
        iv_history: list[float] | pd.Series | None = None,
    ) -> AnalysisResult:
        logger.info("Analyzing volatility %s (%d bars)", symbol, len(prices))
        return self.volatility_engine.analyze(symbol, prices, implied_volatility=implied_volatility, iv_history=iv_history)

    def volume_profile(self, data: pd.DataFrame, *, symbol: str | None = None) -> AnalysisResult:
        logger.info("Building volume profile (%d bars)", len(data))
        return self._volume_profile_builder.build(data, symbol=symbol)

    def breadth(self, snapshot: pd.DataFrame | dict[str, float]) -> AnalysisResult:
        logger.info("Analyzing market breadth")
        return self._breadth.analyze(snapshot)

    def sectors(self, sectors: pd.DataFrame | None = None) -> AnalysisResult | SectorAnalyzer:
        """Sector analysis facade.

        If called with no arguments, returns the SectorAnalyzer for inspection.
        If called with data, runs full sector analysis and returns AnalysisResult.
        """
        if sectors is None:
            return self._sector_analyzer
        logger.info("Analyzing %d sectors", len(sectors))
        result = self._sector_analyzer.analyze(sectors)
        return self._sector_analyzer.to_analysis_result(result)

    def scan(self, data: pd.DataFrame | None = None, scanner: str | None = None) -> ScanResult | dict[str, type]:
        """Run a scanner on universe data.

        If called with no data, returns the dict of available scanners.
        If called with data, runs the specified scanner and returns ScanResult.
        """
        if data is None:
            return self._scanners
        scanner_name = scanner or "momentum"
        scanner_cls = self._scanners.get(scanner_name)
        if not scanner_cls:
            raise ValueError(f"Unknown scanner '{scanner_name}'. Available: {list(self._scanners.keys())}")
        logger.info("Running %s scanner on %d rows", scanner_name, len(data))
        s = scanner_cls()
        return s.scan(data)

    def rank(self, data: pd.DataFrame | None = None, *, name: str = "ranking") -> AnalysisResult | RankingFacade:
        if data is None:
            return RankingFacade(self._ranker)
        logger.info("Ranking %d instruments", len(data))
        return self._ranker.analyze(data, name=name)

    def probability(self, metrics: dict[str, float], *, symbol: str | None = None) -> AnalysisResult:
        logger.info("Computing probability for %s", symbol or "unknown")
        return self._probability.analyze(metrics, symbol=symbol)

    def orderflow(
        self,
        trades: pd.DataFrame | None = None,
        *,
        chain: pd.DataFrame | None = None,
    ) -> AnalysisResult:
        trade_count = len(trades) if trades is not None else 0
        chain_count = len(chain) if chain is not None else 0
        logger.info("Analyzing order flow (trades=%d, chain=%d)", trade_count, chain_count)
        return self._orderflow.analyze(trades, chain=chain)

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
            return self._strategy_pipeline
        from analytics.scanner.models import Candidate
        logger.info("Running strategy pipeline on %d candidates", len(candidates))
        return self._strategy_pipeline.evaluate(candidates, features_by_symbol or {})

    def replay(
        self,
        data: pd.DataFrame | None = None,
        *,
        symbol: str = "SYMBOL",
        config: ReplayConfig | None = None,
    ) -> ReplayEngine | ReplayResult:
        """Run historical replay through the same pipeline used in live trading.

        If called with no arguments, returns the ReplayEngine for configuration.
        If called with data, runs replay and returns ReplayResult.
        """
        if data is None:
            return ReplayEngine(pipeline=None, config=config)
        logger.info("Running replay on %d bars for %s", len(data), symbol)
        engine = ReplayEngine(pipeline=None, config=config)
        return engine.run(data, symbol=symbol)

    def backtest(
        self,
        data: pd.DataFrame | None = None,
        *,
        symbol: str = "SYMBOL",
        config: BacktestConfig | None = None,
        benchmark: pd.DataFrame | None = None,
    ) -> BacktestEngine | BacktestResult:
        """Run backtest with rich performance analytics.

        If called with no arguments, returns the BacktestEngine for configuration.
        If called with data, runs backtest and returns BacktestResult.
        """
        if data is None:
            return BacktestEngine(pipeline=None, config=config)
        logger.info("Running backtest on %d bars for %s", len(data), symbol)
        engine = BacktestEngine(pipeline=None, config=config)
        return engine.run(data, symbol=symbol, benchmark=benchmark)

    def paper(
        self,
        data: pd.DataFrame | None = None,
        *,
        symbol: str = "SYMBOL",
        config: PaperConfig | None = None,
    ) -> PaperTradingEngine | PaperResult:
        """Run paper trading — same pipeline as live, simulated fills.

        If called with no arguments, returns the PaperTradingEngine for configuration.
        If called with data, runs paper trading and returns PaperResult.
        """
        if data is None:
            return PaperTradingEngine(pipeline=None, config=config)
        logger.info("Running paper trading on %d bars for %s", len(data), symbol)
        engine = PaperTradingEngine(pipeline=None, config=config)
        return engine.run(data, symbol=symbol)


__all__ = [
    "AnalysisResult",
    "Analytics",
    "BacktestConfig",
    "BacktestEngine",
    "BacktestResult",
    "BreadthAnalytics",
    "BreakoutScanner",
    "FeatureBuilder",
    "FuturesAnalytics",
    "MarketDataProvider",
    "MomentumScanner",
    "OptionsAnalytics",
    "OrderFlowAnalytics",
    "PaperConfig",
    "PaperResult",
    "PaperTradingEngine",
    "PerformanceMetrics",
    "ProbabilityEngine",
    "RankingEngine",
    "RankingFacade",
    "RelativeStrengthAnalyzer",
    "ReplayConfig",
    "ReplayEngine",
    "ReplayResult",
    "RSScanner",
    "ScanResult",
    "SectorAnalyzer",
    "SectorMapper",
    "Signal",
    "SignalType",
    "StockAnalytics",
    "StrategyPipeline",
    "StrategyResult",
    "TradeAnalysis",
    "VolatilityAnalytics",
    "VolumeProfileBuilder",
    "VolumeScanner",
]
