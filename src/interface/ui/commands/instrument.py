"""CLI command handler for instrument resolution diagnostics."""

from __future__ import annotations

from domain.enums import BrokerId
from rich.console import Console
from rich.table import Table

from interface.ui.services.broker_ops import resolve_security
from interface.ui.services.broker_service import BrokerService
from domain.symbols import normalize_symbol


def _show_all_brokers(symbol: str, console: Console) -> None:
    """Dual-broker resolution via brokers.services."""
    console.print(f"\n[bold]Instrument Resolution: {symbol}[/bold]\n")
    for broker_id in (BrokerId.DHAN, BrokerId.UPSTOX):
        console.print(f"[cyan]--- {broker_id.capitalize()} ---[/cyan]")
        try:
            info = resolve_security(None, symbol, default=broker_id)
            table = Table(show_header=False, show_edge=False)
            table.add_column("Field", style="cyan", width=20)
            table.add_column("Value", width=40)
            for key, val in info.items():
                table.add_row(key.replace("_", " ").title(), str(val or "N/A"))
            console.print(table)
        except Exception as exc:
            console.print(f"  Resolution failed: {exc}")
        console.print()


def _show_active_broker(symbol: str, broker_service: BrokerService, console: Console) -> None:
    """Catalog diagnostics for the active broker gateway."""
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

    loaded = resolver_stats.get("loaded", False)
    total = resolver_stats.get("total", 0)
    if loaded:
        table.add_row(
            "Instrument Catalog",
            f"{total:,} instruments loaded",
            "[green]Active[/green]",
        )
    else:
        table.add_row("Instrument Catalog", "Not loaded", "[red]Not Loaded[/red]")

    resolved = False
    for exchange_label in ("NSE", "INDEX", "NFO", "BSE", "BFO", "MCX", "CDS"):
        inst = resolver.get_by_symbol(symbol, exchange_label)
        if inst is not None:
            table.add_row(
                f"Symbol ({exchange_label})",
                f"Symbol: {inst.symbol} | Type: {inst.instrument_type.value}",
                "[green]Resolved[/green]",
            )
            resolved = True
            if inst.expiry:
                table.add_row("  Expiry", inst.expiry, "[dim]info[/dim]")
            if inst.strike_price is not None:
                table.add_row("  Strike", str(inst.strike_price), "[dim]info[/dim]")
            if inst.option_type:
                table.add_row("  Option Type", inst.option_type.value, "[dim]info[/dim]")
            if inst.underlying:
                table.add_row("  Underlying", inst.underlying, "[dim]info[/dim]")
            if inst.lot_size and inst.lot_size > 1:
                table.add_row("  Lot Size", str(inst.lot_size), "[dim]info[/dim]")
            if inst.canonical_symbol:
                table.add_row("  Canonical", inst.canonical_symbol, "[dim]info[/dim]")
            break

    if not resolved:
        table.add_row("Symbol Lookup (all exchanges)", "Not found", "[red]Missing[/red]")

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


def run(args: list[str], broker_service: BrokerService, console: Console) -> None:
    """Entry point for instrument mapping subcommand."""
    if not args:
        console.print("[yellow]Usage: tradex instrument <symbol> [--all-brokers][/yellow]")
        return

    all_brokers = "--all-brokers" in args
    filtered = [a for a in args if a != "--all-brokers"]
    if not filtered:
        console.print("[yellow]Usage: tradex instrument <symbol> [--all-brokers][/yellow]")
        return

    symbol = normalize_symbol(filtered[0])
    if all_brokers:
        _show_all_brokers(symbol, console)
    else:
        _show_active_broker(symbol, broker_service, console)
