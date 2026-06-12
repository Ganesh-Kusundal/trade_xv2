"""Backtesting module -- historical strategy evaluation.

Provides a simple vectorised backtesting engine that iterates over
historical bars, applies a strategy, and produces performance metrics.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List

from strategy import Signal, Strategy

# -- Backtest Result ---------------------------------------------------------


@dataclass
class BacktestResult:
    """Summary metrics produced by a backtest run."""

    trades: int = 0
    final_pnl: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0


# -- Backtest Engine ---------------------------------------------------------


class BacktestEngine:
    """Event-driven backtester that feeds bars to a :class:`Strategy`.

    Parameters
    ----------
    strategy:
        The strategy instance whose ``on_bar`` method will be called
        for every bar in the dataset.
    initial_capital:
        Starting capital for the simulated account (default 100,000).
    """

    def __init__(self, strategy: Strategy, initial_capital: float = 100_000.0) -> None:
        self._strategy = strategy
        self._initial_capital = initial_capital

    def run(self, data: list[dict[str, Any]]) -> BacktestResult:
        """Execute the backtest over *data* and return results.

        Each item in *data* should be a dict containing at least
        ``"close"`` (the bar close price).
        """
        capital = self._initial_capital
        position = 0  # current shares held (positive = long)
        entry_price = 0.0
        trades: list[float] = []  # per-trade P&L list
        peak = capital

        for bar in data:
            close = float(bar.get("close", 0))
            signal = self._strategy.on_bar(bar)

            if signal == Signal.BUY and position == 0:
                # Open long: buy as many shares as capital allows
                if close > 0:
                    position = int(capital // close)
                    entry_price = close

            elif signal == Signal.SELL and position > 0:
                # Close long
                pnl = (close - entry_price) * position
                capital += pnl
                trades.append(pnl)
                position = 0
                entry_price = 0.0

            # Mark-to-market for drawdown tracking
            equity = capital + (position * close if position > 0 else 0)
            if equity > peak:
                peak = equity

        # Force-close any remaining position at last bar close
        if position > 0 and data:
            last_close = float(data[-1].get("close", 0))
            pnl = (last_close - entry_price) * position
            capital += pnl
            trades.append(pnl)
            position = 0

        final_pnl = capital - self._initial_capital

        # Max drawdown
        max_dd = 0.0
        equity = self._initial_capital
        running_peak = self._initial_capital
        for trade_pnl in trades:
            equity += trade_pnl
            if equity > running_peak:
                running_peak = equity
            dd = (running_peak - equity) / running_peak if running_peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd

        # Win rate
        wins = sum(1 for t in trades if t > 0)
        win_rate = wins / len(trades) if trades else 0.0

        return BacktestResult(
            trades=len(trades),
            final_pnl=final_pnl,
            max_drawdown=max_dd,
            win_rate=win_rate,
        )
