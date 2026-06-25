"""CLI command for broker comparison."""

from __future__ import annotations

import time

from rich.console import Console
from rich.table import Table


def run(args: list[str], broker_service, console: Console) -> None:
    """Compare data between brokers."""
    if not args:
        console.print("[yellow]Usage: tradex compare <quote|history|ltp> <symbol>[/yellow]")
        return

    compare_type = args[0].lower()
    symbol = args[1].upper() if len(args) > 1 else "TCS"

    console.print(f"\n[bold]Broker Comparison: {compare_type.upper()} {symbol}[/bold]\n")

    # Get gateways
    try:
        from pathlib import Path

        from brokers.common.intelligent_gateway import IntelligentGateway
        from cli.services.broker_registry import create_gateway

        dhan = create_gateway("dhan", env_path=Path(".env.local"), load_instruments=True)
        upstox = create_gateway("upstox", env_path=Path(".env.upstox"), load_instruments=True)
        if dhan and upstox:
            gw = IntelligentGateway(dhan_gateway=dhan, upstox_gateway=upstox)
        elif dhan:
            gw = dhan
        elif upstox:
            gw = upstox
        else:
            console.print("[red]No broker gateways available[/red]")
            return
    except Exception as e:
        console.print(f"[red]Error creating gateway: {e}[/red]")
        return

    if compare_type == "quote":
        _compare_quote(gw, symbol, console)
    elif compare_type == "ltp":
        _compare_ltp(gw, symbol, console)
    elif compare_type == "history":
        _compare_history(gw, symbol, console)
    else:
        console.print(f"[yellow]Unknown comparison type: {compare_type}[/yellow]")


def _compare_quote(gw, symbol: str, console: Console) -> None:
    """Compare quote data between brokers."""
    table = Table(show_header=True, header_style="bold")
    table.add_column("Broker", style="cyan")
    table.add_column("LTP", justify="right")
    table.add_column("Bid", justify="right")
    table.add_column("Ask", justify="right")
    table.add_column("Volume", justify="right")
    table.add_column("Latency", justify="right")

    results = {}
    for name, broker in [("Dhan", gw.dhan), ("Upstox", gw.upstox)]:
        try:
            t0 = time.time()
            q = broker.quote(symbol)
            latency = (time.time() - t0) * 1000
            bid_str = f"₹{q.bid}" if hasattr(q, "bid") and q.bid else "N/A"
            ask_str = f"₹{q.ask}" if hasattr(q, "ask") and q.ask else "N/A"
            table.add_row(name, f"₹{q.ltp}", bid_str, ask_str, f"{q.volume:,}", f"{latency:.0f}ms")
            results[name] = q
        except Exception as e:
            # Check if it's an auth error
            if "401" in str(e) or "auth" in str(e).lower():
                table.add_row(name, "N/A", "-", "-", "-", "token expired")
            else:
                table.add_row(name, "ERROR", "-", "-", "-", str(e)[:20])

    console.print(table)

    # Calculate difference
    if len(results) == 2:
        q1, q2 = list(results.values())
        diff = abs(float(q1.ltp) - float(q2.ltp))
        console.print(f"\nDifference: ₹{diff:.2f}")
        console.print(f"Validation: {'PASS' if diff < 1 else 'WARN'}")


def _compare_ltp(gw, symbol: str, console: Console) -> None:
    """Compare LTP between brokers."""
    table = Table(show_header=True, header_style="bold")
    table.add_column("Broker", style="cyan")
    table.add_column("LTP", justify="right")
    table.add_column("Latency", justify="right")

    results = {}
    for name, broker in [("Dhan", gw.dhan), ("Upstox", gw.upstox)]:
        try:
            t0 = time.time()
            ltp = broker.ltp(symbol)
            latency = (time.time() - t0) * 1000
            table.add_row(name, f"₹{ltp}", f"{latency:.0f}ms")
            results[name] = ltp
        except Exception as e:
            table.add_row(name, "ERROR", str(e)[:20])

    console.print(table)

    if len(results) == 2:
        diff = abs(float(results.get("Dhan", 0)) - float(results.get("Upstox", 0)))
        console.print(f"\nDifference: ₹{diff:.2f}")
        console.print(f"Validation: {'PASS' if diff < 1 else 'WARN'}")


def _compare_history(gw, symbol: str, console: Console) -> None:
    """Compare historical data between brokers."""
    table = Table(show_header=True, header_style="bold")
    table.add_column("Broker", style="cyan")
    table.add_column("Rows", justify="right")
    table.add_column("Start", justify="right")
    table.add_column("End", justify="right")
    table.add_column("Latency", justify="right")

    for name, broker in [("Dhan", gw.dhan), ("Upstox", gw.upstox)]:
        try:
            t0 = time.time()
            df = broker.history(symbol, timeframe="1D", lookback_days=30)
            latency = (time.time() - t0) * 1000
            rows = len(df)
            start = str(df["timestamp"].min())[:10] if not df.empty else "N/A"
            end = str(df["timestamp"].max())[:10] if not df.empty else "N/A"
            table.add_row(name, str(rows), start, end, f"{latency:.0f}ms")
        except Exception as e:
            table.add_row(name, "ERROR", "-", "-", str(e)[:20])

    console.print(table)
