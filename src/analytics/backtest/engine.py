"""BacktestEngine — wraps ReplayEngine with rich performance analytics.

The BacktestEngine uses the ReplayEngine for the bar-by-bar loop
(same pipeline as live), then computes comprehensive metrics:
    - Sharpe, Sortino, Calmar ratios
    - Profit factor, expected value
    - Max consecutive wins/losses
    - Benchmark comparison (alpha, beta, IR)
    - Trade analysis

=============================================================================
WARNING — ResearchMode.PURE_SIM IS RESEARCH-ONLY (NOT LIVE-PARITY)
=============================================================================
``ResearchMode.PURE_SIM`` runs fills without OMS risk gates, idempotency,
or order-lifecycle events. Default constructor mode is ``PARITY`` and
**requires** ``trading_context`` or ``oms_adapter``.

For standalone research without OMS, pass ``mode=ResearchMode.PURE_SIM`` explicitly.
Do NOT treat PURE_SIM equity / trade counts as a live-trading guarantee.
=============================================================================

Usage:
    from analytics.pipeline import FeaturePipeline, RSI, ATR, SMA
    from analytics.strategy import StrategyPipeline, MomentumStrategy
    from analytics.backtest import BacktestEngine, BacktestConfig

    pipeline = FeaturePipeline().add(RSI(14)).add(ATR(14)).add(SMA(20))
    strategy = StrategyPipeline(strategies=[MomentumStrategy()])
    config = BacktestConfig(initial_capital=100_000, warmup_bars=20)

    engine = BacktestEngine(pipeline, strategy, config)
    result = engine.run(data, benchmark_data=nifty_data)
    print(result.summary)
"""

from __future__ import annotations

import logging
from enum import Enum

import pandas as pd

from analytics.backtest.models import (
    BacktestConfig,
    BacktestResult,
    CapitalMetricsLabel,
    PerformanceMetrics,
    TradeAnalysis,
)
from analytics.pipeline.pipeline import FeaturePipeline
from analytics.replay.engine import ReplayEngine
from analytics.replay.models import ReplayResult, SimulatedTrade
from analytics.strategy.pipeline import StrategyPipeline
from domain.analytics.statistics import StatisticsEngine, TradeStatistics

logger = logging.getLogger(__name__)


class ResearchMode(str, Enum):
    """ENG-012 / F2f: explicit research vs live-parity simulation modes.

    !! PURE_SIM IS RESEARCH-ONLY — NOT A LIVE GUARANTEE !!

    pure_sim
        Fast research loop; may skip OMS risk / idempotency / order events.
        Must be passed explicitly. Results must **never** be cited as live-safe.
    parity
        Default constructor mode. Requires OMS/trading_context wiring.
    """

    PURE_SIM = "pure_sim"
    PARITY = "parity"


class BacktestEngine:
    """Backtest engine with rich performance analytics.

    Wraps ReplayEngine for the bar-by-bar loop, then computes
    comprehensive performance metrics and trade analysis.

    Parameters
    ----------
    pipeline:
        FeaturePipeline for computing indicators.
    strategy_pipeline:
        StrategyPipeline for signal generation.
    config:
        BacktestConfig with capital, slippage, benchmark, etc.
    mode:
        :class:`ResearchMode` — default ``parity`` (requires OMS context).
        Pass ``pure_sim`` explicitly for standalone research only.
    """

    def __init__(
        self,
        pipeline: FeaturePipeline | None = None,
        strategy_pipeline: StrategyPipeline | None = None,
        config: BacktestConfig | None = None,
        trading_context=None,
        execution_adapter=None,
        oms_adapter=None,
        mode: ResearchMode | str = ResearchMode.PARITY,
        allow_simulate_without_oms: bool | None = None,
    ) -> None:
        self._pipeline = pipeline or FeaturePipeline()
        self._strategy = strategy_pipeline or StrategyPipeline()
        self._config = config or BacktestConfig()
        self._trading_context = trading_context
        self._execution_adapter = execution_adapter
        self._mode = ResearchMode(mode) if not isinstance(mode, ResearchMode) else mode

        if self._mode is ResearchMode.PARITY:
            if trading_context is None and oms_adapter is None:
                raise ValueError(
                    "ResearchMode.PARITY requires trading_context or oms_adapter "
                    "(ENG-012). Use mode=pure_sim for standalone research."
                )
            allow_sim = False
        else:
            allow_sim = True
            logger.info("BacktestEngine mode=pure_sim — OMS optional; not live-parity (ENG-012)")
        if allow_simulate_without_oms is not None:
            allow_sim = allow_simulate_without_oms

        self._replay_engine = ReplayEngine(
            self._pipeline,
            self._strategy,
            self._config,
            trading_context=trading_context,
            execution_adapter=execution_adapter,
            oms_adapter=oms_adapter,
            allow_simulate_without_oms=allow_sim,
        )

    @property
    def mode(self) -> ResearchMode:
        return self._mode

    def run(
        self,
        data: pd.DataFrame,
        *,
        symbol: str = "SYMBOL",
        benchmark: pd.DataFrame | None = None,
    ) -> BacktestResult:
        """Run backtest and compute performance metrics.

        Parameters
        ----------
        data:
            OHLCV DataFrame with timestamp/date, open, high, low, close, volume.
        symbol:
            Symbol name.
        benchmark:
            Optional benchmark OHLCV data for comparison.

        Returns
        -------
        BacktestResult with replay data + performance metrics.
        """
        # Run replay
        replay_result = self._replay_engine.run(data, symbol=symbol)

        # Compute metrics
        metrics = self._compute_metrics(replay_result, benchmark)

        return BacktestResult(
            replay=replay_result,
            metrics=metrics,
            benchmark_data=benchmark,
            equity_curve=replay_result.session.equity_curve,
            capital_metrics_label=(
                CapitalMetricsLabel.PARITY
                if self._mode is ResearchMode.PARITY
                else CapitalMetricsLabel.RESEARCH
            ),
            metadata={
                "research_mode": self._mode.value,
                "capital_metrics_valid": self._mode is ResearchMode.PARITY,
            },
        )

    def _compute_metrics(
        self,
        replay: ReplayResult,
        benchmark: pd.DataFrame | None = None,
    ) -> PerformanceMetrics:
        """Compute all performance metrics via the standalone StatisticsEngine."""
        session = replay.session
        config = self._config

        metrics = PerformanceMetrics()

        initial = session.equity_curve[0][1] if session.equity_curve else 0.0
        final = session.current_equity

        computed = StatisticsEngine.compute(
            session.equity_curve,
            session.trades,
            initial=float(initial),
            final=float(final),
            annualization_factor=config.annualization_factor,
            risk_free_rate=config.risk_free_rate,
            benchmark=benchmark,
        )

        metrics.total_return = computed["total_return"]
        metrics.total_return_pct = computed["total_return_pct"]
        metrics.cagr = computed["cagr"]
        metrics.volatility = computed.get("volatility", 0.0)
        metrics.sharpe_ratio = computed.get("sharpe_ratio", 0.0)
        metrics.sortino_ratio = computed.get("sortino_ratio", 0.0)
        metrics.max_drawdown = computed["max_drawdown"]
        metrics.max_drawdown_duration = computed["max_drawdown_duration"]
        metrics.calmar_ratio = computed["calmar_ratio"]
        metrics.trade_analysis = self._trade_analysis_from_stats(computed["trade_analysis"])

        for key in ("alpha", "beta", "benchmark_return", "tracking_error", "information_ratio"):
            if key in computed:
                setattr(metrics, key, computed[key])

        return metrics

    @staticmethod
    def _trade_analysis_from_stats(stats: TradeStatistics) -> TradeAnalysis:
        """Copy pure :class:`TradeStatistics` into the analytics ``TradeAnalysis``."""
        return TradeAnalysis(
            total_trades=stats.total_trades,
            winning_trades=stats.winning_trades,
            losing_trades=stats.losing_trades,
            win_rate=stats.win_rate,
            avg_win=stats.avg_win,
            avg_loss=stats.avg_loss,
            avg_win_pct=stats.avg_win_pct,
            avg_loss_pct=stats.avg_loss_pct,
            largest_win=stats.largest_win,
            largest_loss=stats.largest_loss,
            avg_holding_bars=stats.avg_holding_bars,
            profit_factor=stats.profit_factor,
            expected_value=stats.expected_value,
            payoff_ratio=stats.payoff_ratio,
            max_consecutive_wins=stats.max_consecutive_wins,
            max_consecutive_losses=stats.max_consecutive_losses,
            total_pnl=stats.total_pnl,
            total_pnl_pct=stats.total_pnl_pct,
            trades_by_strategy=stats.trades_by_strategy,
            avg_entry_confidence=stats.avg_entry_confidence,
        )

    def _analyze_trades(self, trades: list[SimulatedTrade]) -> TradeAnalysis:
        """Analyze all completed trades (delegates to the StatisticsEngine)."""
        stats = StatisticsEngine.analyze_trades(trades)
        return self._trade_analysis_from_stats(stats)
