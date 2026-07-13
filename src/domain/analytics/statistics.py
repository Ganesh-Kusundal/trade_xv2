"""Standalone, pure statistics engine for trading performance metrics.

This module is the single source of truth for the performance math that was
previously inlined in ``analytics.backtest.engine`` (and is reused by
``analytics.replay.engine`` and exposed via the analytics facade).

Design rules (Tier 2-E):
    * Domain-pure — imports only stdlib, numpy, pandas (and, optionally,
      duck-typed domain objects). No dependency on ``application``,
      ``infrastructure`` or ``analytics``.
    * No I/O.
    * Pure functions over trade / equity sequences so the math is testable
      in isolation and reusable without a full simulation.

The numeric formulas are intentionally identical to the original inline
implementations so that backtest / replay results do not change.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    import pandas as pd


@dataclass
class TradeStatistics:
    """Computed trade-level statistics — pure and analytics-agnostic.

    The analytics layer copies these values into its own ``TradeAnalysis``
    dataclass (which may carry extra presentation fields).
    """

    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0

    avg_win: float = 0.0
    avg_loss: float = 0.0
    avg_win_pct: float = 0.0
    avg_loss_pct: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    avg_holding_bars: float = 0.0

    profit_factor: float = 0.0
    expected_value: float = 0.0
    payoff_ratio: float = 0.0

    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0

    total_pnl: float = 0.0
    total_pnl_pct: float = 0.0

    trades_by_strategy: dict[str, int] = field(default_factory=dict)
    avg_entry_confidence: float = 0.0


class StatisticsEngine:
    """Pure performance-statistics engine.

    Every method is static and operates on plain sequences (lists / numpy
    arrays / duck-typed trade objects with ``.pnl``, ``.pnl_pct``,
    ``.entry_time``, ``.exit_time`` and ``.strategy`` attributes) so the math
    can be unit tested on its own.
    """

    # -- returns derived from an equity curve -----------------------------
    @staticmethod
    def equity_returns(equity_curve: Sequence[tuple[Any, float]]) -> np.ndarray:
        """Period-over-period simple returns from an ``(ts, equity)`` curve."""
        equities = np.array([float(eq) for _, eq in equity_curve], dtype=np.float64)
        returns = np.diff(equities) / equities[:-1]
        return returns[np.isfinite(returns)]

    @staticmethod
    def total_return(initial: float, final: float) -> tuple[float, float]:
        """Return ``(absolute, fractional_pct)`` total return."""
        total = final - initial
        pct = (final / initial - 1) if initial > 0 else 0.0
        return float(total), float(pct)

    @staticmethod
    def cagr(initial: float, final: float, n_periods: int, annualization_factor: int) -> float:
        """Compound annual growth rate over ``n_periods`` bars."""
        if n_periods < 2 or initial <= 0:
            return 0.0
        years = n_periods / annualization_factor
        if years <= 0:
            return 0.0
        return float((final / initial) ** (1 / years) - 1)

    # -- risk metrics ------------------------------------------------------
    @staticmethod
    def volatility(returns: np.ndarray, annualization_factor: int) -> float:
        """Annualized standard deviation of returns."""
        if len(returns) == 0:
            return 0.0
        return float(np.std(returns) * np.sqrt(annualization_factor))

    @staticmethod
    def sharpe(returns: np.ndarray, annualization_factor: int, risk_free_rate: float) -> float:
        """Annualized Sharpe ratio using per-bar risk-free rate."""
        if len(returns) == 0:
            return 0.0
        rf_per_bar = risk_free_rate / annualization_factor
        excess = returns - rf_per_bar
        if np.std(excess) > 0:
            return float(np.mean(excess) / np.std(excess) * np.sqrt(annualization_factor))
        return 0.0

    @staticmethod
    def sortino(returns: np.ndarray, annualization_factor: int, risk_free_rate: float) -> float:
        """Annualized Sortino ratio (downside deviation only)."""
        if len(returns) == 0:
            return 0.0
        rf_per_bar = risk_free_rate / annualization_factor
        excess = returns - rf_per_bar
        downside = returns[returns < 0]
        if len(downside) > 0 and np.std(downside) > 0:
            return float(np.mean(excess) / np.std(downside) * np.sqrt(annualization_factor))
        return 0.0

    @staticmethod
    def max_drawdown(equities: Sequence[float]) -> tuple[float, int]:
        """Return ``(max_drawdown_fraction, duration_in_bars)``."""
        arr = np.array([float(e) for e in equities], dtype=np.float64)
        if len(arr) < 2:
            return 0.0, 0
        peak = np.maximum.accumulate(arr)
        drawdown = (peak - arr) / peak
        drawdown = drawdown[np.isfinite(drawdown)]
        dd = float(np.max(drawdown)) if len(drawdown) > 0 else 0.0
        peak_idx = int(np.argmax(arr))
        trough_idx = (
            int(np.argmin(arr[peak_idx:]) + peak_idx)
            if peak_idx < len(arr)
            else len(arr) - 1
        )
        return dd, int(trough_idx - peak_idx)

    @staticmethod
    def calmar(cagr: float, max_drawdown: float) -> float:
        """Calmar ratio = CAGR / max drawdown."""
        return float(cagr / max_drawdown) if max_drawdown > 0 else 0.0

    # -- trade analysis ----------------------------------------------------
    @staticmethod
    def analyze_trades(trades: Iterable[Any]) -> TradeStatistics:
        """Analyze a sequence of completed trades.

        ``trades`` may be any iterable whose items expose
        ``.pnl`` (numeric, e.g. ``Decimal`` or ``float``), ``.pnl_pct``,
        ``.entry_time``, ``.exit_time`` and ``.strategy``.
        """
        trades = list(trades)
        stats = TradeStatistics(total_trades=len(trades))
        if not trades:
            return stats

        wins = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl <= 0]
        stats.winning_trades = len(wins)
        stats.losing_trades = len(losses)
        stats.win_rate = len(wins) / len(trades) if trades else 0.0

        if wins:
            stats.avg_win = float(np.mean([float(t.pnl) for t in wins]))
            stats.avg_win_pct = float(np.mean([t.pnl_pct for t in wins]))
            stats.largest_win = float(max(float(t.pnl) for t in wins))
        if losses:
            stats.avg_loss = float(np.mean([float(t.pnl) for t in losses]))
            stats.avg_loss_pct = float(np.mean([t.pnl_pct for t in losses]))
            stats.largest_loss = float(min(float(t.pnl) for t in losses))

        total_wins = sum((t.pnl for t in wins), 0)
        total_losses = abs(sum((t.pnl for t in losses), 0))
        if total_losses != 0:
            stats.profit_factor = total_wins / total_losses
        elif total_wins != 0:
            stats.profit_factor = float("inf")
        else:
            stats.profit_factor = 0.0

        stats.payoff_ratio = (
            stats.avg_win / abs(stats.avg_loss) if stats.avg_loss != 0 else 0.0
        )
        stats.expected_value = (
            stats.win_rate * stats.avg_win + (1 - stats.win_rate) * stats.avg_loss
        )
        stats.total_pnl = float(sum(float(t.pnl) for t in trades))
        stats.total_pnl_pct = float(sum(t.pnl_pct for t in trades))

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
        stats.max_consecutive_wins = max_wins
        stats.max_consecutive_losses = max_losses

        holding_days: list[float] = []
        for t in trades:
            if t.entry_time and t.exit_time:
                delta = t.exit_time - t.entry_time
                holding_days.append(delta.total_seconds() / 86400.0)
        stats.avg_holding_bars = float(np.mean(holding_days)) if holding_days else 0.0

        strategy_counts: dict[str, int] = {}
        for t in trades:
            strategy_counts[t.strategy] = strategy_counts.get(t.strategy, 0) + 1
        stats.trades_by_strategy = strategy_counts
        return stats

    # -- benchmark comparison ---------------------------------------------
    @staticmethod
    def benchmark_metrics(
        equity_curve: Sequence[tuple[Any, float]],
        benchmark: pd.DataFrame,
        *,
        risk_free_rate: float,
        annualization_factor: int,
    ) -> dict[str, float]:
        """Compute alpha, beta, information ratio, tracking error, benchmark return."""
        if not equity_curve or benchmark is None or benchmark.empty:
            return {}
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

        equities = np.array([float(eq) for _, eq in equity_curve])
        strat_returns = np.diff(equities) / equities[:-1]
        strat_returns = strat_returns[np.isfinite(strat_returns)]

        min_len = min(len(strat_returns), len(bench_returns))
        if min_len < 2:
            return {}
        strat_returns = strat_returns[:min_len]
        bench_returns = bench_returns[:min_len]

        cov = np.cov(strat_returns, bench_returns)
        beta = cov[0, 1] / cov[1, 1] if cov[1, 1] > 0 else 0.0

        rf = risk_free_rate / annualization_factor
        alpha = float(np.mean(strat_returns) - rf - beta * (np.mean(bench_returns) - rf))

        tracking_diff = strat_returns - bench_returns
        tracking_error = float(np.std(tracking_diff) * np.sqrt(annualization_factor))
        ir = (
            float((np.mean(strat_returns) - np.mean(bench_returns)) / np.std(tracking_diff))
            if np.std(tracking_diff) > 0
            else 0.0
        )
        bench_total = float((bench_returns + 1).prod() - 1)

        return {
            "alpha": alpha,
            "beta": float(beta),
            "benchmark_return": bench_total,
            "tracking_error": tracking_error,
            "information_ratio": ir,
        }

    # -- combined performance metrics -------------------------------------
    @staticmethod
    def compute(
        equity_curve: Sequence[tuple[Any, float]],
        trades: Iterable[Any],
        *,
        initial: float,
        final: float,
        annualization_factor: int = 252,
        risk_free_rate: float = 0.065,
        benchmark: pd.DataFrame | None = None,
    ) -> dict[str, Any]:
        """Compute the full set of performance metrics.

        ``initial`` / ``final`` are passed explicitly because the final equity
        (realized PnL after closing open positions) may differ from the last
        equity-curve sample.
        """
        metrics: dict[str, Any] = {
            "max_drawdown": 0.0,
            "max_drawdown_duration": 0,
        }

        metrics["total_return"], metrics["total_return_pct"] = StatisticsEngine.total_return(
            initial, final
        )
        metrics["cagr"] = StatisticsEngine.cagr(
            initial, final, len(equity_curve), annualization_factor
        )

        metrics["trade_analysis"] = StatisticsEngine.analyze_trades(trades)

        if len(equity_curve) >= 2:
            returns = StatisticsEngine.equity_returns(equity_curve)
            if len(returns) > 0:
                metrics["volatility"] = StatisticsEngine.volatility(returns, annualization_factor)
                metrics["sharpe_ratio"] = StatisticsEngine.sharpe(
                    returns, annualization_factor, risk_free_rate
                )
                metrics["sortino_ratio"] = StatisticsEngine.sortino(
                    returns, annualization_factor, risk_free_rate
                )
                dd, duration = StatisticsEngine.max_drawdown([eq for _, eq in equity_curve])
                metrics["max_drawdown"] = dd
                metrics["max_drawdown_duration"] = duration

        metrics["calmar_ratio"] = (
            StatisticsEngine.calmar(metrics["cagr"], metrics["max_drawdown"])
            if metrics["max_drawdown"] > 0
            else 0.0
        )

        if benchmark is not None and not benchmark.empty:
            metrics.update(
                StatisticsEngine.benchmark_metrics(
                    equity_curve,
                    benchmark,
                    risk_free_rate=risk_free_rate,
                    annualization_factor=annualization_factor,
                )
            )

        return metrics
