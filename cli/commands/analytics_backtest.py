"""Backtest and Paper Trading CLI commands."""

from __future__ import annotations

import pandas as pd
from rich.console import Console
from rich.table import Table

from analytics.backtest import BacktestConfig, BacktestEngine
from analytics.paper import PaperConfig, PaperTradingEngine
from analytics.pipeline import ATR, RSI, SMA, FeaturePipeline
from analytics.strategy import MomentumStrategy, StrategyPipeline


def run_backtest(args: list[str], console: Console) -> None:
    """Run backtest with rich performance analytics."""
    file_path = None
    benchmark_path = None
    capital = 100_000.0
    warmup = 20
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--file" and index + 1 < len(args):
            file_path = args[index + 1]
            index += 2
        elif arg == "--benchmark" and index + 1 < len(args):
            benchmark_path = args[index + 1]
            index += 2
        elif arg == "--capital" and index + 1 < len(args):
            capital = float(args[index + 1])
            index += 2
        elif arg == "--warmup" and index + 1 < len(args):
            warmup = int(args[index + 1])
            index += 2
        else:
            index += 1

    if not file_path:
        console.print("[yellow]Usage: tradex analytics backtest --file ohlcv.csv [--benchmark nifty.csv] [--capital 100000] [--warmup 20][/yellow]")
        return

    try:
        data = pd.read_csv(file_path)
        console.print(f"[dim]Loaded {len(data)} bars from {file_path}[/dim]")
    except Exception as exc:
        console.print(f"[red]Error loading file: {exc}[/red]")
        return

    benchmark = None
    if benchmark_path:
        try:
            benchmark = pd.read_csv(benchmark_path)
            console.print(f"[dim]Loaded benchmark: {len(benchmark)} bars from {benchmark_path}[/dim]")
        except Exception as exc:
            console.print(f"[yellow]Warning: Could not load benchmark: {exc}[/yellow]")

    pipeline = FeaturePipeline().add(RSI(14)).add(ATR(14)).add(SMA(20))
    config = BacktestConfig(initial_capital=capital, warmup_bars=warmup)

    engine = BacktestEngine(pipeline, config=config)
    result = engine.run(data, symbol="BACKTEST", benchmark=benchmark)

    console.print("\n[bold cyan]=== BACKTEST RESULTS ===[/bold cyan]\n")
    summary = result.summary

    table = Table(title="Performance Summary", header_style="bold cyan")
    table.add_column("Metric", style="bold white")
    table.add_column("Value", style="green")
    for key, val in summary.items():
        table.add_row(key.replace("_", " ").title(), str(val))
    console.print(table)

    ta = result.metrics.trade_analysis
    if ta.total_trades > 0:
        console.print(f"\n[bold]Trades:[/bold] {ta.total_trades} | Win: {ta.winning_trades} | Loss: {ta.losing_trades}")
        console.print(f"[bold]Win Rate:[/bold] {ta.win_rate*100:.1f}% | Profit Factor: {ta.profit_factor:.2f}")
        console.print(f"[bold]Avg Win:[/bold] ₹{ta.avg_win:.2f} ({ta.avg_win_pct:+.1f}%) | Avg Loss: ₹{ta.avg_loss:.2f} ({ta.avg_loss_pct:+.1f}%)")
        console.print(f"[bold]Max Consecutive:[/bold] {ta.max_consecutive_wins} wins / {ta.max_consecutive_losses} losses")
        if ta.trades_by_strategy:
            console.print(f"[bold]By Strategy:[/bold] {ta.trades_by_strategy}")
    else:
        console.print("\n[yellow]No trades executed.[/yellow]")


def run_paper(args: list[str], console: Console) -> None:
    """Run paper trading with the same pipeline as live."""
    file_path = None
    capital = 100_000.0
    warmup = 20
    max_positions = 5
    slippage = 0.01
    commission = 0.0003
    stop_loss = 2.0
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--file" and index + 1 < len(args):
            file_path = args[index + 1]
            index += 2
        elif arg == "--capital" and index + 1 < len(args):
            capital = float(args[index + 1])
            index += 2
        elif arg == "--warmup" and index + 1 < len(args):
            warmup = int(args[index + 1])
            index += 2
        elif arg == "--positions" and index + 1 < len(args):
            max_positions = int(args[index + 1])
            index += 2
        elif arg == "--slippage" and index + 1 < len(args):
            slippage = float(args[index + 1])
            index += 2
        elif arg == "--commission" and index + 1 < len(args):
            commission = float(args[index + 1])
            index += 2
        elif arg == "--stop-loss" and index + 1 < len(args):
            stop_loss = float(args[index + 1])
            index += 2
        else:
            index += 1

    if not file_path:
        console.print("[yellow]Usage: tradex analytics paper --file ohlcv.csv [--capital 100000] [--positions 5] [--warmup 20] [--slippage 0.01] [--commission 0.0003] [--stop-loss 2.0][/yellow]")
        return

    try:
        data = pd.read_csv(file_path)
        console.print(f"[dim]Loaded {len(data)} bars from {file_path}[/dim]")
    except Exception as exc:
        console.print(f"[red]Error loading file: {exc}[/red]")
        return

    required = {"close"}
    missing = required - set(data.columns)
    if missing:
        console.print(f"[red]Missing required columns: {missing}[/red]")
        return

    pipeline = FeaturePipeline().add(RSI(14)).add(ATR(14)).add(SMA(20))
    strategy = StrategyPipeline(strategies=[MomentumStrategy()])
    config = PaperConfig(
        initial_capital=capital,
        warmup_bars=warmup,
        max_positions=max_positions,
        slippage_pct=slippage,
        commission_pct=commission,
        stop_loss_pct=stop_loss,
    )

    console.print(f"[dim]Running paper trading: ₹{capital:,.0f} capital, {max_positions} max positions, {slippage}% slippage[/dim]")
    engine = PaperTradingEngine(pipeline, strategy, config)
    result = engine.run(data, symbol="PAPER")

    console.print("\n[bold cyan]=== PAPER TRADING RESULTS ===[/bold cyan]\n")
    summary = result.summary

    table = Table(title="Paper Trading Summary", header_style="bold cyan")
    table.add_column("Metric", style="bold white")
    table.add_column("Value", style="green")
    for key, val in summary.items():
        table.add_row(key.replace("_", " ").title(), str(val))
    console.print(table)

    if result.session.positions:
        console.print("\n[bold]Open Positions:[/bold]")
        pos_table = Table(header_style="bold cyan")
        pos_table.add_column("Symbol", style="bold white")
        pos_table.add_column("Side", style="cyan")
        pos_table.add_column("Qty", style="yellow")
        pos_table.add_column("Entry", style="green")
        pos_table.add_column("Current", style="green")
        pos_table.add_column("P&L", style="magenta")
        for p in result.session.open_positions:
            pnl_style = "green" if p.unrealized_pnl >= 0 else "red"
            pos_table.add_row(
                p.symbol, p.side.value, str(p.quantity),
                f"₹{p.entry_price:.2f}", f"₹{p.current_price:.2f}",
                f"[{pnl_style}]₹{p.unrealized_pnl:.2f}[/{pnl_style}]",
            )
        console.print(pos_table)

    if result.session.trades:
        wins = sum(1 for t in result.session.trades if t.pnl > 0)
        losses = sum(1 for t in result.session.trades if t.pnl <= 0)
        console.print(f"\n[bold]Trades:[/bold] {len(result.session.trades)} | Win: {wins} | Loss: {losses}")
        console.print(f"[bold]Win Rate:[/bold] {result.session.win_rate*100:.1f}%")
        console.print(f"[bold]Total P&L:[/bold] ₹{result.session.total_pnl:.2f}")
        console.print(f"[bold]Commission:[/bold] ₹{result.session.total_commission:.2f}")
    else:
        console.print("\n[yellow]No trades executed.[/yellow]")
