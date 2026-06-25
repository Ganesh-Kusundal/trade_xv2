"""Walk-forward analysis CLI command."""

from __future__ import annotations

import pandas as pd
from rich.console import Console
from rich.table import Table

from analytics.pipeline import ATR, RSI, SMA, FeaturePipeline
from analytics.strategy import MomentumStrategy, StrategyPipeline
from analytics.walk_forward.engine import WalkForwardConfig, WalkForwardEngine


def run_walkforward(args: list[str], console: Console) -> None:
    """Run walk-forward analysis on OHLCV data."""
    file_path = None
    symbol = "TEST"
    train_bars = 500
    test_bars = 100
    step_bars = 100
    capital = 100_000.0
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--file" and index + 1 < len(args):
            file_path = args[index + 1]
            index += 2
        elif arg == "--symbol" and index + 1 < len(args):
            symbol = args[index + 1].upper()
            index += 2
        elif arg == "--train-bars" and index + 1 < len(args):
            train_bars = int(args[index + 1])
            index += 2
        elif arg == "--test-bars" and index + 1 < len(args):
            test_bars = int(args[index + 1])
            index += 2
        elif arg == "--step-bars" and index + 1 < len(args):
            step_bars = int(args[index + 1])
            index += 2
        elif arg == "--capital" and index + 1 < len(args):
            capital = float(args[index + 1])
            index += 2
        else:
            index += 1

    if file_path:
        try:
            df = pd.read_csv(file_path)
        except Exception as exc:
            console.print(f"[red]Error loading file: {exc}[/red]")
            return
    else:
        console.print("[dim]No --file provided; generating synthetic OHLCV for demo[/dim]")
        ts = pd.date_range(
            "2026-01-02 09:15", periods=train_bars + test_bars + step_bars, freq="1min"
        )
        price = 100 + pd.Series(range(len(ts))).astype(float) * 0.05
        df = pd.DataFrame(
            {
                "timestamp": ts,
                "open": price,
                "high": price + 0.5,
                "low": price - 0.5,
                "close": price,
                "volume": 10000,
            }
        )

    pipeline = FeaturePipeline().add(RSI(14)).add(ATR(14)).add(SMA(20))
    strategy = StrategyPipeline(strategies=[MomentumStrategy()])
    engine = WalkForwardEngine(
        pipeline,
        strategy,
        WalkForwardConfig(
            train_bars=train_bars,
            test_bars=test_bars,
            step_bars=step_bars,
            initial_capital=capital,
        ),
    )
    result = engine.run(df, symbol=symbol)

    table = Table(title=f"Walk-Forward: {symbol}")
    table.add_column("Window")
    table.add_column("PnL", justify="right")
    table.add_column("Sharpe", justify="right")
    for w in result.windows:
        table.add_row(str(w["window"]), f"{w['pnl']:.2f}", f"{w['sharpe']:.3f}")
    console.print(table)
    console.print(
        f"[green]Windows: {result.window_count} | Total PnL: {result.total_pnl:.2f} | "
        f"Avg Sharpe: {result.avg_sharpe:.3f}[/green]"
    )
