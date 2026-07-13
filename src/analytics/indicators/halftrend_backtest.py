"""HalfTrend backtest across NIFTY500 universe.

Usage:
    python -m analytics.indicators.halftrend_backtest [--top 50] [--years 1]
"""

from __future__ import annotations

import argparse
import logging
import sys
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd

from domain.ports.data_catalog import DEFAULT_DATA_ROOT

logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from analytics.backtest.models import (
    BacktestConfig,
)
from analytics.indicators.halftrend import HalfTrend
from analytics.scanner.models import Candidate
from analytics.strategy import Signal, SignalType
from domain.entities.trade import Trade
from domain.trading_costs import apply_slippage as _apply_slippage

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
            return Signal(
                symbol=candidate.symbol,
                signal_type=SignalType.HOLD,
                confidence=0.0,
                strategy=self.name,
                reasons=["No data"],
            )

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


def fast_backtest(
    data: pd.DataFrame, strategy, config: BacktestConfig, symbol: str = "SYMBOL", cooldown: int = 50
) -> dict:
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
                entry_p = float(
                    _apply_slippage(
                        Decimal(str(price)), side="BUY", slippage_pct=config.slippage_pct
                    )
                )
                position = {"entry": entry_p, "qty": qty, "time": ts}
                capital -= config.commission_flat

        elif signal_str == "SELL" and position is not None:
            exit_p = float(
                _apply_slippage(Decimal(str(price)), side="SELL", slippage_pct=config.slippage_pct)
            )
            pnl = (exit_p - position["entry"]) * position["qty"]
            trades.append(
                Trade(
                    symbol=symbol,
                    side="LONG",
                    entry_price=position["entry"],
                    exit_price=exit_p,
                    entry_time=position["time"],
                    exit_time=ts,
                    quantity=position["qty"],
                    pnl=pnl - config.commission_flat,
                    pnl_pct=(exit_p / position["entry"] - 1) * 100,
                )
            )
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
        trades.append(
            Trade(
                symbol=symbol,
                side="LONG",
                entry_price=position["entry"],
                exit_price=last_price,
                entry_time=position["time"],
                exit_time=features.iloc[-1]["timestamp"],
                quantity=position["qty"],
                pnl=pnl - config.commission_flat,
                pnl_pct=(last_price / position["entry"] - 1) * 100,
            )
        )

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
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd

    return {
        "trades": len(trades),
        "win_rate": len(winning) / len(trades) * 100 if trades else 0,
        "return": (equity_curve[-1] - equity_curve[0]) / equity_curve[0] * 100,
        "pnl": total_pnl,
        "sharpe": (mean_ret - 0.065) / volatility if volatility > 0 else 0,
        "max_dd": max_dd * 100,
        "profit_factor": abs(sum(t.pnl for t in winning) / sum(t.pnl for t in trades if t.pnl <= 0))
        if trades and any(t.pnl <= 0 for t in trades)
        else 0,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run_halftrend_backtest(top_n: int = 50, years: int = 1, gateway=None):
    """Run HalfTrend backtest across top N stocks by volume.

    Parameters
    ----------
    top_n : int
        Top N stocks by volume to backtest.
    years : int
        Years of history to use.
    gateway : DataLakeGateway, optional
        Data gateway instance. If None, creates a new one.
    """
    from datalake.adapters.analytics_provider import DataLakeMarketDataProvider

    gw = gateway or DataLakeMarketDataProvider(root=DEFAULT_DATA_ROOT)
    all_symbols = gw.list_symbols()
    logger.info("Universe: %d symbols", len(all_symbols))

    # Sample symbols
    sample = all_symbols[: min(top_n * 2, len(all_symbols))]

    # Load data and compute average volume for ranking
    logger.info("Loading data for ranking...")
    volume_data = {}
    for sym in sample:
        try:
            df = gw.history(sym, timeframe="1m", lookback_days=30)
            if not df.empty and len(df) > 100:
                avg_vol = df["volume"].mean()
                volume_data[sym] = avg_vol
        except Exception as exc:
            logger.debug("volume_fetch_failed: %s: %s", sym, exc)

    # Sort by volume, take top N
    ranked = sorted(volume_data.items(), key=lambda x: x[1], reverse=True)[:top_n]
    symbols = [s for s, _ in ranked]
    logger.info("Selected %d symbols by volume", len(symbols))

    # Run HalfTrend backtest on each
    config = BacktestConfig(
        initial_capital=1_000_000,
        slippage_pct=0.1,
        commission_flat=20,
        max_position_pct=0.05,
        warmup_bars=100,
    )

    results = []
    logger.info("Running HalfTrend backtest on %d symbols...", len(symbols))
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
                logger.info("  [%d/%d] processed...", i, len(symbols))
        except Exception as exc:
            logger.debug("backtest_failed: %s: %s", sym, exc)

    # Summary
    if not results:
        logger.info("No results")
        return

    returns = [r["return"] for r in results]
    trades = [r["trades"] for r in results]
    win_rates = [r["win_rate"] for r in results if r["trades"] > 0]

    logger.info("=" * 60)
    logger.info("HALFTREND RESULTS: %d symbols", len(results))
    logger.info("=" * 60)
    logger.info("  Avg Return: %+.2f%%", np.mean(returns))
    logger.info("  Median Return: %+.2f%%", np.median(returns))
    logger.info("  Avg Trades: %.0f", np.mean(trades))
    logger.info("  Avg Win Rate: %.1f%%", np.mean(win_rates))
    logger.info("  Positive: %d/%d", sum(1 for r in returns if r > 0), len(returns))
    logger.info("  Best: %+.2f%%", max(returns))
    logger.info("  Worst: %+.2f%%", min(returns))

    # Top 10
    results.sort(key=lambda x: x["return"], reverse=True)
    logger.info("Top 10:")
    for r in results[:10]:
        logger.info(
            "  %s: %+.2f%% | %d trades | Win %.0f%% | Sharpe %.3f",
            r['symbol'], r['return'], r['trades'], r['win_rate'], r['sharpe'],
        )

    logger.info("Bottom 5:")
    for r in results[-5:]:
        logger.info(
            "  %s: %+.2f%% | %d trades | Win %.0f%%",
            r['symbol'], r['return'], r['trades'], r['win_rate'],
        )


def main():
    parser = argparse.ArgumentParser(description="HalfTrend Backtester")
    parser.add_argument("--top", type=int, default=50, help="Top N stocks by volume")
    parser.add_argument("--years", type=int, default=1, help="Years of history")
    args = parser.parse_args()
    run_halftrend_backtest(top_n=args.top, years=args.years)


if __name__ == "__main__":
    main()
