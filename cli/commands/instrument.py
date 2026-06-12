"""CLI command handler for broker mapping diagnostics."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from brokers.common.core.broker import Broker
from brokers.common.core.instruments import InstrumentRegistry
from brokers.dhan.mapper.seed_security_ids import DHAN_SEED_SECURITY_IDS


def run(args: list[str], broker: Broker, console: Console) -> None:
    """Entry point for instrument mapping subcommand."""
    if not args:
        console.print("[yellow]Usage: tradex instrument <symbol>[/yellow]")
        return

    symbol = args[0].upper().strip()
    service = broker.instrument_service
    registry = InstrumentRegistry()

    table = Table(title=f"Multi-Broker Mapping Diagnostics: {symbol}", header_style="bold cyan")
    table.add_column("Broker Partner", style="bold white")
    table.add_column("Instrument Key / Identifier", justify="center")
    table.add_column("Status", justify="center")

    dhan_id = "N/A"
    dhan_seg = "N/A"
    dhan_status = "[red]Missing[/red]"

    for exchange_label in ("IDX", "NSE", "IDX_I", "NFO"):
        try:
            result = service.resolve_symbol(symbol, exchange_label)
            if result.is_single and result.definition is not None:
                defn = result.definition
                dhan_id = defn.security_id
                dhan_seg = defn.exchange_segment.value
                dhan_status = "[green]Active[/green]"
                break
        except Exception:
            continue

    catalog_loaded = service._indexes.catalog.is_loaded
    if catalog_loaded:
        fallback_status = "[green]Active[/green]"
    else:
        fallback_status = "[yellow]Seed-only[/yellow]"

    table.add_row("Dhan Security ID", dhan_id, dhan_status)
    table.add_row("Dhan Segment", dhan_seg, fallback_status)
    table.add_row("Zerodha Instrument Token", "N/A", "[yellow]Unmapped[/yellow]")
    table.add_row("Upstox Instrument Key", "N/A", "[yellow]Unmapped[/yellow]")

    # Always show the verified Dhan seed ID for any registered symbol.
    # The InstrumentRegistry is the canonical source of truth and is loaded
    # from the audited ``brokers.dhan.mapper.seed_security_ids`` file.
    if dhan_id == "N/A":
        seed_id = DHAN_SEED_SECURITY_IDS.get(
            (symbol, "IDX"),
            seeds.get((symbol, "IDX_I"), seeds.get((symbol, "NSE"), "N/A")),
        )
        if seed_id != "N/A":
            table.add_row(f"Seed table ({symbol})", seed_id, "[yellow]Fallback[/yellow]")
    else:
        # Symbol resolved from catalog — also print the verified seed for cross-check.
        seed_id = DHAN_SEED_SECURITY_IDS.get(
            (symbol, "IDX"),
            seeds.get((symbol, "IDX_I"), seeds.get((symbol, "NSE"), "N/A")),
        )
        if seed_id != "N/A" and seed_id != dhan_id:
            table.add_row(f"Seed table ({symbol})", seed_id, "[yellow]Drift![/yellow]")
        elif seed_id != "N/A":
            table.add_row(f"Seed table ({symbol})", seed_id, "[green]Verified[/green]")

    # Print a one-liner showing the audited ID straight from InstrumentRegistry
    # (the single source of truth), so users can be sure they're seeing the
    # pinned value.
    audit_id = "N/A"
    for exch in ("NSE", "BSE", "IDX", "IDX_I"):
        try:
            audit_id = registry.broker_identifier(symbol, exch)
            table.add_row(f"Audited registry ({exch})", audit_id, "[green]Source of truth[/green]")
            break
        except KeyError:
            continue
    if audit_id == "N/A":
        table.add_row("Audited registry", "N/A", "[red]Unregistered[/red]")

    console.print(table)
