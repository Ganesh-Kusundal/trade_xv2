"""HalfTrend backtest across NIFTY500 universe.

Usage:
    python -m analytics.indicators.halftrend_backtest [--top 50] [--years 1]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from datalake.gateway import DataLakeGateway
from analytics.indicators.halftrend import HalfTrend
from analytics.pipeline.pipeline import FeaturePipeline
from analytics.pipeline.features import RSI, ATR
from analytics.strategy import StrategyPipeline, Signal, SignalType
from analytics.strategy.models import StrategyResult
from analytics.scanner.models import Candidate
from analytics.backtest.models import BacktestConfig, BacktestResult, PerformanceMetrics, TradeAnalysis


# ---------------------------------------------------------------------------
# HalfTrend Strategy (wraps indicator for StrategyPipeline)
# ---------------------------------------------------------------------------

class HalfTrendStrategy:
    """Strategy that uses HalfTrend signals."""

    name = "HalfTrend"

    def __init__(self, period: int = 10, atr_period: int = 10, deviation: float = 1.0):
        self._ht = HalfTrend(period=period, atr_period=atr_period, deviation=deviation)

    def evaluate(self, candidate: Candidate, features: pd.DataFrame) -> Signal:
        if features.empty:
            return Signal(symbol=candidate.symbol, signal_type=SignalType.HOLD, confidence=0.0, strategy=self.name, reasons=["No data"])

        # Compute HalfTrend on the feature DataFrame
        df = self._ht.compute(features)
        last = df.iloc[-1]

        signal_str = last.get("halftrend_signal", "HOLD")
        direction = last.get("halftrend_direction", 0)
        close = float(last.get("close", 0))
        ht_val = float(last.get("halftrend", close))

        if signal_str == "BUY":
            return Signal(
                symbol=candidate.symbol,
                signal_type=SignalType.BUY,
                confidence=0.7,
                entry_price=close,
                stop_loss=close * 0.97,
                target=close * 1.06,
                strategy=self.name,
                reasons=["HalfTrend BUY signal", f"direction={direction}"],
                metadata={"halftrend": ht_val},
            )
        elif signal_str == "SELL":
            return Signal(
                symbol=candidate.symbol,
                signal_type=SignalType.SELL,
                confidence=0.7,
                entry_price=close,
                stop_loss=close * 1.03,
                target=close * 0.94,
                strategy=self.name,
                reasons=["HalfTrend SELL signal", f"direction={direction}"],
                metadata={"halftrend": ht_val},
            )

        return Signal(
            symbol=candidate.symbol,
            signal_type=SignalType.HOLD,
            confidence=0.0,
            strategy=self.name,
            reasons=[f"HalfTrend HOLD direction={direction}"],
        )


# ---------------------------------------------------------------------------
# Fast Backtest Engine (pre-computes features)
# ---------------------------------------------------------------------------

@dataclass
class Trade:
    symbol: str
    side: str
    entry_price: float
    exit_price: float
    entry_time: object
    exit_time: object
    quantity: int
    pnl: float
    pnl_pct: float
    strategy: str = ""


def fast_backtest(data: pd.DataFrame, strategy, config: BacktestConfig, symbol: str = "SYMBOL", cooldown: int = 50) -> dict:
    """Optimized backtest that pre-computes features once."""
    if data.empty or len(data) < config.warmup_bars + 10:
        return {"trades": 0, "return": 0, "win_rate": 0, "sharpe": 0, "max_dd": 0}

    # Pre-compute HalfTrend once on full dataset
    ht = HalfTrend(period=10, atr_period=10, deviation=1.0, cooldown=cooldown)
    features = ht.compute(data)

    capital = config.initial_capital
    position = None
    trades = []
    equity_curve = [capital]

    for idx in range(config.warmup_bars, len(features)):
        row = features.iloc[idx]
        signal_str = row.get("halftrend_signal", "HOLD")
        price = float(row["close"])
        ts = row["timestamp"]

        if signal_str == "BUY" and position is None:
            qty = int((capital * config.max_position_pct) / price) if price > 0 else 0
            if qty > 0:
                position = {"entry": price, "qty": qty, "time": ts}
                capital -= config.commission_flat

        elif signal_str == "SELL" and position is not None:
            exit_p = price - price * (config.slippage_pct / 100)
            pnl = (exit_p - position["entry"]) * position["qty"]
            trades.append(Trade(
                symbol=symbol, side="LONG",
                entry_price=position["entry"], exit_price=exit_p,
                entry_time=position["time"], exit_time=ts,
                quantity=position["qty"], pnl=pnl - config.commission_flat,
                pnl_pct=(exit_p / position["entry"] - 1) * 100,
            ))
            capital += pnl - config.commission_flat
            position = None

        if position:
            unrealized = (price - position["entry"]) * position["qty"]
            equity = capital + position["entry"] * position["qty"] + unrealized
        else:
            equity = capital
        equity_curve.append(equity)

    # Close open position
    if position:
        last_price = float(features.iloc[-1]["close"])
        pnl = (last_price - position["entry"]) * position["qty"]
        trades.append(Trade(
            symbol=symbol, side="LONG",
            entry_price=position["entry"], exit_price=last_price,
            entry_time=position["time"], exit_time=features.iloc[-1]["timestamp"],
            quantity=position["qty"], pnl=pnl - config.commission_flat,
            pnl_pct=(last_price / position["entry"] - 1) * 100,
        ))

    # Metrics
    winning = [t for t in trades if t.pnl > 0]
    total_pnl = sum(t.pnl for t in trades)
    returns = pd.Series(equity_curve).pct_change().dropna()
    # For 1m bars: ~390 bars/day * 252 days/year
    bars_per_year = 390 * 252
    volatility = float(returns.std() * np.sqrt(bars_per_year)) if len(returns) > 1 else 0
    mean_ret = float(returns.mean() * bars_per_year) if len(returns) > 1 else 0

    peak = equity_curve[0]
    max_dd = 0
    for eq in equity_curve:
        if eq > peak: peak = eq
        dd = (peak - eq) / peak if peak > 0 else 0
        if dd > max_dd: max_dd = dd

    return {
        "trades": len(trades),
        "win_rate": len(winning) / len(trades) * 100 if trades else 0,
        "return": (equity_curve[-1] - equity_curve[0]) / equity_curve[0] * 100,
        "pnl": total_pnl,
        "sharpe": (mean_ret - 0.065) / volatility if volatility > 0 else 0,
        "max_dd": max_dd * 100,
        "profit_factor": abs(sum(t.pnl for t in winning) / sum(t.pnl for t in trades if t.pnl <= 0)) if trades and any(t.pnl <= 0 for t in trades) else 0,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_halftrend_backtest(top_n: int = 50, years: int = 1):
    """Run HalfTrend backtest across top N stocks by volume."""
    print(f"\n{'='*60}")
    print(f"HALFTREND BACKTEST: Top {top_n} by volume | {years}Y | 1m")
    print(f"{'='*60}")

    gw = DataLakeGateway(root="market_data")
    all_symbols = gw.list_symbols()
    print(f"Universe: {len(all_symbols)} symbols")

    # Sample symbols
    sample = all_symbols[:min(top_n * 2, len(all_symbols))]

    # Load data and compute average volume for ranking
    print("Loading data for ranking...")
    volume_data = {}
    for sym in sample:
        try:
            df = gw.history(sym, timeframe="1m", lookback_days=30)
            if not df.empty and len(df) > 100:
                avg_vol = df["volume"].mean()
                volume_data[sym] = avg_vol
        except:
            pass

    # Sort by volume, take top N
    ranked = sorted(volume_data.items(), key=lambda x: x[1], reverse=True)[:top_n]
    symbols = [s for s, _ in ranked]
    print(f"Selected {len(symbols)} symbols by volume")

    # Run HalfTrend backtest on each
    config = BacktestConfig(
        initial_capital=1_000_000,
        slippage_pct=0.1,
        commission_flat=20,
        max_position_pct=0.05,
        warmup_bars=100,
    )

    results = []
    print(f"\nRunning HalfTrend backtest on {len(symbols)} symbols...")
    for i, sym in enumerate(symbols, 1):
        try:
            data = gw.history(sym, timeframe="1m", lookback_days=years * 365)
            if data.empty or len(data) < 500:
                continue

            strategy = HalfTrendStrategy(period=10, atr_period=10, deviation=1.0)
            result = fast_backtest(data, strategy, config, symbol=sym)
            result["symbol"] = sym
            results.append(result)

            if i % 20 == 0:
                print(f"  [{i}/{len(symbols)}] processed...")
        except Exception as e:
            pass

    # Summary
    if not results:
        print("No results")
        return

    returns = [r["return"] for r in results]
    trades = [r["trades"] for r in results]
    win_rates = [r["win_rate"] for r in results if r["trades"] > 0]

    print(f"\n{'='*60}")
    print(f"HALFTREND RESULTS: {len(results)} symbols")
    print(f"{'='*60}")
    print(f"  Avg Return: {np.mean(returns):+.2f}%")
    print(f"  Median Return: {np.median(returns):+.2f}%")
    print(f"  Avg Trades: {np.mean(trades):.0f}")
    print(f"  Avg Win Rate: {np.mean(win_rates):.1f}%")
    print(f"  Positive: {sum(1 for r in returns if r > 0)}/{len(returns)}")
    print(f"  Best: {max(returns):+.2f}%")
    print(f"  Worst: {min(returns):+.2f}%")

    # Top 10
    results.sort(key=lambda x: x["return"], reverse=True)
    print(f"\nTop 10:")
    for r in results[:10]:
        print(f"  {r['symbol']}: {r['return']:+.2f}% | {r['trades']} trades | Win {r['win_rate']:.0f}% | Sharpe {r['sharpe']:.3f}")

    print(f"\nBottom 5:")
    for r in results[-5:]:
        print(f"  {r['symbol']}: {r['return']:+.2f}% | {r['trades']} trades | Win {r['win_rate']:.0f}%")


def main():
    parser = argparse.ArgumentParser(description="HalfTrend Backtester")
    parser.add_argument("--top", type=int, default=50, help="Top N stocks by volume")
    parser.add_argument("--years", type=int, default=1, help="Years of history")
    args = parser.parse_args()
    run_halftrend_backtest(top_n=args.top, years=args.years)


if __name__ == "__main__":
    main()
