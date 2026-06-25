"""CLI command handler for instrument resolution diagnostics."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from cli.services.broker_service import BrokerService


def run(args: list[str], broker_service: BrokerService, console: Console) -> None:
    """Entry point for instrument mapping subcommand."""
    if not args:
        console.print("[yellow]Usage: tradex instrument <symbol>[/yellow]")
        return

    symbol = args[0].upper().strip()
    gw = broker_service.active_broker

    resolver = gw.instruments
    resolver_stats = resolver.stats()

    table = Table(
        title=f"Instrument Resolution Diagnostics: {symbol}",
        header_style="bold cyan",
    )
    table.add_column("Lookup Method", style="bold white")
    table.add_column("Result", justify="center")
    table.add_column("Status", justify="center")

    # 1. SymbolResolver catalog status
    loaded = resolver_stats.get("loaded", False)
    total = resolver_stats.get("total", 0)
    if loaded:
        table.add_row(
            "Instrument Catalog",
            f"{total:,} instruments loaded",
            "[green]Active[/green]",
        )
    else:
        table.add_row(
            "Instrument Catalog",
            "Not loaded",
            "[red]Not Loaded[/red]",
        )

    # 2. Try resolving by symbol across common exchanges
    resolved = False
    for exchange_label in ("NSE", "INDEX", "NFO", "BSE", "BFO", "MCX", "CDS"):
        inst = resolver.get_by_symbol(symbol, exchange_label)
        if inst is not None:
            table.add_row(
                f"Symbol ({exchange_label})",
                f"Security ID: {inst.security_id} | Type: {inst.instrument_type.value}",
                "[green]Resolved[/green]",
            )
            resolved = True
            # Show additional details if available
            if inst.expiry:
                table.add_row(
                    "  Expiry",
                    inst.expiry,
                    "[dim]info[/dim]",
                )
            if inst.strike_price is not None:
                table.add_row(
                    "  Strike",
                    str(inst.strike_price),
                    "[dim]info[/dim]",
                )
            if inst.option_type:
                table.add_row(
                    "  Option Type",
                    inst.option_type.value,
                    "[dim]info[/dim]",
                )
            if inst.underlying:
                table.add_row(
                    "  Underlying",
                    inst.underlying,
                    "[dim]info[/dim]",
                )
            if inst.lot_size and inst.lot_size > 1:
                table.add_row(
                    "  Lot Size",
                    str(inst.lot_size),
                    "[dim]info[/dim]",
                )
            if inst.canonical_symbol:
                table.add_row(
                    "  Canonical",
                    inst.canonical_symbol,
                    "[dim]info[/dim]",
                )
            break

    if not resolved:
        table.add_row(
            "Symbol Lookup (all exchanges)",
            "Not found",
            "[red]Missing[/red]",
        )

    # 3. Try resolve() which may raise InstrumentNotFoundError
    try:
        for exchange_label in ("NSE", "INDEX", "NFO"):
            inst = resolver.resolve(symbol, exchange_label)
            table.add_row(
                f"Resolve ({exchange_label})",
                f"{inst.symbol} [{inst.exchange.value}]",
                "[green]OK[/green]",
            )
            break
    except Exception:
        table.add_row(
            "Resolve (strict)",
            "Symbol not in resolver index",
            "[yellow]Not Indexed[/yellow]",
        )

    # 4. Search all instruments for partial matches
    all_instruments = resolver.all_instruments()
    partial_matches = [
        i
        for i in all_instruments
        if symbol in i.symbol.upper() and i.instrument_type.value in ("EQUITY", "FUTURE")
    ]
    if partial_matches and not resolved:
        sample = partial_matches[:5]
        symbols_str = ", ".join(f"{i.symbol} ({i.exchange.value})" for i in sample)
        table.add_row(
            "Partial Matches",
            symbols_str,
            f"[yellow]{len(partial_matches)} found[/yellow]",
        )

    console.print(table)
