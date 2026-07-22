"""Optimized backtest — pre-compute features once, then run strategy.

The standard ReplayEngine runs FeaturePipeline on every bar (O(n²)).
This module pre-computes all features once, then runs the strategy in O(n).

Ownership: ``FastBacktestEngine`` is the opt-in performance variant for signal
pre-filtering and quick scans. ``BacktestEngine`` (``analytics.backtest.engine``)
is the authoritative path for equity curves and fill semantics through the shared
OMS spine. Use FastBacktest when you need speed on large universes; use
BacktestEngine when results must match replay/live parity tests.

Canonical home: analytics.backtest.fast_backtest
(moved out of datalake so the storage layer does not depend on analytics).
"""

from __future__ import annotations

import logging
from decimal import Decimal

import numpy as np
import pandas as pd

from analytics.backtest.models import (
    BacktestConfig,
    BacktestResult,
    CapitalMetricsLabel,
    PerformanceMetrics,
    TradeAnalysis,
)
from analytics.pipeline.pipeline import FeaturePipeline
from analytics.scanner.models import Candidate
from analytics.strategy.models import Signal, SignalType
from analytics.strategy.pipeline import StrategyPipeline
from domain.constants import DEFAULT_EXCHANGE
from domain.entities.trade import Trade
from domain.enums import Side
from application.services.trading_costs_service import apply_slippage as _apply_slippage

logger = logging.getLogger(__name__)


class FastBacktestEngine:
    """Optimized signal pre-filter — NOT authoritative for PnL.

    Pre-computes features once for fast signal scanning. For equity curves and
    fills, use :class:`analytics.replay.engine.ReplayEngine` (single PnL spine).
    """

    def __init__(
        self,
        pipeline: FeaturePipeline,
        strategy_pipeline: StrategyPipeline | None = None,
        config: BacktestConfig | None = None,
        *,
        production: bool = False,
    ) -> None:
        self._pipeline = pipeline
        self._strategy = strategy_pipeline or StrategyPipeline()
        self._config = config or BacktestConfig()
        self._production = production
        self._warned_lookahead: bool = False

    def run(self, data: pd.DataFrame, *, symbol: str = "SYMBOL") -> BacktestResult:
        """Run optimized backtest on OHLCV DataFrame."""
        if self._production:
            raise RuntimeError(
                "FastBacktestEngine has documented look-ahead bias "
                "(features at bar N may use data from bar N+1). "
                "Use the standard BacktestEngine for production backtesting."
            )
        if not self._warned_lookahead:
            self._warned_lookahead = True
            logger.warning(
                "FastBacktestEngine uses pre-computed features on the full "
                "dataset — features at bar N may use data from bar N+1. "
                "For production backtesting, use the standard BacktestEngine."
            )
        if data.empty or len(data) < self._config.warmup_bars + 10:
            return BacktestResult()

        # Pre-compute features once
        try:
            features = self._pipeline.run(data)
        except Exception as exc:
            logger.error("FeaturePipeline failed: %s", exc)
            return BacktestResult()

        # Run strategy bar-by-bar on pre-computed features
        trades, equity_curve, signals = self._run_strategy(features, symbol)

        # Compute metrics
        metrics = self._compute_metrics(trades, equity_curve, features)

        # Build result
        from analytics.replay.models import ReplayResult, ReplaySession

        session = ReplaySession(capital=self._config.initial_capital)
        session.equity_curve = equity_curve
        session.signals = signals

        replay = ReplayResult(
            session=session,
            config=self._config,
            bars_processed=len(features),
            signals_generated=len(signals),
        )

        return BacktestResult(
            replay=replay,
            metrics=metrics,
            equity_curve=equity_curve,
            capital_metrics_label=CapitalMetricsLabel.RESEARCH,
            metadata={
                "engine": "FastBacktestEngine",
                "research_trade_count": len(trades),
                "capital_metrics_valid": False,
                "capital_metrics_label": CapitalMetricsLabel.RESEARCH.value,
                "bias_warning": (
                    "This backtest uses pre-computed features on the full dataset. "
                    "Features at bar N may use data from bar N+1 (look-ahead in feature computation). "
                    "For research scanning this is acceptable. "
                    "For production backtesting, use BacktestEngine with ResearchMode.PARITY."
                ),
            },
        )

    def _run_strategy(
        self, features: pd.DataFrame, symbol: str
    ) -> tuple[list[Trade], list[tuple], list[Signal]]:
        """Run strategy on pre-computed features."""
        config = self._config
        capital = config.initial_capital
        position = None  # None = flat, dict = in position
        trades = []
        signals = []
        equity_curve = [(features["timestamp"].iloc[0], capital)]

        warmup = config.warmup_bars
        ts_col = "timestamp"

        for idx in range(warmup, len(features)):
            row = features.iloc[idx]
            bar_df = features.iloc[: idx + 1]  # View up to current bar (no copy)

            candidate = Candidate(symbol=symbol, score=50.0, reasons=["fast_backtest"])

            try:
                bar_signals = self._strategy.evaluate_single(candidate, bar_df)
            except Exception:
                bar_signals = []

            for signal in bar_signals:
                signals.append(signal)
                price = float(row["close"])
                ts = row[ts_col]

                if (
                    signal.signal_type in (SignalType.BUY, SignalType.STRONG_BUY)
                    and position is None
                ):
                    qty = int((capital * config.max_position_pct) / price) if price > 0 else 0
                    if qty > 0:
                        entry_price = float(
                            _apply_slippage(
                                Decimal(str(price)), side=Side.BUY, slippage_pct=config.slippage_pct
                            )
                        )
                        commission = config.commission_flat
                        position = {
                            "side": "LONG",
                            "entry_price": entry_price,
                            "quantity": qty,
                            "entry_time": ts,
                            "strategy": signal.strategy,
                            "reasons": signal.reasons.copy(),
                            "cost": commission,
                        }
                        capital -= commission

                elif (
                    signal.signal_type in (SignalType.SELL, SignalType.STRONG_SELL)
                    and position is not None
                ):
                    price = float(row["close"])
                    exit_price = float(
                        _apply_slippage(
                            Decimal(str(price)), side=Side.SELL, slippage_pct=config.slippage_pct
                        )
                    )
                    commission = config.commission_flat

                    pnl = (exit_price - position["entry_price"]) * position["quantity"]
                    (exit_price / position["entry_price"] - 1) * 100

                    trade = Trade(
                        trade_id=f"backtest:{symbol}:{len(trades)}",
                        order_id="",
                        symbol=symbol,
                        exchange=DEFAULT_EXCHANGE,
                        side=Side.BUY if position["side"] == "LONG" else Side.SELL,
                        quantity=position["quantity"],
                        price=Decimal(str(position["entry_price"])),
                        trade_value=Decimal(str(pnl - commission - position["cost"])),
                    )
                    trades.append(trade)
                    capital += pnl - commission
                    position = None

            # Update equity (cash + mark-to-market position value)
            if position is not None:
                equity = capital + position["quantity"] * float(row["close"])
            else:
                equity = capital

            equity_curve.append((ts, equity))

        # Close open position at end
        if position is not None and len(features) > 0:
            last = features.iloc[-1]
            exit_price = float(last["close"])
            pnl = (exit_price - position["entry_price"]) * position["quantity"]
            trade = Trade(
                trade_id=f"backtest:{symbol}:{len(trades)}",
                order_id="",
                symbol=symbol,
                exchange=DEFAULT_EXCHANGE,
                side=Side.BUY if position["side"] == "LONG" else Side.SELL,
                quantity=position["quantity"],
                price=Decimal(str(position["entry_price"])),
                trade_value=Decimal(str(pnl - config.commission_flat - position["cost"])),
            )
            trades.append(trade)

        return trades, equity_curve, signals

    def _compute_metrics(
        self, trades: list[Trade], equity_curve: list[tuple], features: pd.DataFrame
    ) -> PerformanceMetrics:
        """Compute performance metrics from trades and equity curve."""
        if not trades:
            return PerformanceMetrics()

        # Trade analysis
        winning = [t for t in trades if t.trade_value > 0]
        losing = [t for t in trades if t.trade_value <= 0]
        total_pnl = sum(t.trade_value for t in trades)

        win_rate = len(winning) / len(trades) if trades else 0
        avg_win = np.mean([t.trade_value for t in winning]) if winning else 0
        avg_loss = np.mean([t.trade_value for t in losing]) if losing else 0
        profit_factor = (
            abs(sum(t.trade_value for t in winning) / sum(t.trade_value for t in losing))
            if losing and sum(t.trade_value for t in losing) != 0
            else 0
        )

        trade_analysis = TradeAnalysis(
            total_trades=len(trades),
            winning_trades=len(winning),
            losing_trades=len(losing),
            win_rate=win_rate,
            avg_win=float(avg_win),
            avg_loss=float(avg_loss),
            profit_factor=float(profit_factor),
            total_pnl=float(total_pnl),
        )

        # Return metrics
        equities = [e for _, e in equity_curve]
        if len(equities) >= 2:
            total_return = (equities[-1] - equities[0]) / equities[0]
            total_return_pct = total_return * 100
        else:
            total_return = 0
            total_return_pct = 0

        # Drawdown
        peak = equities[0]
        max_dd = 0
        for eq in equities:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd

        # Volatility and Sharpe
        returns = pd.Series(equities).pct_change().dropna()
        volatility = float(returns.std() * np.sqrt(252)) if len(returns) > 1 else 0
        mean_return = float(returns.mean() * 252) if len(returns) > 1 else 0
        sharpe = (mean_return - 0.065) / volatility if volatility > 0 else 0

        return PerformanceMetrics(
            total_return=float(total_return),
            total_return_pct=float(total_return_pct),
            max_drawdown=float(max_dd),
            max_drawdown_pct=float(max_dd * 100),
            volatility=float(volatility),
            sharpe_ratio=float(sharpe),
            trade_analysis=trade_analysis,
        )
