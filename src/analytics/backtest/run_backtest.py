"""Backtest runner — wire DataLake into the analytics pipeline.

Usage:
    python -m analytics.backtest.run_backtest [--symbol RELIANCE] [--years 5]
    python -m analytics.backtest.run_backtest --scan --top 10 --years 2

Canonical home: analytics.backtest.run_backtest
(moved out of datalake so the storage layer does not depend on analytics).
"""

from __future__ import annotations

import argparse
import logging

import pandas as pd

from analytics.backtest import BacktestConfig
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


def run_single_backtest(symbol: str, years: int = 5, *, research_only: bool = False):
    """Run backtest on a single symbol using 1m data.

    Default uses OMS PARITY via ``build_paper_session``. Pass ``research_only=True``
    for fast PURE_SIM without OMS routing.
    """
    logger.info("=" * 60)
    logger.info(
        "BACKTEST: %s | %dY | 1m%s",
        symbol,
        years,
        " | RESEARCH" if research_only else " | PARITY",
    )
    logger.info("=" * 60)

    gw = DataLakeGateway()
    data = gw.history(symbol, timeframe="1m", lookback_days=years * 365)
    if data.empty:
        logger.warning("No data for %s", symbol)
        return None

    logger.info(
        "Data: %d bars from %s to %s",
        len(data),
        data["timestamp"].min(),
        data["timestamp"].max(),
    )

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

    from runtime.paper_session import build_backtest_engine

    engine = build_backtest_engine(
        pipeline,
        strategy,
        config,
        research_only=research_only,
    )
    result = engine.run(data, symbol=symbol)

    ta = result.metrics.trade_analysis
    logger.info("Results:")
    logger.info("  Total Return: %.2f%%", result.metrics.total_return_pct)
    logger.info("  Sharpe Ratio: %.3f", result.metrics.sharpe_ratio)
    logger.info("  Max Drawdown: %.2f%%", result.metrics.max_drawdown_pct)
    logger.info("  Win Rate: %.1f%%", ta.win_rate * 100)
    logger.info("  Trades: %d", ta.total_trades)
    logger.info("  Profit Factor: %.2f", ta.profit_factor)

    return result


def run_scan_and_backtest(top_n: int = 10, years: int = 2):
    """Scan universe, pick top N, backtest each using 1m data."""
    logger.info("=" * 60)
    logger.info("SCAN + BACKTEST: Top %d | %dY | 1m", top_n, years)
    logger.info("=" * 60)

    gw = DataLakeGateway()
    all_symbols = gw.list_symbols(timeframe="1m")
    logger.info("Universe: %d symbols", len(all_symbols))

    logger.info("Loading data for scanning...")
    universe_df = load_multi_symbol_data(gw, all_symbols[:100], lookback_days=252)
    if universe_df.empty:
        logger.warning("No data loaded")
        return []

    logger.info(
        "Loaded %d rows for %d symbols",
        len(universe_df),
        universe_df["symbol"].nunique(),
    )

    pipeline = build_pipeline()
    scanner = MomentumScanner(pipeline=pipeline, top_n=top_n)

    logger.info("Running scanner...")
    scan_result = scanner.scan(universe_df)
    logger.info("Scan complete: %d candidates", len(scan_result.candidates))

    for c in scan_result.candidates[:10]:
        logger.info("  %s: score=%.1f", c.symbol, c.score)

    strategy = StrategyPipeline(strategies=[MomentumStrategy()])
    config = BacktestConfig(
        initial_capital=1_000_000,
        slippage_pct=0.1,
        commission_flat=20,
        max_position_pct=0.1,
        warmup_bars=100,
    )

    results = []
    logger.info("Backtesting top %d candidates...", min(top_n, len(scan_result.candidates)))
    for candidate in scan_result.candidates[:top_n]:
        try:
            data = gw.history(candidate.symbol, timeframe="1m", lookback_days=years * 365)
            if data.empty or len(data) < 200:
                logger.warning("  %s: Insufficient data (%d rows)", candidate.symbol, len(data))
                continue
            from runtime.paper_session import build_backtest_engine

            engine = build_backtest_engine(pipeline, strategy, config)
            result = engine.run(data, symbol=candidate.symbol)
            ta = result.metrics.trade_analysis
            results.append((candidate.symbol, result))
            logger.info(
                "  %s: return=%.2f%% sharpe=%.3f trades=%d",
                candidate.symbol,
                result.metrics.total_return_pct,
                result.metrics.sharpe_ratio,
                ta.total_trades,
            )
        except Exception as e:
            logger.error("  %s: ERROR - %s", candidate.symbol, e)

    if results:
        returns = [r.metrics.total_return_pct for _, r in results]
        sharpes = [r.metrics.sharpe_ratio for _, r in results]
        trade_counts = [r.metrics.trade_analysis.total_trades for _, r in results]
        logger.info("Portfolio Summary:")
        logger.info("  Symbols backtested: %d", len(results))
        logger.info("  Avg Return: %.2f%%", sum(returns) / len(returns))
        logger.info("  Avg Sharpe: %.3f", sum(sharpes) / len(sharpes))
        logger.info("  Total Trades: %d", sum(trade_counts))
        logger.info("  Best: %.2f%%", max(returns))
        logger.info("  Worst: %.2f%%", min(returns))

        results.sort(key=lambda x: x[1].metrics.total_return_pct, reverse=True)
        logger.info("Top 5:")
        for sym, r in results[:5]:
            ta = r.metrics.trade_analysis
            logger.info(
                "  %s: %.2f%% | Sharpe %.3f | %d trades | Win %.0f%%",
                sym,
                r.metrics.total_return_pct,
                r.metrics.sharpe_ratio,
                ta.total_trades,
                ta.win_rate * 100,
            )

    return results


def main():
    parser = argparse.ArgumentParser(description="Data Lake Backtester")
    parser.add_argument("--symbol", default=None, help="Single symbol to backtest")
    parser.add_argument("--scan", action="store_true", help="Scan universe and backtest top N")
    parser.add_argument("--top", type=int, default=10, help="Top N from scan")
    parser.add_argument("--years", type=int, default=5, help="Years of history")
    parser.add_argument(
        "--research",
        action="store_true",
        help=(
            "Run PURE_SIM without OMS parity. Default routes fills through the paper OMS session."
        ),
    )
    args = parser.parse_args()

    if args.research and not args.symbol:
        parser.error("--research is only supported with --symbol (not --scan)")

    if args.scan:
        run_scan_and_backtest(top_n=args.top, years=args.years)
    elif args.symbol:
        run_single_backtest(args.symbol, years=args.years, research_only=args.research)
    else:
        run_scan_and_backtest(top_n=10, years=2)


if __name__ == "__main__":
    main()
