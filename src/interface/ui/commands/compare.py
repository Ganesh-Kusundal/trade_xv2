"""Compare brokers using brokers.services (single code path)."""

from __future__ import annotations

import time
from pathlib import Path

from domain.enums import BrokerId
from rich.console import Console
from rich.table import Table

from interface.ui.services.broker_ops import get_history, get_quote
from interface.ui.commands._broker import broker_id_from


def _env_kwargs(broker_id: str) -> dict:
    env = Path(".env.local") if broker_id == BrokerId.DHAN else Path(".env.upstox")
    return {"env_path": str(env), "load_instruments": True}


def run(args: list[str], broker_service, console: Console) -> None:
    """Compare data between brokers."""
    if not args:
        console.print("[yellow]Usage: tradex compare <quote|history|ltp> <symbol>[/yellow]")
        return

    compare_type = args[0].lower()
    symbol = args[1].upper() if len(args) > 1 else "TCS"

    console.print(f"\n[bold]Broker Comparison: {compare_type.upper()} {symbol}[/bold]\n")

    brokers: list[tuple[str, str]] = []
    for name in (BrokerId.DHAN, BrokerId.UPSTOX):
        try:
            get_quote(broker_id_from(None, default=name), symbol, **_env_kwargs(name))
            brokers.append((name.capitalize(), name))
        except Exception:
            pass

    if not brokers:
        console.print("[red]No broker sessions available[/red]")
        return

    if compare_type == "quote":
        _compare_quote(brokers, symbol, console)
    elif compare_type == "ltp":
        _compare_ltp(brokers, symbol, console)
    elif compare_type == "history":
        _compare_history(brokers, symbol, console)
    else:
        console.print(f"[yellow]Unknown comparison type: {compare_type}[/yellow]")


def _compare_quote(brokers: list[tuple[str, str]], symbol: str, console: Console) -> None:
    table = Table(show_header=True, header_style="bold")
    table.add_column("Broker", style="cyan")
    table.add_column("LTP", justify="right")
    table.add_column("Bid", justify="right")
    table.add_column("Ask", justify="right")
    table.add_column("Volume", justify="right")
    table.add_column("Latency", justify="right")

    results = {}
    for name, broker_id in brokers:
        try:
            t0 = time.time()
            q = get_quote(broker_id_from(None, default=broker_id), symbol, **_env_kwargs(broker_id))
            latency = (time.time() - t0) * 1000
            bid_str = f"₹{q.bid}" if hasattr(q, "bid") and q.bid else "N/A"
            ask_str = f"₹{q.ask}" if hasattr(q, "ask") and q.ask else "N/A"
            table.add_row(name, f"₹{q.ltp}", bid_str, ask_str, f"{q.volume:,}", f"{latency:.0f}ms")
            results[name] = q
        except Exception as e:
            if "401" in str(e) or "auth" in str(e).lower():
                table.add_row(name, "N/A", "-", "-", "-", "token expired")
            else:
                table.add_row(name, "ERROR", "-", "-", "-", str(e)[:20])

    console.print(table)
    if len(results) == 2:
        q1, q2 = list(results.values())
        diff = abs(float(q1.ltp) - float(q2.ltp))
        console.print(f"\nDifference: ₹{diff:.2f}")
        console.print(f"Validation: {'PASS' if diff < 1 else 'WARN'}")


def _compare_ltp(brokers: list[tuple[str, str]], symbol: str, console: Console) -> None:
    table = Table(show_header=True, header_style="bold")
    table.add_column("Broker", style="cyan")
    table.add_column("LTP", justify="right")
    table.add_column("Latency", justify="right")

    results = {}
    for name, broker_id in brokers:
        try:
            t0 = time.time()
            q = get_quote(broker_id_from(None, default=broker_id), symbol, **_env_kwargs(broker_id))
            ltp = q.ltp
            latency = (time.time() - t0) * 1000
            table.add_row(name, f"₹{ltp}", f"{latency:.0f}ms")
            results[name] = ltp
        except Exception as e:
            table.add_row(name, "ERROR", str(e)[:20])

    console.print(table)
    if len(results) == 2:
        vals = list(results.values())
        diff = abs(float(vals[0]) - float(vals[1]))
        console.print(f"\nDifference: ₹{diff:.2f}")
        console.print(f"Validation: {'PASS' if diff < 1 else 'WARN'}")


def _compare_history(brokers: list[tuple[str, str]], symbol: str, console: Console) -> None:
    table = Table(show_header=True, header_style="bold")
    table.add_column("Broker", style="cyan")
    table.add_column("Bars", justify="right")
    table.add_column("Latency", justify="right")

    for name, broker_id in brokers:
        try:
            t0 = time.time()
            series = get_history(
                broker_id_from(None, default=broker_id), symbol, days=30, **_env_kwargs(broker_id)
            )
            latency = (time.time() - t0) * 1000
            n = getattr(series, "bar_count", 0)
            table.add_row(name, str(n), f"{latency:.0f}ms")
        except Exception as e:
            table.add_row(name, "ERROR", str(e)[:20])

    console.print(table)
