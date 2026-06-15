"""Strategy optimization CLI command."""

from __future__ import annotations

import pandas as pd
from rich.console import Console
from rich.table import Table

from analytics.backtest.optimizer import (
    optimize_grid,
    optimize_rsi_period,
    optimize_sma_period,
    ParamGrid,
)


def run_optimize(args: list[str], console: Console) -> None:
    """Run strategy parameter optimization."""
    file_path = None
    symbol = "OPTIMIZE"
    strategy = "momentum"
    capital = 100_000.0
    rsi_range = None
    sma_range = None
    atr_range = None
    top_n = 10

    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--file" and index + 1 < len(args):
            file_path = args[index + 1]
            index += 2
        elif arg == "--symbol" and index + 1 < len(args):
            symbol = args[index + 1].upper()
            index += 2
        elif arg == "--strategy" and index + 1 < len(args):
            strategy = args[index + 1].lower()
            index += 2
        elif arg == "--capital" and index + 1 < len(args):
            capital = float(args[index + 1])
            index += 2
        elif arg == "--rsi" and index + 1 < len(args):
            rsi_range = [int(x) for x in args[index + 1].split(",")]
            index += 2
        elif arg == "--sma" and index + 1 < len(args):
            sma_range = [int(x) for x in args[index + 1].split(",")]
            index += 2
        elif arg == "--atr" and index + 1 < len(args):
            atr_range = [int(x) for x in args[index + 1].split(",")]
            index += 2
        elif arg == "--top" and index + 1 < len(args):
            top_n = int(args[index + 1])
            index += 2
        else:
            index += 1

    if not file_path:
        console.print("[yellow]Usage: tradex analytics optimize --file ohlcv.csv [--rsi 7,10,14,21] [--sma 10,20,30] [--top 10][/yellow]")
        console.print("[dim]Quick modes:[/dim]")
        console.print("[dim]  tradex analytics optimize --file ohlcv.csv --rsi-only[/dim]")
        console.print("[dim]  tradex analytics optimize --file ohlcv.csv --sma-only[/dim]")
        return

    try:
        data = pd.read_csv(file_path)
        console.print(f"[dim]Loaded {len(data)} bars from {file_path}[/dim]")
    except Exception as exc:
        console.print(f"[red]Error loading file: {exc}[/red]")
        return

    # Build parameter grids
    grids = []
    if rsi_range:
        grids.append(ParamGrid("rsi_period", rsi_range))
    if sma_range:
        grids.append(ParamGrid("sma_period", sma_range))
    if atr_range:
        grids.append(ParamGrid("atr_period", atr_range))

    if not grids:
        # Default: quick RSI optimization
        console.print("[dim]No parameter ranges specified, running RSI optimization...[/dim]")
        result = optimize_rsi_period(data, symbol=symbol, initial_capital=capital)
    else:
        console.print(f"[dim]Optimizing {len(grids)} parameters...[/dim]")
        result = optimize_grid(
            data=data,
            symbol=symbol,
            param_grids=grids,
            strategy_name=strategy,
            initial_capital=capital,
        )

    # Print results
    console.print("\n[bold cyan]=== OPTIMIZATION RESULTS ===[/bold cyan]\n")

    # Best parameters
    console.print(f"[bold]Best Parameters:[/bold] {result.best_params}")
    console.print(f"[bold]Best Return:[/bold] {result.best_return:+.2f}%")
    console.print(f"[bold]Best Sharpe:[/bold] {result.best_sharpe:.2f}")

    # Results table
    if result.results:
        sorted_results = sorted(result.results, key=lambda x: x.get("sharpe_ratio", 0), reverse=True)

        table = Table(title=f"Top {min(top_n, len(sorted_results))} Parameter Combinations", header_style="bold cyan")
        table.add_column("#", style="dim", width=4)
        table.add_column("Parameters", style="bold white")
        table.add_column("Return", style="green")
        table.add_column("Sharpe", style="cyan")
        table.add_column("Max DD", style="red")
        table.add_column("Trades", style="yellow")
        table.add_column("Win Rate", style="magenta")

        for i, row in enumerate(sorted_results[:top_n], 1):
            ret_style = "green" if row["total_return_pct"] >= 0 else "red"
            table.add_row(
                str(i),
                str(row["params"]),
                f"[{ret_style}]{row['total_return_pct']:+.2f}%[/{ret_style}]",
                f"{row['sharpe_ratio']:.2f}",
                f"{row['max_drawdown_pct']:.1f}%",
                str(row["total_trades"]),
                f"{row['win_rate']*100:.0f}%",
            )

        console.print(table)
        console.print(f"[dim]{len(result.results)} combinations tested[/dim]")
