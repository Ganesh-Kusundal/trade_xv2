"""CLI command handler for instrument searching."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from domain.symbols import normalize_symbol


def run(args: list[str], broker_service, console: Console) -> None:
    """Entry point for search subcommand."""
    if not args:
        console.print("[yellow]Usage: tradex search <query_string>[/yellow]")
        return

    gw = broker_service.active_broker
    resolver = getattr(gw, "instruments", None)
    if resolver is None:
        console.print("[red]Search requires a live broker with loaded instruments.[/red]")
        return

    query = normalize_symbol(args[0])

    table = Table(title=f"Instrument Search: '{query}'", header_style="bold yellow")
    table.add_column("Symbol", style="bold white")
    table.add_column("Exchange", justify="center")
    table.add_column("Type", justify="center")

    matches = []
    for inst in resolver.all_instruments():
        if query in inst.symbol.upper() or (
            inst.canonical_symbol and query in inst.canonical_symbol.upper()
        ):
            matches.append(inst)
        if len(matches) >= 80:
            break

    if matches:
        for inst in matches:
            table.add_row(
                (inst.canonical_symbol or inst.symbol)[:60],
                inst.exchange.value,
                inst.instrument_type.value,
            )
        stats = resolver.stats()
        table.caption = (
            f"[dim]{len(matches)} matches from {stats.get('total', 0):,} instruments[/dim]"
        )
        console.print(table)
    else:
        console.print(f"[yellow]No instruments matched '{query}'.[/yellow]")
