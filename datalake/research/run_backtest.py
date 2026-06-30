"""Backtest runner — Wire DataLake into pipeline for real backtesting.

Usage:
    python -m datalake.run_backtest [--symbol RELIANCE] [--years 5] [--timeframe 1D]
    python -m datalake.run_backtest --scan --top 10 --years 2
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging

import pandas as pd

from analytics.backtest import BacktestConfig, BacktestEngine
from analytics.pipeline.features import (
    ATR,
    ROC,
    RSI,
    SMA,
    Momentum,
    RelativeVolume,
    Trend,
)
from analytics.pipeline.pipeline import FeaturePipeline
from analytics.scanner.scanners import MomentumScanner
from analytics.strategy import BreakoutStrategy, MomentumStrategy, StrategyPipeline
from datalake.gateway import DataLakeGateway

# Initialize logging if not already configured
if not logging.getLogger().handlers:

    logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


def build_pipeline() -> FeaturePipeline:
    """Build the feature pipeline for scanning and backtesting."""
    return (
        FeaturePipeline()
        .add(RSI(period=14))
        .add(ROC(period=5))
        .add(Momentum(period=5))
        .add(Trend(fast_period=10, slow_period=50))
        .add(RelativeVolume(period=20))
        .add(SMA(period=20))
        .add(ATR(period=14))
    )


def load_multi_symbol_data(
    gw: DataLakeGateway, symbols: list[str], lookback_days: int = 252
) -> pd.DataFrame:
    """Load data for multiple symbols into a single DataFrame."""
    frames = []
    for symbol in symbols:
        try:
            df = gw.history(symbol, timeframe="1m", lookback_days=lookback_days)
            if not df.empty:
                frames.append(df)
        except Exception as e:
            logger.warning("Failed to load %s: %s", symbol, e)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def run_single_backtest(symbol: str, years: int = 5):
    """Run backtest on a single symbol using 1m data."""
    print(f"\n{'=' * 60}")
    print(f"BACKTEST: {symbol} | {years}Y | 1m")
    print(f"{'=' * 60}")

    gw = DataLakeGateway(root="market_data")
    data = gw.history(symbol, timeframe="1m", lookback_days=years * 365)
    if data.empty:
        print(f"No data for {symbol}")
        return None

    print(f"Data: {len(data)} bars from {data['timestamp'].min()} to {data['timestamp'].max()}")

    pipeline = build_pipeline()
    strategy = StrategyPipeline(strategies=[MomentumStrategy(), BreakoutStrategy()])
    config = BacktestConfig(
        initial_capital=1_000_000,
        slippage_pct=0.1,
        commission_flat=20,
        max_position_pct=0.1,
        warmup_bars=100,
        risk_free_rate=0.065,
    )

    engine = BacktestEngine(pipeline=pipeline, strategy_pipeline=strategy, config=config)
    result = engine.run(data, symbol=symbol)

    ta = result.metrics.trade_analysis
    print("\nResults:")
    print(f"  Total Return: {result.metrics.total_return_pct:.2f}%")
    print(f"  Sharpe Ratio: {result.metrics.sharpe_ratio:.3f}")
    print(f"  Max Drawdown: {result.metrics.max_drawdown_pct:.2f}%")
    print(f"  Win Rate: {ta.win_rate * 100:.1f}%")
    print(f"  Trades: {ta.total_trades}")
    print(f"  Profit Factor: {ta.profit_factor:.2f}")

    return result


def run_scan_and_backtest(top_n: int = 10, years: int = 2):
    """Scan universe, pick top N, backtest each using 1m data."""
    print(f"\n{'=' * 60}")
    print(f"SCAN + BACKTEST: Top {top_n} | {years}Y | 1m")
    print(f"{'=' * 60}")

    gw = DataLakeGateway(root="market_data")
    all_symbols = gw.list_symbols(timeframe="1m")
    print(f"Universe: {len(all_symbols)} symbols")

    # Load recent data for scanning (last 252 days)
    print("\nLoading data for scanning...")
    universe_df = load_multi_symbol_data(gw, all_symbols[:100], lookback_days=252)
    if universe_df.empty:
        print("No data loaded")
        return []

    print(f"Loaded {len(universe_df)} rows for {universe_df['symbol'].nunique()} symbols")

    # Run scanner
    pipeline = build_pipeline()
    scanner = MomentumScanner(pipeline=pipeline, top_n=top_n)

    print("Running scanner...")
    scan_result = scanner.scan(universe_df)
    print(f"Scan complete: {len(scan_result.candidates)} candidates")

    for c in scan_result.candidates[:10]:
        print(f"  {c.symbol}: score={c.score:.1f}")

    # Backtest each candidate
    strategy = StrategyPipeline(strategies=[MomentumStrategy()])
    config = BacktestConfig(
        initial_capital=1_000_000,
        slippage_pct=0.1,
        commission_flat=20,
        max_position_pct=0.1,
        warmup_bars=100,
    )

    results = []
    print(f"\nBacktesting top {min(top_n, len(scan_result.candidates))} candidates...")
    for candidate in scan_result.candidates[:top_n]:
        try:
            data = gw.history(candidate.symbol, timeframe="1m", lookback_days=years * 365)
            if data.empty or len(data) < 200:
                print(f"  {candidate.symbol}: Insufficient data ({len(data)} rows)")
                continue
            engine = BacktestEngine(pipeline=pipeline, strategy_pipeline=strategy, config=config)
            result = engine.run(data, symbol=candidate.symbol)
            ta = result.metrics.trade_analysis
            results.append((candidate.symbol, result))
            print(
                f"  {candidate.symbol}: return={result.metrics.total_return_pct:.2f}% sharpe={result.metrics.sharpe_ratio:.3f} trades={ta.total_trades}"
            )
        except Exception as e:
            print(f"  {candidate.symbol}: ERROR - {e}")

    # Summary
    if results:
        returns = [r.metrics.total_return_pct for _, r in results]
        sharpes = [r.metrics.sharpe_ratio for _, r in results]
        trade_counts = [r.metrics.trade_analysis.total_trades for _, r in results]
        print("\nPortfolio Summary:")
        print(f"  Symbols backtested: {len(results)}")
        print(f"  Avg Return: {sum(returns) / len(returns):.2f}%")
        print(f"  Avg Sharpe: {sum(sharpes) / len(sharpes):.3f}")
        print(f"  Total Trades: {sum(trade_counts)}")
        print(f"  Best: {max(returns):.2f}%")
        print(f"  Worst: {min(returns):.2f}%")

        # Sort by return
        results.sort(key=lambda x: x[1].metrics.total_return_pct, reverse=True)
        print("\nTop 5:")
        for sym, r in results[:5]:
            ta = r.metrics.trade_analysis
            print(
                f"  {sym}: {r.metrics.total_return_pct:.2f}% | Sharpe {r.metrics.sharpe_ratio:.3f} | {ta.total_trades} trades | Win {ta.win_rate * 100:.0f}%"
            )

    return results


def main():
    parser = argparse.ArgumentParser(description="Data Lake Backtester")
    parser.add_argument("--symbol", default=None, help="Single symbol to backtest")
    parser.add_argument("--scan", action="store_true", help="Scan universe and backtest top N")
    parser.add_argument("--top", type=int, default=10, help="Top N from scan")
    parser.add_argument("--years", type=int, default=5, help="Years of history")
    args = parser.parse_args()

    if args.scan:
        run_scan_and_backtest(top_n=args.top, years=args.years)
    elif args.symbol:
        run_single_backtest(args.symbol, years=args.years)
    else:
        run_scan_and_backtest(top_n=10, years=2)


if __name__ == "__main__":
    main()
