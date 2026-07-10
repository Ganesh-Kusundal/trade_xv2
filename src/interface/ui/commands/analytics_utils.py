"""Shared utilities for analytics CLI commands."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from rich.console import Console
from rich.table import Table


def load_dataframe(args: list[str]) -> pd.DataFrame | None:
    if not args or args[0] is None:
        return None
    path = Path(args[0])
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")
    return pd.read_csv(path)


def print_records(console: Console, records: list[dict[str, object]], *, limit: int) -> None:
    if not records:
        console.print("[yellow]No candidates found.[/yellow]")
        return

    first = records[0]
    table = Table(title="Analytics Results", header_style="bold cyan")
    for key in list(first.keys())[:8]:
        table.add_column(str(key))
    for row in records[:limit]:
        table.add_row(*[format_record_value(row.get(key, "")) for key in list(first.keys())[:8]])
    console.print(table)


def print_scan_result(console: Console, result, *, limit: int) -> None:
    """Print ScanResult from the new scanner framework."""
    if not result.candidates:
        console.print("[yellow]No candidates found.[/yellow]")
        return

    table = Table(title=f"Scanner: {result.scanner}", header_style="bold cyan")
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


def parse_common_args(args: list[str], **defaults) -> dict:
    """Parse common CLI arguments like --file, --limit, --symbol, --years."""
    result = dict(defaults)
    index = 0
    while index < len(args):
        arg = args[index]
        if arg in {"--file", "--csv"} and index + 1 < len(args):
            result["file_path"] = args[index + 1]
            index += 2
        elif arg == "--limit" and index + 1 < len(args):
            result["limit"] = int(args[index + 1])
            index += 2
        elif arg == "--symbol" and index + 1 < len(args):
            result["symbol"] = args[index + 1].upper()
            index += 2
        elif arg == "--years" and index + 1 < len(args):
            result["years"] = float(args[index + 1])
            index += 2
        elif arg == "--capital" and index + 1 < len(args):
            result["capital"] = float(args[index + 1])
            index += 2
        elif not arg.startswith("--"):
            if "symbol" not in result:
                result["symbol"] = args[index].upper()
            index += 1
        else:
            index += 1
    return result


def format_record_value(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.4f}"
    if isinstance(value, list | dict):
        return str(value)[:80]
    return str(value)


def last_float(data: pd.DataFrame, column: str) -> float | None:
    if column not in data or data.empty:
        return None
    value = data[column].iloc[-1]
    return float(value) if pd.notna(value) else None


def price_change(data: pd.DataFrame) -> float:
    if data.empty or "close" not in data or len(data) < 2:
        return 0.0
    return float(data["close"].iloc[-1] - data["close"].iloc[-2])
