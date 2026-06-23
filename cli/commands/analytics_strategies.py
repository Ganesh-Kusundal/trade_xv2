"""Multi-strategy CLI commands."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from brokers.common.strategy.multi_strategy_runtime import MultiStrategyRuntime


def run_strategies(args: list[str], console: Console) -> None:
    """List or run registered strategies."""
    if not args or args[0] == "list":
        runtime = MultiStrategyRuntime()
        names = runtime.list_strategies()
        table = Table(title="Registered Strategies")
        table.add_column("Name")
        for name in names:
            table.add_row(name)
        console.print(table)
        return

    if args[0] == "run":
        names = [a for a in args[1:] if not a.startswith("-")]
        if not names:
            console.print("[yellow]Usage: tradex analytics strategies run <name> [name...][/yellow]")
            return
        pipeline = MultiStrategyRuntime.create_pipeline(names)
        console.print(f"[green]Pipeline ready with {len(pipeline.strategies)} strategies[/green]")
        return

    console.print("[yellow]Usage: tradex analytics strategies list | run <name>...[/yellow]")
