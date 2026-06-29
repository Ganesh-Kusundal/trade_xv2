"""BacktestEngine — wraps ReplayEngine with rich performance analytics.

The BacktestEngine uses the ReplayEngine for the bar-by-bar loop
(same pipeline as live), then computes comprehensive metrics:
    - Sharpe, Sortino, Calmar ratios
    - Profit factor, expected value
    - Max consecutive wins/losses
    - Benchmark comparison (alpha, beta, IR)
    - Trade analysis

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

import numpy as np
import pandas as pd

from analytics.backtest.models import (
    BacktestConfig,
    BacktestResult,
    PerformanceMetrics,
    TradeAnalysis,
)
from analytics.pipeline.pipeline import FeaturePipeline
from analytics.replay.engine import ReplayEngine
from analytics.replay.models import ReplayResult, SimulatedTrade
from analytics.strategy.pipeline import StrategyPipeline

logger = logging.getLogger(__name__)


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
    """

    def __init__(
        self,
        pipeline: FeaturePipeline | None = None,
        strategy_pipeline: StrategyPipeline | None = None,
        config: BacktestConfig | None = None,
        trading_context=None,
        execution_adapter=None,
        oms_adapter=None,
    ) -> None:
        self._pipeline = pipeline or FeaturePipeline()
        self._strategy = strategy_pipeline or StrategyPipeline()
        self._config = config or BacktestConfig()
        self._trading_context = trading_context
        self._execution_adapter = execution_adapter
        self._replay_engine = ReplayEngine(
            self._pipeline,
            self._strategy,
            self._config,
            trading_context=trading_context,
            execution_adapter=execution_adapter,
            oms_adapter=oms_adapter,
        )

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
        )

    def _compute_metrics(
        self,
        replay: ReplayResult,
        benchmark: pd.DataFrame | None = None,
    ) -> PerformanceMetrics:
        """Compute all performance metrics from replay result."""
        session = replay.session
        config = self._config

        metrics = PerformanceMetrics()

        # Basic return
        if session.equity_curve:
            initial = session.equity_curve[0][1]
            final = session.current_equity
            metrics.total_return = final - initial
            metrics.total_return_pct = ((final / initial) - 1) if initial > 0 else 0.0

            # CAGR
            if len(session.equity_curve) >= 2:
                years = len(session.equity_curve) / config.annualization_factor
                if years > 0 and initial > 0:
                    metrics.cagr = (final / initial) ** (1 / years) - 1

        # Trade analysis
        metrics.trade_analysis = self._analyze_trades(session.trades)

        # Risk metrics from equity curve
        if len(session.equity_curve) >= 2:
            equities = np.array([eq for _, eq in session.equity_curve])
            returns = np.diff(equities) / equities[:-1]
            returns = returns[np.isfinite(returns)]

            if len(returns) > 0:
                # Volatility (annualized)
                metrics.volatility = float(np.std(returns) * np.sqrt(config.annualization_factor))

                # Sharpe ratio
                rf_per_bar = config.risk_free_rate / config.annualization_factor
                excess_returns = returns - rf_per_bar
                if np.std(excess_returns) > 0:
                    metrics.sharpe_ratio = float(
                        np.mean(excess_returns)
                        / np.std(excess_returns)
                        * np.sqrt(config.annualization_factor)
                    )

                # Sortino ratio (downside deviation only)
                downside = returns[returns < 0]
                if len(downside) > 0 and np.std(downside) > 0:
                    metrics.sortino_ratio = float(
                        np.mean(excess_returns)
                        / np.std(downside)
                        * np.sqrt(config.annualization_factor)
                    )

                # Max drawdown
                peak = np.maximum.accumulate(equities)
                drawdown = (peak - equities) / peak
                drawdown = drawdown[np.isfinite(drawdown)]
                if len(drawdown) > 0:
                    metrics.max_drawdown = float(np.max(drawdown))

                # Max drawdown duration
                peak_idx = np.argmax(equities)
                trough_idx = (
                    np.argmin(equities[peak_idx:]) + peak_idx
                    if peak_idx < len(equities)
                    else len(equities) - 1
                )
                metrics.max_drawdown_duration = int(trough_idx - peak_idx)

        # Calmar ratio
        if metrics.max_drawdown > 0:
            metrics.calmar_ratio = metrics.cagr / metrics.max_drawdown

        # Benchmark comparison
        if benchmark is not None and not benchmark.empty:
            bench_metrics = self._compute_benchmark_metrics(session.equity_curve, benchmark, config)
            metrics.alpha = bench_metrics.get("alpha", 0.0)
            metrics.beta = bench_metrics.get("beta", 0.0)
            metrics.benchmark_return = bench_metrics.get("benchmark_return", 0.0)
            metrics.tracking_error = bench_metrics.get("tracking_error", 0.0)
            metrics.information_ratio = bench_metrics.get("information_ratio", 0.0)

        return metrics

    def _analyze_trades(self, trades: list[SimulatedTrade]) -> TradeAnalysis:
        """Analyze all completed trades."""
        analysis = TradeAnalysis()
        if not trades:
            return analysis

        analysis.total_trades = len(trades)

        wins = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl <= 0]

        analysis.winning_trades = len(wins)
        analysis.losing_trades = len(losses)
        analysis.win_rate = len(wins) / len(trades) if trades else 0.0

        # Win/loss amounts
        if wins:
            analysis.avg_win = float(np.mean([t.pnl for t in wins]))
            analysis.avg_win_pct = float(np.mean([t.pnl_pct for t in wins]))
            analysis.largest_win = float(max(t.pnl for t in wins))
        if losses:
            analysis.avg_loss = float(np.mean([t.pnl for t in losses]))
            analysis.avg_loss_pct = float(np.mean([t.pnl_pct for t in losses]))
            analysis.largest_loss = float(min(t.pnl for t in losses))

        # Profit factor
        total_wins = sum(t.pnl for t in wins)
        total_losses = abs(sum(t.pnl for t in losses))
        analysis.profit_factor = (
            total_wins / total_losses
            if total_losses > 0
            else float("inf")
            if total_wins > 0
            else 0.0
        )

        # Payoff ratio
        analysis.payoff_ratio = (
            analysis.avg_win / abs(analysis.avg_loss) if analysis.avg_loss != 0 else 0.0
        )

        # Expected value
        analysis.expected_value = (
            analysis.win_rate * analysis.avg_win + (1 - analysis.win_rate) * analysis.avg_loss
        )

        # Total PnL
        analysis.total_pnl = float(sum(t.pnl for t in trades))
        analysis.total_pnl_pct = float(sum(t.pnl_pct for t in trades))

        # Consecutive wins/losses
        max_wins = max_losses = current_wins = current_losses = 0
        for t in trades:
            if t.pnl > 0:
                current_wins += 1
                current_losses = 0
                max_wins = max(max_wins, current_wins)
            else:
                current_losses += 1
                current_wins = 0
                max_losses = max(max_losses, current_losses)
        analysis.max_consecutive_wins = max_wins
        analysis.max_consecutive_losses = max_losses

        # Holding period — use total_seconds for intraday accuracy.
        # delta.days returns 0 for same-day trades, understating duration.
        holding_days = []
        for t in trades:
            if t.entry_time and t.exit_time:
                delta = t.exit_time - t.entry_time
                holding_days.append(delta.total_seconds() / 86400.0)
        analysis.avg_holding_bars = float(np.mean(holding_days)) if holding_days else 0.0

        # Trades by strategy
        strategy_counts: dict[str, int] = {}
        for t in trades:
            strategy_counts[t.strategy] = strategy_counts.get(t.strategy, 0) + 1
        analysis.trades_by_strategy = strategy_counts

        return analysis

    @staticmethod
    def _compute_benchmark_metrics(
        equity_curve: list,
        benchmark: pd.DataFrame,
        config: BacktestConfig,
    ) -> dict[str, float]:
        """Compute alpha, beta, IR vs benchmark."""
        if not equity_curve or benchmark.empty:
            return {}

        # Build benchmark returns
        ts_col = (
            "timestamp"
            if "timestamp" in benchmark.columns
            else "date"
            if "date" in benchmark.columns
            else None
        )
        if ts_col is None or "close" not in benchmark.columns:
            return {}

        bench = benchmark.sort_values(ts_col)
        bench_returns = bench["close"].pct_change().dropna().values

        # Strategy returns from equity curve
        equities = np.array([eq for _, eq in equity_curve])
        strat_returns = np.diff(equities) / equities[:-1]
        strat_returns = strat_returns[np.isfinite(strat_returns)]

        # Align lengths
        min_len = min(len(strat_returns), len(bench_returns))
        if min_len < 2:
            return {}
        strat_returns = strat_returns[:min_len]
        bench_returns = bench_returns[:min_len]

        # Beta = Cov(strat, bench) / Var(bench)
        cov = np.cov(strat_returns, bench_returns)
        beta = cov[0, 1] / cov[1, 1] if cov[1, 1] > 0 else 0.0

        # Alpha = Strat_mean - risk_free - beta * (Bench_mean - risk_free)
        rf = config.risk_free_rate / config.annualization_factor
        alpha = float(np.mean(strat_returns) - rf - beta * (np.mean(bench_returns) - rf))

        # Information Ratio = (Strat_mean - Bench_mean) / Tracking Error
        tracking_diff = strat_returns - bench_returns
        tracking_error = float(np.std(tracking_diff) * np.sqrt(config.annualization_factor))
        ir = (
            float((np.mean(strat_returns) - np.mean(bench_returns)) / np.std(tracking_diff))
            if np.std(tracking_diff) > 0
            else 0.0
        )

        # Benchmark total return
        bench_total = float((bench_returns + 1).prod() - 1)

        return {
            "alpha": alpha,
            "beta": float(beta),
            "benchmark_return": bench_total,
            "tracking_error": tracking_error,
            "information_ratio": ir,
        }
