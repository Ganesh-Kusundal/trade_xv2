"""Scanner CLI commands."""

from __future__ import annotations

import logging

import pandas as pd
from rich.console import Console
from rich.table import Table

from analytics import Analytics
from analytics.scanner import BreakoutScanner, MomentumScanner, RSScanner, VolumeScanner

from .analytics_utils import load_dataframe, print_scan_result

logger = logging.getLogger(__name__)


def run_scan(args: list[str], console: Console) -> None:
    """Run generic scan command."""
    scanner_name = "breakout"
    file_path = None
    limit = 20

    index = 0
    while index < len(args):
        arg = args[index]
        if arg in {"--scanner", "--scan"} and index + 1 < len(args):
            scanner_name = args[index + 1].lower()
            index += 2
        elif arg in {"--file", "--csv"} and index + 1 < len(args):
            file_path = args[index + 1]
            index += 2
        elif arg == "--limit" and index + 1 < len(args):
            limit = int(args[index + 1])
            index += 2
        elif not arg.startswith("--"):
            scanner_name = arg.lower()
            index += 1
        else:
            index += 1

    data = load_dataframe([file_path] if file_path else [])
    if data is None or data.empty:
        console.print("[yellow]No data. Provide --file with OHLCV data (symbol,timestamp,open,high,low,close,volume).[/yellow]")
        return

    result = Analytics().scan(data, scanner=scanner_name)
    if hasattr(result, "candidates"):
        print_scan_result(console, result, limit=limit)
    else:
        from .analytics_utils import print_records
        print_records(console, result.charts[0]["data"] if result.charts else [], limit=limit)


def run_rank(args: list[str], console: Console) -> None:
    """Run rank command."""
    from .analytics_utils import print_records

    file_path = None
    limit = 20
    index = 0
    while index < len(args):
        arg = args[index]
        if arg in {"--file", "--csv"} and index + 1 < len(args):
            file_path = args[index + 1]
            index += 2
        elif arg == "--limit" and index + 1 < len(args):
            limit = int(args[index + 1])
            index += 2
        else:
            index += 1

    data = load_dataframe([file_path] if file_path else [])
    if data is not None:
        result = Analytics().rank(data, name="ranking")
    else:
        result = Analytics().rank().top_stocks()
    print_records(console, result.charts[0]["data"] if result.charts else [], limit=limit)


def run_scanner_command(scanner_name: str, args: list[str], broker_service, console: Console) -> None:
    """Run a specific scanner command."""
    limit = 10
    file_path = None
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--limit" and index + 1 < len(args):
            limit = int(args[index + 1])
            index += 2
        elif arg == "--file" and index + 1 < len(args):
            file_path = args[index + 1]
            index += 2
        else:
            index += 1

    if file_path:
        try:
            universe = pd.read_csv(file_path)
            console.print(f"[dim]Loaded {len(universe)} rows from {file_path}[/dim]")
        except Exception as exc:
            console.print(f"[red]Error loading file: {exc}[/red]")
            return

        required = {"close"}
        missing = required - set(universe.columns)
        if missing:
            console.print(f"[red]Missing required columns: {missing}[/red]")
            console.print("[dim]Expected OHLCV data: symbol, timestamp, open, high, low, close, volume[/dim]")
            console.print("[dim]Universe CSVs (only symbols) won't work — use market data with prices.[/dim]")
            return
    else:
        gateway = broker_service.active_broker
        if gateway is None:
            console.print("[red]No active broker. Connect first or provide --file[/red]")
            return
        console.print("[yellow]Loading universe data from broker...[/yellow]")
        universe = _load_universe_from_broker(gateway, console)
        if universe is None or universe.empty:
            console.print("[red]Could not load universe data[/red]")
            return

    scanners = {
        "momentum": MomentumScanner,
        "volume": VolumeScanner,
        "rs": RSScanner,
        "breakout": BreakoutScanner,
    }
    scanner_class = scanners.get(scanner_name)
    if not scanner_class:
        console.print(f"[red]Unknown scanner: {scanner_name}[/red]")
        return

    console.print(f"[dim]Running {scanner_name} scanner on {len(universe)} stocks...[/dim]")
    scanner = scanner_class()
    result = scanner.scan(universe)

    # Persist scan results to DuckDB
    try:
        from datalake.scan_store import save_scan_result
        scan_id = save_scan_result(
            scanner=scanner_name,
            candidates=result.candidates,
            universe_size=result.universe_size,
        )
        console.print(f"[dim]Scan saved: {scan_id}[/dim]")
    except Exception as exc:
        logger.debug("Failed to save scan results: %s", exc)

    if not result.candidates:
        console.print("[yellow]No candidates found.[/yellow]")
        return

    table = Table(title=f"Scanner: {scanner_name.upper()}", header_style="bold cyan")
    table.add_column("#", style="dim", width=4)
    table.add_column("Symbol", style="bold white")
    table.add_column("Score", style="green")
    table.add_column("Reasons", style="cyan")

    for i, candidate in enumerate(result.top(limit), 1):
        table.add_row(
            str(i),
            candidate.symbol,
            f"{candidate.score:.1f}",
            ", ".join(candidate.reasons) if candidate.reasons else "-",
        )

    console.print(table)
    console.print(f"[dim]{result.count} candidates from {result.universe_size} stocks[/dim]")


def _load_universe_from_broker(gateway, console: Console) -> pd.DataFrame | None:
    """Load universe data from broker (simplified version)."""
    return None
