"""OrderFlow and Probability CLI commands."""

from __future__ import annotations

import pandas as pd
from rich.console import Console
from rich.table import Table

from analytics.orderflow import OrderFlowAnalytics
from analytics.probability import ProbabilityEngine
from analytics.reports.reports import print_result


def run_orderflow(args: list[str], console: Console) -> None:
    """Run order-flow analysis on trade data or option chain."""
    file_path = None
    chain_path = None
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--file" and index + 1 < len(args):
            file_path = args[index + 1]
            index += 2
        elif arg == "--chain" and index + 1 < len(args):
            chain_path = args[index + 1]
            index += 2
        else:
            index += 1

    if not file_path and not chain_path:
        console.print("[yellow]Usage: tradex analytics orderflow --file trades.csv[/yellow]")
        console.print("[dim]   or: tradex analytics orderflow --chain option_chain.csv[/dim]")
        return

    engine = OrderFlowAnalytics()

    if file_path:
        trades = pd.read_csv(file_path)
        console.print(f"[dim]Loaded {len(trades)} trades from {file_path}[/dim]")
        result = engine.analyze(trades=trades)
    else:
        chain = pd.read_csv(chain_path)
        console.print(f"[dim]Loaded option chain from {chain_path}[/dim]")
        result = engine.analyze(chain=chain)

    print_result(result, console)


def run_probability(args: list[str], console: Console) -> None:
    """Run probability scoring on provided metrics."""
    metrics = {}
    symbol = None
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--trend" and index + 1 < len(args):
            metrics["trend"] = float(args[index + 1])
            index += 2
        elif arg == "--momentum" and index + 1 < len(args):
            metrics["momentum"] = float(args[index + 1])
            index += 2
        elif arg == "--volume" and index + 1 < len(args):
            metrics["volume"] = float(args[index + 1])
            index += 2
        elif arg == "--oi" and index + 1 < len(args):
            metrics["oi"] = float(args[index + 1])
            index += 2
        elif arg == "--rs" and index + 1 < len(args):
            metrics["relative_strength"] = float(args[index + 1])
            index += 2
        elif arg == "--symbol" and index + 1 < len(args):
            symbol = args[index + 1].upper()
            index += 2
        else:
            index += 1

    if not metrics:
        console.print("[yellow]Usage: tradex analytics probability --trend 70 --momentum 60 --volume 80 [--oi 50] [--rs 65] [--symbol RELIANCE][/yellow]")
        console.print("[dim]All values 0-100. Defaults to 50 if not provided.[/dim]")
        return

    engine = ProbabilityEngine()
    result = engine.analyze(metrics, symbol=symbol)

    table = Table(title=f"Probability Score{f': {symbol}' if symbol else ''}", header_style="bold cyan")
    table.add_column("Component", style="bold white")
    table.add_column("Score", style="green")
    table.add_column("Weight", style="dim")

    weights = {"trend": "25%", "momentum": "25%", "volume": "15%", "oi": "15%", "relative_strength": "20%"}
    for key, weight in weights.items():
        val = result.scores.get(f"{key}_score", 50)
        table.add_row(key.replace("_", " ").title(), f"{val:.1f}", weight)

    table.add_row("─" * 20, "─" * 8, "─" * 8, style="dim")
    composite = result.scores.get("composite_score", 50)
    comp_style = "green" if composite >= 70 else "red" if composite <= 30 else "yellow"
    table.add_row("COMPOSITE", f"[{comp_style}]{composite:.1f}[/{comp_style}]", "100%")

    console.print(table)
    console.print(f"\n[bold]{result.summary}[/bold]")
    if result.recommendations:
        for rec in result.recommendations:
            console.print(f"[dim]{rec}[/dim]")
