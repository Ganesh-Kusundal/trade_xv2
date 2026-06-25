"""CLI command handler for ``tradex instruments ...`` subcommand."""

from __future__ import annotations

import logging

from rich.console import Console
from rich.table import Table

logger = logging.getLogger(__name__)


def run(args: list[str], broker_service, console: Console) -> None:
    """Route instruments subcommands."""
    if not args:
        console.print("[yellow]Usage: tradex instruments <lookup|stats|refresh> [args][/yellow]")
        return

    sub = args[0].lower()
    rest = args[1:]

    if sub == "lookup" and rest:
        _lookup(rest[0], broker_service, console)
    elif sub == "stats":
        _stats(broker_service, console)
    elif sub == "refresh":
        _refresh(broker_service, console)
    else:
        console.print(f"[yellow]Unknown instruments subcommand: {sub}[/yellow]")


def _lookup(symbol: str, broker_service, console: Console) -> None:
    gw = broker_service.active_broker
    resolver = getattr(gw, "instruments", None)
    if resolver is None:
        console.print("[red]No instrument resolver available.[/red]")
        return

    table = Table(title=f"Instrument Lookup: {symbol}", header_style="bold cyan")
    table.add_column("Field", style="bold white")
    table.add_column("Value", style="white")

    # Try each exchange
    for exch in ["NSE", "BSE", "NFO", "BFO", "MCX", "INDEX", "CDS"]:
        inst = resolver.get_by_symbol(symbol, exch)
        if inst:
            table.add_row(
                f"Match ({exch})",
                f"{inst.symbol} | sid={inst.security_id} | type={inst.instrument_type.value}",
            )
            if inst.expiry:
                table.add_row("  Expiry", inst.expiry)
            if inst.strike_price:
                table.add_row("  Strike", str(inst.strike_price))
            if inst.option_type:
                table.add_row("  Option Type", inst.option_type.value)
            if inst.underlying:
                table.add_row("  Underlying", inst.underlying)
            table.add_row("  Lot Size", str(inst.lot_size))

    if not table.rows:
        table.add_row("Result", "[red]Not found in any exchange[/red]")

    stats = resolver.stats()
    table.caption = f"[dim]Cache: {stats.get('total', 0):,} instruments[/dim]"
    console.print(table)


def _stats(broker_service, console: Console) -> None:
    gw = broker_service.active_broker
    resolver = getattr(gw, "instruments", None)
    if resolver is None:
        console.print("[red]No resolver available.[/red]")
        return
    stats = resolver.stats()
    table = Table(title="Instrument Cache Stats", header_style="bold cyan")
    table.add_column("Key", style="bold white")
    table.add_column("Value", style="white")
    for k, v in stats.items():
        table.add_row(str(k), str(v))
    console.print(table)


def _refresh(broker_service, console: Console) -> None:
    gw = broker_service.active_broker
    try:
        gw.load_instruments(use_cache=False)
        stats = gw.instruments.stats()
        console.print(f"[green]Instruments refreshed: {stats}[/green]")
    except Exception as exc:
        console.print(f"[red]Refresh failed: {exc}[/red]")
