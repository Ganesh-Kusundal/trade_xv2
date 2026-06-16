"""Backtest comparison CLI command."""

from __future__ import annotations

import pandas as pd
from rich.console import Console
from rich.table import Table

from analytics.backtest.comparator import compare_parameters, compare_strategies


def run_compare(args: list[str], console: Console) -> None:
    """Compare multiple backtest strategies or parameter sets."""
    file_path = None
    symbol = "COMPARE"
    strategies = None
    rsi_values = None
    sma_values = None
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
        elif arg == "--strategies" and index + 1 < len(args):
            strategies = args[index + 1].split(",")
            index += 2
        elif arg == "--rsi" and index + 1 < len(args):
            rsi_values = [int(x) for x in args[index + 1].split(",")]
            index += 2
        elif arg == "--sma" and index + 1 < len(args):
            sma_values = [int(x) for x in args[index + 1].split(",")]
            index += 2
        elif arg == "--capital" and index + 1 < len(args):
            capital = float(args[index + 1])
            index += 2
        else:
            index += 1

    if not file_path:
        console.print("[yellow]Usage: tradex analytics compare --file ohlcv.csv[/yellow]")
        console.print("[dim]Compare strategies: tradex analytics compare --file ohlcv.csv --strategies momentum,breakout[/dim]")
        console.print("[dim]Compare parameters: tradex analytics compare --file ohlcv.csv --rsi 7,14,21 --sma 10,20,30[/dim]")
        return

    try:
        data = pd.read_csv(file_path)
        console.print(f"[dim]Loaded {len(data)} bars from {file_path}[/dim]")
    except Exception as exc:
        console.print(f"[red]Error loading file: {exc}[/red]")
        return

    if rsi_values or sma_values:
        # Compare parameters
        param_sets = []
        if rsi_values and sma_values:
            for rsi in rsi_values:
                for sma in sma_values:
                    param_sets.append({"rsi_period": rsi, "sma_period": sma})
        elif rsi_values:
            for rsi in rsi_values:
                param_sets.append({"rsi_period": rsi})
        elif sma_values:
            for sma in sma_values:
                param_sets.append({"sma_period": sma})

        console.print(f"[dim]Comparing {len(param_sets)} parameter sets...[/dim]")
        result = compare_parameters(data, symbol=symbol, param_sets=param_sets, initial_capital=capital)
        _print_param_comparison(console, result)
    else:
        # Compare strategies
        if strategies is None:
            strategies = ["momentum", "breakout"]

        console.print(f"[dim]Comparing {len(strategies)} strategies: {', '.join(strategies)}[/dim]")
        result = compare_strategies(data, symbol=symbol, strategies=strategies, initial_capital=capital)
        _print_strategy_comparison(console, result)


def _print_strategy_comparison(console: Console, result) -> None:
    """Print strategy comparison table."""
    if not result.results:
        console.print("[yellow]No results to compare.[/yellow]")
        return

    table = Table(title="Strategy Comparison", header_style="bold cyan")
    table.add_column("Strategy", style="bold white")
    table.add_column("Return", style="green")
    table.add_column("CAGR", style="cyan")
    table.add_column("Sharpe", style="magenta")
    table.add_column("Sortino", style="yellow")
    table.add_column("Max DD", style="red")
    table.add_column("Trades", style="dim")
    table.add_column("Win Rate", style="green")
    table.add_column("PF", style="cyan")

    for row in result.results:
        ret_style = "green" if row["total_return_pct"] >= 0 else "red"
        table.add_row(
            row["strategy"],
            f"[{ret_style}]{row['total_return_pct']:+.2f}%[/{ret_style}]",
            f"{row['cagr']*100:+.2f}%",
            f"{row['sharpe_ratio']:.2f}",
            f"{row['sortino_ratio']:.2f}",
            f"{row['max_drawdown_pct']:.1f}%",
            str(row["total_trades"]),
            f"{row['win_rate']*100:.0f}%",
            f"{row['profit_factor']:.2f}",
        )

    console.print(table)

    if result.best:
        console.print(f"\n[bold]Best Strategy:[/bold] {result.best['strategy']} (Sharpe: {result.best['sharpe_ratio']:.2f})")


def _print_param_comparison(console: Console, result) -> None:
    """Print parameter comparison table."""
    if not result.results:
        console.print("[yellow]No results to compare.[/yellow]")
        return

    table = Table(title="Parameter Comparison", header_style="bold cyan")
    table.add_column("Parameters", style="bold white")
    table.add_column("Return", style="green")
    table.add_column("CAGR", style="cyan")
    table.add_column("Sharpe", style="magenta")
    table.add_column("Max DD", style="red")
    table.add_column("Trades", style="dim")
    table.add_column("Win Rate", style="green")
    table.add_column("PF", style="cyan")

    for row in result.results:
        ret_style = "green" if row["total_return_pct"] >= 0 else "red"
        table.add_row(
            str(row["params"]),
            f"[{ret_style}]{row['total_return_pct']:+.2f}%[/{ret_style}]",
            f"{row['cagr']*100:+.2f}%",
            f"{row['sharpe_ratio']:.2f}",
            f"{row['max_drawdown_pct']:.1f}%",
            str(row["total_trades"]),
            f"{row['win_rate']*100:.0f}%",
            f"{row['profit_factor']:.2f}",
        )

    console.print(table)

    if result.best:
        console.print(f"\n[bold]Best Parameters:[/bold] {result.best['params']} (Sharpe: {result.best['sharpe_ratio']:.2f})")
