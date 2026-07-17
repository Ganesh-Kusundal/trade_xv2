"""Multi-strategy CLI commands."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from runtime.factory import build_multi_strategy_runtime


def run_strategies(args: list[str], console: Console) -> None:
    """List or run registered strategies."""
    if not args or args[0] == "list":
        runtime = build_multi_strategy_runtime()
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
            console.print(
                "[yellow]Usage: tradex analytics strategies run <name> [name...][/yellow]"
            )
            return
        runtime = build_multi_strategy_runtime(names)
        console.print(
            f"[green]Pipeline ready with {len(runtime.strategies)} strategies[/green]"
        )
        return

    console.print("[yellow]Usage: tradex analytics strategies list | run <name>...[/yellow]")
