"""CLI command for instrument resolution."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table


def run(args: list[str], broker_service, console: Console) -> None:
    """Show instrument resolution details."""
    if not args:
        console.print("[yellow]Usage: tradex instrument <symbol>[/yellow]")
        return

    symbol = args[0].upper()

    console.print(f"\n[bold]Instrument Resolution: {symbol}[/bold]\n")

    # Get gateway
    try:
        from pathlib import Path
        from types import SimpleNamespace

        from cli.services.broker_registry import create_gateway

        dhan = create_gateway("dhan", env_path=Path(".env.local"), load_instruments=True)
        upstox = create_gateway("upstox", env_path=Path(".env.upstox"), load_instruments=True)
        if not dhan and not upstox:
            console.print("[red]No broker gateways available[/red]")
            return
        gw = SimpleNamespace(dhan=dhan, upstox=upstox)
    except Exception as e:
        console.print(f"[red]Error creating gateway: {e}[/red]")
        return

    # Dhan resolution
    console.print("[cyan]--- Dhan ---[/cyan]")
    try:
        inst = gw.dhan.instruments.resolve(symbol, "NSE")
        table = Table(show_header=False, show_edge=False)
        table.add_column("Field", style="cyan", width=20)
        table.add_column("Value", width=40)
        table.add_row("Symbol", inst.symbol)
        table.add_row("Canonical Symbol", inst.canonical_symbol or "N/A")
        table.add_row("Exchange", inst.exchange.value)
        table.add_row("Security ID", inst.security_id)
        table.add_row("Instrument Type", inst.instrument_type.value)
        table.add_row("Lot Size", str(inst.lot_size))
        table.add_row("Tick Size", str(inst.tick_size))
        console.print(table)
    except Exception as e:
        console.print(f"  Resolution failed: {e}")

    # Upstox resolution
    console.print("\n[cyan]--- Upstox ---[/cyan]")
    try:
        from cli.services.broker_facade import UpstoxDomainMapper

        segment = UpstoxDomainMapper.segment_to_wire("NSE")
        defn = gw.upstox.instruments.resolve(symbol=symbol, exchange_segment=segment)
        if defn:
            table = Table(show_header=False, show_edge=False)
            table.add_column("Field", style="cyan", width=20)
            table.add_column("Value", width=40)
            table.add_row("Symbol", defn.trading_symbol or defn.symbol)
            table.add_row("Exchange Segment", defn.exchange_segment)
            table.add_row("Instrument Key", defn.instrument_key)
            table.add_row("Instrument Type", defn.instrument_type)
            table.add_row("Lot Size", str(defn.lot_size))
            console.print(table)
        else:
            console.print("  Resolution failed: instrument not found")
    except Exception as e:
        console.print(f"  Resolution failed: {e}")
