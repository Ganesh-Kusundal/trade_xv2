"""DataLake Backtest CLI commands."""

from __future__ import annotations

import pandas as pd
from rich.console import Console
from rich.table import Table

from datalake.gateway import DataLakeGateway
from datalake.fast_backtest import FastBacktestEngine
from analytics.pipeline.pipeline import FeaturePipeline
from analytics.pipeline.features import (
    EMA, RSI, MACD, ROC, ATR, Momentum, Trend, VolumeSMA,
    BollingerBands, RelativeVolume, SwingHighLow, SMA,
)
from analytics.strategy import StrategyPipeline, MomentumStrategy, BreakoutStrategy
from analytics.backtest import BacktestConfig


def run_datalake_backtest(args: list[str], console: Console) -> None:
    """Run backtest from datalake (single symbol or scan+backtest)."""
    symbol = None
    scan_mode = False
    top = 10
    years = 2
    strategy_name = "momentum"
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--symbol" and index + 1 < len(args):
            symbol = args[index + 1].upper()
            index += 2
        elif arg == "--scan":
            scan_mode = True
            index += 1
        elif arg == "--top" and index + 1 < len(args):
            top = int(args[index + 1])
            index += 2
        elif arg == "--years" and index + 1 < len(args):
            years = float(args[index + 1])
            index += 2
        elif arg == "--strategy" and index + 1 < len(args):
            strategy_name = args[index + 1].lower()
            index += 2
        elif not arg.startswith("--"):
            symbol = args[index].upper()
            index += 1
        else:
            index += 1

    if not symbol and not scan_mode:
        console.print("[yellow]Usage: tradex analytics datalake-backtest --symbol RELIANCE [--years 2][/yellow]")
        console.print("[dim]   or: tradex analytics datalake-backtest --scan --top 10 --years 2[/dim]")
        return

    gw = DataLakeGateway()
    lookback_days = int(years * 365)

    pipeline = (
        FeaturePipeline()
        .add(RSI(period=14))
        .add(ROC(period=5))
        .add(Momentum(period=5))
        .add(Trend(fast_period=10, slow_period=50))
        .add(RelativeVolume(period=20))
        .add(SMA(period=20))
        .add(ATR(period=14))
    )

    strategies = {
        "momentum": MomentumStrategy(),
        "breakout": BreakoutStrategy(),
    }
    strategy = StrategyPipeline(strategies=[strategies.get(strategy_name, MomentumStrategy())])
    config = BacktestConfig(initial_capital=100_000, warmup_bars=50)

    if scan_mode:
        symbols = gw.list_symbols()
        console.print(f"[dim]Scanning {len(symbols)} symbols, backtesting top {top}...[/dim]")

        scored = []
        for sym in symbols:
            try:
                df = gw.history(sym, timeframe="1m", lookback_days=lookback_days)
                if df.empty or len(df) < 100:
                    continue
                close = df["close"]
                ret_5d = (close.iloc[-1] / close.iloc[-120] - 1) * 100 if len(close) > 120 else 0
                scored.append((sym, ret_5d))
            except Exception:
                continue
        scored.sort(key=lambda x: x[1], reverse=True)

        bt_table = Table(title=f"DataLake Backtest — Top {top}", header_style="bold cyan")
        bt_table.add_column("#", style="dim", width=4)
        bt_table.add_column("Symbol", style="bold white")
        bt_table.add_column("Return", style="green")
        bt_table.add_column("Trades", style="cyan")
        bt_table.add_column("Win Rate", style="yellow")
        bt_table.add_column("Max DD", style="red")
        bt_table.add_column("Sharpe", style="magenta")

        for i, (sym, _) in enumerate(scored[:top], 1):
            try:
                df = gw.history(sym, timeframe="1m", lookback_days=lookback_days)
                if df.empty:
                    continue
                engine = FastBacktestEngine(pipeline, strategy, config)
                bt_result = engine.run(df, symbol=sym)
                m = bt_result.metrics
                ret_style = "green" if m.total_return_pct >= 0 else "red"
                bt_table.add_row(
                    str(i), sym,
                    f"[{ret_style}]{m.total_return_pct:+.2f}%[/{ret_style}]",
                    str(m.trade_analysis.total_trades),
                    f"{m.trade_analysis.win_rate*100:.0f}%",
                    f"{m.max_drawdown_pct:.1f}%",
                    f"{m.sharpe_ratio:.2f}",
                )
            except Exception as e:
                bt_table.add_row(str(i), sym, f"[red]Error[/red]", "-", "-", "-", "-")

        console.print(bt_table)
    else:
        df = gw.history(symbol, timeframe="1m", lookback_days=lookback_days)
        if df.empty:
            console.print(f"[red]No data for {symbol} in datalake.[/red]")
            return

        console.print(f"[dim]Running backtest: {symbol}, {len(df)} bars, {years}yr[/dim]")
        engine = FastBacktestEngine(pipeline, strategy, config)
        bt_result = engine.run(df, symbol=symbol)

        console.print("\n[bold cyan]=== DATALAKE BACKTEST RESULTS ===[/bold cyan]\n")
        m = bt_result.metrics

        table = Table(title=f"Backtest: {symbol}", header_style="bold cyan")
        table.add_column("Metric", style="bold white")
        table.add_column("Value", style="green")
        table.add_row("Total Return", f"{m.total_return_pct:+.2f}%")
        table.add_row("CAGR", f"{m.cagr:+.2f}%")
        table.add_row("Sharpe Ratio", f"{m.sharpe_ratio:.2f}")
        table.add_row("Max Drawdown", f"{m.max_drawdown_pct:.2f}%")
        table.add_row("Sortino Ratio", f"{m.sortino_ratio:.2f}")
        table.add_row("Calmar Ratio", f"{m.calmar_ratio:.2f}")
        table.add_row("Total Trades", str(m.trade_analysis.total_trades))
        table.add_row("Win Rate", f"{m.trade_analysis.win_rate*100:.1f}%")
        table.add_row("Profit Factor", f"{m.trade_analysis.profit_factor:.2f}")
        table.add_row("Avg Win", f"₹{m.trade_analysis.avg_win:.2f}")
        table.add_row("Avg Loss", f"₹{m.trade_analysis.avg_loss:.2f}")
        console.print(table)
