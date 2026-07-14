"""Analytics facade — notebook-friendly entry point.

This module is intentionally thin. The heavy lifting lives in three focused
modules that this facade composes:

* :mod:`analytics.engine_factory` — lazy construction/caching of every engine.
* :mod:`analytics.data_fetcher` — ``fetch_history`` / ``fetch_option_chain``.
* :mod:`analytics.analysis_methods` — the high-level analysis entry points.

The ``Analytics`` class keeps only construction, the ``from_*`` factories, and
thin delegation so the public API is unchanged (backward compatible).
"""

from __future__ import annotations

import logging

import pandas as pd

from analytics.analysis_methods import AnalyticsAnalysisMethods
from analytics.backtest import (
    BacktestConfig,
    BacktestEngine,
    BacktestResult,
    ResearchMode,
)
from analytics.core.instrument_analyzer import InstrumentAnalyzer
from analytics.core.models import AnalysisResult
from analytics.core.providers import MarketDataProvider
from analytics.data_fetcher import AnalyticsDataFetcher
from analytics.engine_factory import AnalyticsEngineFactory
from analytics.paper import PaperConfig, PaperResult, PaperTradingEngine
from analytics.pipeline.pipeline import FeaturePipeline
from analytics.ranking.ranking import RankingFacade
from analytics.replay import ReplayConfig, ReplayEngine, ReplayResult
from analytics.scanner.models import ScanResult
from analytics.sector import SectorAnalyzer
from analytics.strategy.models import StrategyResult
from analytics.strategy.pipeline import StrategyPipeline
from analytics.walk_forward import WalkForwardConfig, WalkForwardEngine, WalkForwardResult
from domain.instruments.instrument import Instrument
from domain.constants.market import DEFAULT_RISK_FREE_RATE
from domain.ports.data_catalog import DEFAULT_DATA_ROOT

logger = logging.getLogger(__name__)


class Analytics:
    """Notebook-friendly facade for TradeXV2 analytics.

    Engines are lazily initialized on first access (via
    :class:`AnalyticsEngineFactory`) to avoid the overhead of instantiating all
    15+ engines when only a subset is needed.
    """

    def __init__(self, provider: MarketDataProvider | None = None) -> None:
        self.provider = provider
        self._instrument: Instrument | None = None
        self._instrument_analyzer: InstrumentAnalyzer | None = None
        self._engines = AnalyticsEngineFactory(provider=provider)
        self._fetcher = AnalyticsDataFetcher(
            provider=provider,
            instrument=self._instrument,
            instrument_analyzer=self._instrument_analyzer,
            engines=self._engines,
        )
        self._analysis = AnalyticsAnalysisMethods(self._engines)
        self._cache: dict[str, object] = {}

    # ------------------------------------------------------------------ #
    # Factory methods (must stay here: they construct Analytics, so they
    # cannot live in a module that imports this class).
    # ------------------------------------------------------------------ #
    @classmethod
    def from_provider(cls, provider: MarketDataProvider) -> Analytics:
        return cls(provider=provider)

    @classmethod
    def from_instrument(cls, instrument: Instrument) -> Analytics:
        """Create an Analytics instance from an Instrument.

        New code should prefer this over from_provider().
        """
        instance = cls()
        instance._instrument = instrument
        instance._instrument_analyzer = InstrumentAnalyzer()
        # Keep the data fetcher in sync with the instrument set here.
        instance._fetcher._instrument = instrument
        instance._fetcher._instrument_analyzer = instance._instrument_analyzer
        return instance

    @classmethod
    def from_datalake(cls, root: str = DEFAULT_DATA_ROOT) -> Analytics:
        """Create an Analytics instance backed by the local data lake.

        This is the recommended entry point for notebook / CLI usage.
        All historical data flows through
        :class:`~datalake.adapters.analytics_provider.DataLakeMarketDataProvider`,
        which implements :class:`~domain.ports.market_data.MarketDataPort`.
        """
        from datalake.adapters.analytics_provider import DataLakeMarketDataProvider

        return cls(provider=DataLakeMarketDataProvider(root=root))

    # ------------------------------------------------------------------ #
    # Engine accessors — delegate to the engine factory (backward compat).
    # ------------------------------------------------------------------ #
    @property
    def feature_builder(self):
        return self._engines.feature_builder

    @property
    def stock_engine(self):
        return self._engines.stock_engine

    @property
    def future_engine(self):
        return self._engines.future_engine

    @property
    def options_engine(self):
        return self._engines.options_engine

    @property
    def volatility_engine(self):
        return self._engines.volatility_engine

    @property
    def _volume_profile_builder(self):
        return self._engines._volume_profile_builder

    @property
    def _breadth(self):
        return self._engines._breadth

    @property
    def _sectors(self):
        return self._engines._sectors

    @property
    def _scanners(self):
        return self._engines._scanners

    @property
    def _ranker(self):
        return self._engines._ranker

    @property
    def _probability(self):
        return self._engines._probability

    @property
    def _orderflow(self):
        return self._engines._orderflow

    @property
    def _strategy_pipeline(self):
        return self._engines._strategy_pipeline

    @property
    def _sector_analyzer(self):
        return self._engines._sector_analyzer

    # ------------------------------------------------------------------ #
    # Statistics (Tier 2-E) — kept on the facade.
    # ------------------------------------------------------------------ #
    @property
    def statistics_engine(self):
        """Lazily-created standalone StatisticsEngine (Tier 2-E).

        Lets callers compute performance metrics from an equity curve and
        trades directly, without running a full backtest or replay.
        """
        if "statistics" not in self._cache:
            from domain.analytics.statistics import StatisticsEngine

            self._cache["statistics"] = StatisticsEngine()
        return self._cache["statistics"]

    def statistics(
        self,
        equity_curve: list,
        trades: list | None = None,
        *,
        annualization_factor: int = 252,
        risk_free_rate: float = DEFAULT_RISK_FREE_RATE,
        benchmark: pd.DataFrame | None = None,
    ) -> dict:
        """Compute performance metrics directly from an equity curve + trades.

        Parameters
        ----------
        equity_curve:
            Sequence of ``(timestamp, equity)`` samples.
        trades:
            Optional iterable of completed trades (any objects exposing
            ``.pnl``, ``.pnl_pct``, ``.entry_time``, ``.exit_time``,
            ``.strategy``).
        annualization_factor, risk_free_rate:
            Annualization parameters forwarded to the StatisticsEngine.
        benchmark:
            Optional benchmark OHLCV DataFrame for alpha/beta/IR.

        Returns
        -------
        Dict with the same metric keys produced by the backtest engine.
        """
        trades = trades or []
        initial = equity_curve[0][1] if equity_curve else 0.0
        final = equity_curve[-1][1] if equity_curve else 0.0
        return self.statistics_engine.compute(
            equity_curve,
            trades,
            initial=initial,
            final=final,
            annualization_factor=annualization_factor,
            risk_free_rate=risk_free_rate,
            benchmark=benchmark,
        )

    @property
    def has_instrument(self) -> bool:
        """True when created via from_instrument()."""
        return self._instrument is not None

    # ------------------------------------------------------------------ #
    # Data fetching — delegate to the data fetcher.
    # ------------------------------------------------------------------ #
    def fetch_history(
        self,
        symbol: str | Instrument | None = None,
        *,
        timeframe: str = "1D",
        lookback_days: int = 120,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> AnalysisResult:
        return self._fetcher.fetch_history(
            symbol,
            timeframe=timeframe,
            lookback_days=lookback_days,
            from_date=from_date,
            to_date=to_date,
        )

    def fetch_option_chain(
        self,
        underlying: str | Instrument | None = None,
        *,
        expiry: str | None = None,
    ) -> AnalysisResult:
        return self._fetcher.fetch_option_chain(underlying, expiry=expiry)

    # ------------------------------------------------------------------ #
    # Symbol-level analysis methods — delegate to the data fetcher, which
    # owns the instrument/analyzer and the engines.
    # ------------------------------------------------------------------ #
    def stock(
        self,
        symbol: str | Instrument | None = None,
        prices: pd.DataFrame | None = None,
        benchmark_prices: pd.DataFrame | None = None,
        benchmark_symbol: str = "NIFTY",
        sector_prices: pd.DataFrame | None = None,
    ) -> AnalysisResult:
        return self._fetcher.stock(
            symbol,
            prices=prices,
            benchmark_prices=benchmark_prices,
            benchmark_symbol=benchmark_symbol,
            sector_prices=sector_prices,
        )

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
        return self._fetcher.future(
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
        underlying: str | Instrument | None = None,
        chain: pd.DataFrame | dict | None = None,
        *,
        spot_price: float | None = None,
        iv_history: list[float] | pd.Series | None = None,
    ) -> AnalysisResult:
        return self._fetcher.options(
            underlying,
            chain=chain,
            spot_price=spot_price,
            iv_history=iv_history,
        )

    def volatility(
        self,
        symbol: str | Instrument | None = None,
        prices: pd.DataFrame | None = None,
        *,
        implied_volatility: float | None = None,
        iv_history: list[float] | pd.Series | None = None,
    ) -> AnalysisResult:
        return self._fetcher.volatility(
            symbol,
            prices=prices,
            implied_volatility=implied_volatility,
            iv_history=iv_history,
        )

    # ------------------------------------------------------------------ #
    # Analysis methods — delegate to the analysis-methods module.
    # ------------------------------------------------------------------ #
    def volume_profile(self, data: pd.DataFrame, *, symbol: str | None = None) -> AnalysisResult:
        return self._analysis.volume_profile(data, symbol=symbol)

    def breadth(self, snapshot: pd.DataFrame | dict[str, float]) -> AnalysisResult:
        return self._analysis.breadth(snapshot)

    def sectors(self, sectors: pd.DataFrame | None = None) -> AnalysisResult | SectorAnalyzer:
        return self._analysis.sectors(sectors)

    def scan(
        self, data: pd.DataFrame | None = None, scanner: str | None = None
    ) -> ScanResult | dict[str, type]:
        return self._analysis.scan(data, scanner=scanner)

    def rank(
        self, data: pd.DataFrame | None = None, *, name: str = "ranking"
    ) -> AnalysisResult | RankingFacade:
        return self._analysis.rank(data, name=name)

    def probability(
        self, metrics: dict[str, float], *, symbol: str | None = None
    ) -> AnalysisResult:
        return self._analysis.probability(metrics, symbol=symbol)

    def orderflow(
        self,
        trades: pd.DataFrame | None = None,
        *,
        chain: pd.DataFrame | None = None,
    ) -> AnalysisResult:
        return self._analysis.orderflow(trades, chain=chain)

    def strategy(
        self,
        candidates: list | None = None,
        features_by_symbol: dict[str, pd.DataFrame] | None = None,
    ) -> StrategyPipeline | list[StrategyResult]:
        return self._analysis.strategy(candidates, features_by_symbol=features_by_symbol)

    # ------------------------------------------------------------------ #
    # Replay / backtest / paper — kept on the facade (not in the plan's
    # extraction set).
    # ------------------------------------------------------------------ #
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
            return ReplayEngine(config=config)
        logger.info("Running replay on %d bars for %s", len(data), symbol)
        engine = ReplayEngine(config=config)
        return engine.run(data, symbol=symbol)

    def backtest(
        self,
        data: pd.DataFrame | None = None,
        *,
        symbol: str = "SYMBOL",
        config: BacktestConfig | None = None,
        benchmark: pd.DataFrame | None = None,
        trading_context: object | None = None,
        mode: ResearchMode | str = ResearchMode.PURE_SIM,
    ) -> BacktestEngine | BacktestResult:
        """Run backtest with rich performance analytics.

        If called with no arguments, returns the BacktestEngine for configuration.
        If called with data, runs backtest and returns BacktestResult.

        trading_context / mode:
            Pass a real ``TradingContext`` (e.g. from
            ``application.oms.factory.create_trading_context``) with
            ``mode=ResearchMode.PARITY`` to route fills through the real OMS
            (RiskManager, IdempotencyGuard, order FSM) instead of PURE_SIM.
        """
        engine = BacktestEngine(
            config=config, trading_context=trading_context, mode=mode
        )
        if data is None:
            return engine
        logger.info("Running backtest on %d bars for %s", len(data), symbol)
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
            return PaperTradingEngine(config=config)
        logger.info("Running paper trading on %d bars for %s", len(data), symbol)
        engine = PaperTradingEngine(config=config)
        return engine.run(data, symbol=symbol)

    def walk_forward(
        self,
        data: pd.DataFrame | None = None,
        *,
        symbol: str = "SYMBOL",
        pipeline: FeaturePipeline | None = None,
        strategy_pipeline: StrategyPipeline | None = None,
        config: WalkForwardConfig | None = None,
        max_workers: int | None = None,
    ) -> WalkForwardEngine | WalkForwardResult:
        """Run rolling train/test walk-forward validation over a single OHLCV series.

        If called with no arguments, returns the WalkForwardEngine for configuration.
        If called with data, runs walk-forward and returns WalkForwardResult.
        """
        engine = WalkForwardEngine(
            pipeline or FeaturePipeline(),
            strategy_pipeline or StrategyPipeline(),
            config=config,
        )
        if data is None:
            return engine
        logger.info("Running walk-forward on %d bars for %s", len(data), symbol)
        return engine.run(data, symbol=symbol, max_workers=max_workers)
