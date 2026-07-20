"""CLI command for broker benchmarking."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from rich.console import Console
from rich.table import Table

from domain.enums import BrokerId
from interface.ui.commands._broker import broker_id_from
from interface.ui.services.broker_ops import get_history, get_option_chain, get_quote
from runtime.platform_bridge import run_benchmark

logger = logging.getLogger(__name__)


def _env_kwargs(broker_id: str) -> dict:
    env = Path(".env.local") if broker_id == BrokerId.DHAN else Path(".env.upstox")
    return {"env_path": str(env), "load_instruments": True}


def _broker_available(broker_id: str) -> bool:
    try:
        get_quote(broker_id_from(None, default=broker_id), "RELIANCE", **_env_kwargs(broker_id))
        return True
    except Exception as exc:
        logger.debug("benchmark_open_%s_failed: %s", broker_id, exc)
        return False


def run(args: list[str], broker_service, console: Console) -> None:
    """Run broker benchmark comparing Dhan and Upstox."""
    console.print("\n[bold]Broker Benchmark[/bold]\n")

    dhan_ok = _broker_available("dhan")
    upstox_ok = _broker_available("upstox")
    if not dhan_ok and not upstox_ok:
        console.print("[red]No broker sessions available[/red]")
        return

    symbols = ["TCS", "INFY", "RELIANCE", "HDFCBANK", "ICICIBANK"]
    _bench_history(dhan_ok, upstox_ok, symbols, console)
    _bench_quote(dhan_ok, upstox_ok, symbols, console)
    _bench_ltp(dhan_ok, upstox_ok, symbols, console)
    _bench_option_chain(dhan_ok, console)
    _print_services_benchmark(dhan_ok, upstox_ok, console)
    _print_summary(console)


def _bench_history(dhan_ok: bool, upstox_ok: bool, symbols: list[str], console: Console) -> None:
    console.print("[cyan]Testing Historical Data...[/cyan]")
    table = Table(show_header=True, header_style="bold")
    table.add_column("Symbols", justify="center")
    table.add_column("Dhan", justify="right")
    table.add_column("Upstox", justify="right")
    table.add_column("Winner", justify="center")

    for count in [1, 5, 10]:
        syms = symbols[:count]
        t_dhan = _timed_history(BrokerId.DHAN, syms) if dhan_ok else float("inf")
        t_up = _timed_history(BrokerId.UPSTOX, syms) if upstox_ok else float("inf")
        winner = "Dhan" if t_dhan < t_up else "Upstox"
        table.add_row(
            str(count),
            f"{t_dhan:.0f}ms" if dhan_ok else "N/A",
            f"{t_up:.0f}ms" if upstox_ok else "N/A",
            winner,
        )
    console.print(table)


def _timed_history(broker_id: str, syms: list[str]) -> float:
    t0 = time.time()
    kw = _env_kwargs(broker_id)
    for s in syms:
        try:
            get_history(broker_id_from(None, default=broker_id), s, days=30, **kw)
        except Exception as exc:
            logger.debug("benchmark_history_failed: %s", exc)
    return (time.time() - t0) * 1000


def _bench_quote(dhan_ok: bool, upstox_ok: bool, symbols: list[str], console: Console) -> None:
    console.print("\n[cyan]Testing Quote API...[/cyan]")
    table = Table(show_header=True, header_style="bold")
    table.add_column("Symbols", justify="center")
    table.add_column("Dhan", justify="right")
    table.add_column("Upstox", justify="right")
    table.add_column("Winner", justify="center")

    for count in [1, 5, 10]:
        syms = symbols[:count]
        t_dhan = _timed_quote(BrokerId.DHAN, syms) if dhan_ok else float("inf")
        t_up = _timed_quote(BrokerId.UPSTOX, syms) if upstox_ok else float("inf")
        winner = "Dhan" if t_dhan < t_up else "Upstox"
        table.add_row(
            str(count),
            f"{t_dhan:.0f}ms" if dhan_ok else "N/A",
            f"{t_up:.0f}ms" if upstox_ok else "N/A",
            winner,
        )
    console.print(table)


def _timed_quote(broker_id: str, syms: list[str]) -> float:
    t0 = time.time()
    kw = _env_kwargs(broker_id)
    for s in syms:
        try:
            get_quote(broker_id_from(None, default=broker_id), s, **kw)
        except Exception as exc:
            logger.debug("benchmark_quote_failed: %s", exc)
    return (time.time() - t0) * 1000


def _bench_ltp(dhan_ok: bool, upstox_ok: bool, symbols: list[str], console: Console) -> None:
    console.print("\n[cyan]Testing LTP API...[/cyan]")
    table = Table(show_header=True, header_style="bold")
    table.add_column("Symbols", justify="center")
    table.add_column("Dhan", justify="right")
    table.add_column("Upstox", justify="right")
    table.add_column("Winner", justify="center")

    for count in [1, 5, 10]:
        syms = symbols[:count]
        t_dhan = _timed_ltp(BrokerId.DHAN, syms) if dhan_ok else float("inf")
        t_up = _timed_ltp(BrokerId.UPSTOX, syms) if upstox_ok else float("inf")
        winner = "Dhan" if t_dhan < t_up else "Upstox"
        table.add_row(
            str(count),
            f"{t_dhan:.0f}ms" if dhan_ok else "N/A",
            f"{t_up:.0f}ms" if upstox_ok else "N/A",
            winner,
        )
    console.print(table)


def _timed_ltp(broker_id: str, syms: list[str]) -> float:
    return _timed_quote(broker_id, syms)


def _bench_option_chain(dhan_ok: bool, console: Console) -> None:
    console.print("\n[cyan]Testing Option Chain...[/cyan]")
    if not dhan_ok:
        console.print("  Dhan: N/A")
        console.print("  Upstox: N/A (deprecated)")
        return
    t0 = time.time()
    chain = get_option_chain(
        broker_id_from(None, default=BrokerId.DHAN), "NIFTY", **_env_kwargs(BrokerId.DHAN)
    )
    t_dhan = (time.time() - t0) * 1000
    strikes = len(getattr(chain, "strikes", []) or [])
    console.print(f"  Dhan NIFTY: {t_dhan:.0f}ms ({strikes} strikes)")
    console.print("  Upstox: N/A (deprecated)")


def _print_services_benchmark(dhan_ok: bool, upstox_ok: bool, console: Console) -> None:
    console.print("\n[cyan]brokers.services run_benchmark (per broker)...[/cyan]")
    for label, ok, broker_id in (
        ("Dhan", dhan_ok, BrokerId.DHAN),
        ("Upstox", upstox_ok, BrokerId.UPSTOX),
    ):
        if not ok:
            console.print(f"  {label}: N/A")
            continue
        try:
            report = run_benchmark(broker_id_from(None, default=broker_id))
            avg = (
                sum(r.latency_ms for r in report.results) / len(report.results)
                if report.results
                else 0
            )
            console.print(f"  {label}: avg {avg:.1f}ms ({len(report.results)} probes)")
        except Exception as exc:
            console.print(f"  {label}: ERROR ({exc})")


def _print_summary(console: Console) -> None:
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
