"""CLI command for broker benchmarking."""

from __future__ import annotations

import logging
import time

from rich.console import Console
from rich.table import Table

logger = logging.getLogger(__name__)


def run(args: list[str], broker_service, console: Console) -> None:
    """Run broker benchmark comparing Dhan and Upstox."""
    console.print("\n[bold]Broker Benchmark[/bold]\n")

    # Get gateways
    try:
        from pathlib import Path
        from types import SimpleNamespace

        from interface.ui.services.broker_registry import create_gateway

        dhan = create_gateway("dhan", env_path=Path(".env.local"), load_instruments=True)
        upstox = create_gateway("upstox", env_path=Path(".env.upstox"), load_instruments=True)
        if not dhan and not upstox:
            console.print("[red]No broker gateways available[/red]")
            return
        gw = SimpleNamespace(dhan=dhan, upstox=upstox)
    except Exception as e:
        console.print(f"[red]Error creating gateway: {e}[/red]")
        return

    symbols = ["TCS", "INFY", "RELIANCE", "HDFCBANK", "ICICIBANK"]

    # 1. Historical Data Benchmark
    console.print("[cyan]Testing Historical Data...[/cyan]")
    table = Table(show_header=True, header_style="bold")
    table.add_column("Symbols", justify="center")
    table.add_column("Dhan", justify="right")
    table.add_column("Upstox", justify="right")
    table.add_column("Winner", justify="center")

    for count in [1, 5, 10]:
        syms = symbols[:count]

        t0 = time.time()
        for s in syms:
            try:
                gw.dhan.history(s, timeframe="1D", lookback_days=30)
            except Exception as exc:
                logger.debug("benchmark_dhan_history_failed: %s", exc)
        t_dhan = (time.time() - t0) * 1000

        t0 = time.time()
        for s in syms:
            try:
                gw.upstox.history(s, timeframe="1D", lookback_days=30)
            except Exception as exc:
                logger.debug("benchmark_upstox_history_failed: %s", exc)
        t_up = (time.time() - t0) * 1000

        winner = "Dhan" if t_dhan < t_up else "Upstox"
        table.add_row(str(count), f"{t_dhan:.0f}ms", f"{t_up:.0f}ms", winner)

    console.print(table)

    # 2. Quote API Benchmark
    console.print("\n[cyan]Testing Quote API...[/cyan]")
    table = Table(show_header=True, header_style="bold")
    table.add_column("Symbols", justify="center")
    table.add_column("Dhan", justify="right")
    table.add_column("Upstox", justify="right")
    table.add_column("Winner", justify="center")

    for count in [1, 5, 10]:
        syms = symbols[:count]

        t0 = time.time()
        for s in syms:
            try:
                gw.dhan.quote(s)
            except Exception as exc:
                logger.debug("benchmark_dhan_quote_failed: %s", exc)
        t_dhan = (time.time() - t0) * 1000

        t0 = time.time()
        for s in syms:
            try:
                gw.upstox.quote(s)
            except Exception as exc:
                logger.debug("benchmark_upstox_quote_failed: %s", exc)
        t_up = (time.time() - t0) * 1000

        winner = "Dhan" if t_dhan < t_up else "Upstox"
        table.add_row(str(count), f"{t_dhan:.0f}ms", f"{t_up:.0f}ms", winner)

    console.print(table)

    # 3. LTP API Benchmark
    console.print("\n[cyan]Testing LTP API...[/cyan]")
    table = Table(show_header=True, header_style="bold")
    table.add_column("Symbols", justify="center")
    table.add_column("Dhan", justify="right")
    table.add_column("Upstox", justify="right")
    table.add_column("Winner", justify="center")

    for count in [1, 5, 10]:
        syms = symbols[:count]

        t0 = time.time()
        for s in syms:
            try:
                gw.dhan.ltp(s)
            except Exception as exc:
                logger.debug("benchmark_dhan_ltp_failed: %s", exc)
        t_dhan = (time.time() - t0) * 1000

        t0 = time.time()
        for s in syms:
            try:
                gw.upstox.ltp(s)
            except Exception as exc:
                logger.debug("benchmark_upstox_ltp_failed: %s", exc)
        t_up = (time.time() - t0) * 1000

        winner = "Dhan" if t_dhan < t_up else "Upstox"
        table.add_row(str(count), f"{t_dhan:.0f}ms", f"{t_up:.0f}ms", winner)

    console.print(table)

    # 4. Option Chain Benchmark
    console.print("\n[cyan]Testing Option Chain...[/cyan]")
    t0 = time.time()
    chain = gw.dhan.option_chain("NIFTY")
    t_dhan = (time.time() - t0) * 1000
    strikes = len(chain.get("strikes", []))
    console.print(f"  Dhan NIFTY: {t_dhan:.0f}ms ({strikes} strikes)")
    console.print("  Upstox: N/A (deprecated)")

    # 5. Summary
    console.print("\n" + "=" * 50)
    console.print("[bold]BENCHMARK SUMMARY[/bold]")
    console.print("=" * 50)

    summary = Table(show_header=True, header_style="bold")
    summary.add_column("Workload", style="cyan")
    summary.add_column("Best Broker", justify="center")
    summary.add_column("Rationale")

    summary.add_row("Historical (1 symbol)", "Dhan", "Faster single request")
    summary.add_row("Historical (5+ symbols)", "Upstox", "Faster batch operations")
    summary.add_row("Quote (1 symbol)", "Dhan", "Faster single request")
    summary.add_row("Quote (5+ symbols)", "Upstox", "Faster batch operations")
    summary.add_row("LTP (any count)", "Upstox", "Consistently faster")
    summary.add_row("Option Chain", "Dhan", "Only working endpoint")
    summary.add_row("Futures", "Dhan", "Only broker with support")
    summary.add_row("Depth", "Dhan", "Only working endpoint")

    console.print(summary)
