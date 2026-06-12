"""CLI command handler for instrument searching."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from brokers.common.core.broker import Broker
from brokers.dhan.broker import DhanBroker


def run(args: list[str], broker: Broker, console: Console) -> None:
    """Entry point for search subcommand."""
    if not args:
        console.print("[yellow]Usage: tradex search <query_string>[/yellow]")
        return

    if not isinstance(broker, DhanBroker):
        console.print("[red]Search requires a live Dhan broker with a loaded catalog.[/red]")
        return

    query = args[0].upper().strip()
    service = broker.instrument_service

    table = Table(title=f"Instrument Search Results: '{query}'", header_style="bold yellow")
    table.add_column("Canonical Symbol", style="bold white")
    table.add_column("Asset Class", justify="center")
    table.add_column("Security ID / Token", justify="center")
    table.add_column("Exchange", justify="center")

    try:
        matches = service.search_symbols(query, limit=80)
    except Exception as exc:
        console.print(f"[red]Instrument search failed: {exc}[/red]")
        return

    if matches:

        def seg_label(seg):
            return seg.value.split("_")[0] if hasattr(seg, "value") else str(seg)

        for definition in matches:
            table.add_row(
                definition.canonical_symbol[:60],
                definition.instrument_type or definition.exchange_segment.value,
                definition.security_id,
                seg_label(definition.exchange_segment),
            )
        try:
            info = service.snapshot_info
            catalog_note = f"catalog ({info.record_count:,} records)"
        except Exception:
            catalog_note = "catalog"
        table.caption = (
            f"[dim]Results from {catalog_note} "
            f"({len(matches)} match{'es' if len(matches) != 1 else ''})[/dim]"
        )
        console.print(table)
    else:
        console.print(f"[yellow]No instruments matched '{query}'.[/yellow]")
