"""CLI commands for cache management.

Provides visibility and control over the instrument cache.

Commands:
    tradex cache status        # View cache state
    tradex cache clear         # Clear cache
    tradex cache refresh       # Force refresh from broker
    tradex cache stats         # Show cache statistics
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table

from interface.ui.services.broker_facade import InstrumentLoader
from interface.ui.commands.registry import CommandResult
from interface.ui.services.broker_service import BrokerService

logger = logging.getLogger(__name__)


def show_cache_status(
    args: list[str], broker_service: BrokerService, console: Console
) -> CommandResult:
    """Display current cache status."""
    # Find cache directory
    cache_dir = Path(__file__).resolve().parents[2] / "runtime-dev" / "instruments"

    if not cache_dir.exists():
        console.print("[yellow]Cache directory not found[/yellow]")
        return CommandResult(success=False, error="Cache directory not found")

    # Find cache files
    cache_files = list(cache_dir.glob("instruments_*.csv"))
    cache_files = [f for f in cache_files if not f.name.endswith(".tmp")]

    if not cache_files:
        console.print("[yellow]No cached instruments found[/yellow]")
        return CommandResult(success=True, data={"cached": False})

    # Get latest cache
    latest = max(cache_files, key=lambda f: f.stat().st_mtime)
    mtime = datetime.fromtimestamp(latest.stat().st_mtime)
    age_hours = (datetime.now() - mtime).total_seconds() / 3600.0

    table = Table(title="📦 Instrument Cache Status", header_style="bold cyan")
    table.add_column("Property", style="bold white")
    table.add_column("Value")

    table.add_row("Cache Directory", str(cache_dir))
    table.add_row("Latest Cache", latest.name)
    table.add_row("Cache Size", f"{latest.stat().st_size / 1024 / 1024:.2f} MB")
    table.add_row("Cached At", mtime.strftime("%Y-%m-%d %H:%M:%S"))
    table.add_row("Age", f"{age_hours:.1f} hours")
    table.add_row(
        "Status",
        "[green]Fresh (< 6h)[/green]" if age_hours < 6 else "[yellow]Stale (> 6h)[/yellow]",
    )
    table.add_row("Total Files", str(len(cache_files)))

    console.print(table)

    return CommandResult(
        success=True,
        data={
            "cached": True,
            "latest_cache": latest.name,
            "age_hours": round(age_hours, 1),
            "file_count": len(cache_files),
        },
    )


def clear_cache(args: list[str], broker_service: BrokerService, console: Console) -> CommandResult:
    """Clear instrument cache."""
    if "--confirm" not in args:
        console.print("[yellow]This will delete all cached instrument files.[/yellow]")
        console.print("[yellow]Usage: tradex cache clear --confirm[/yellow]")
        return CommandResult(success=False, error="Confirmation required: use --confirm")

    cache_dir = Path(__file__).resolve().parents[2] / "runtime-dev" / "instruments"

    if not cache_dir.exists():
        console.print("[yellow]Cache directory not found[/yellow]")
        return CommandResult(success=True, data={"cleared": 0})

    cache_files = list(cache_dir.glob("instruments_*.csv"))
    cleared = 0

    for cache_file in cache_files:
        try:
            cache_file.unlink()
            cleared += 1
        except Exception as exc:
            console.print(f"[red]Failed to delete {cache_file.name}: {exc}[/red]")

    console.print(f"[green]✅ Cleared {cleared} cached instrument files[/green]")

    return CommandResult(success=True, data={"cleared": cleared})


def refresh_cache(
    args: list[str], broker_service: BrokerService, console: Console
) -> CommandResult:
    """Force refresh cache from broker."""
    console.print("[cyan]🔄 Refreshing instrument cache from Dhan...[/cyan]")

    try:
        start_time = time.time()
        rows = InstrumentLoader.load_cached(force_refresh=True)
        elapsed = time.time() - start_time

        console.print(
            f"[green]✅ Cache refreshed: {len(rows):,} instruments in {elapsed:.2f}s[/green]"
        )

        return CommandResult(
            success=True,
            data={
                "instruments_loaded": len(rows),
                "elapsed_seconds": round(elapsed, 2),
            },
        )
    except Exception as exc:
        console.print(f"[red]❌ Cache refresh failed: {exc}[/red]")
        return CommandResult(success=False, error=str(exc))


def show_cache_stats(
    args: list[str], broker_service: BrokerService, console: Console
) -> CommandResult:
    """Display cache statistics."""
    cache_dir = Path(__file__).resolve().parents[2] / "runtime-dev" / "instruments"

    if not cache_dir.exists():
        console.print("[yellow]Cache directory not found[/yellow]")
        return CommandResult(success=False, error="Cache directory not found")

    cache_files = list(cache_dir.glob("instruments_*.csv"))
    cache_files = [f for f in cache_files if not f.name.endswith(".tmp")]

    if not cache_files:
        console.print("[yellow]No cached instruments found[/yellow]")
        return CommandResult(success=True, data={"cached": False})

    # Calculate statistics
    total_size = sum(f.stat().st_size for f in cache_files)
    oldest = min(cache_files, key=lambda f: f.stat().st_mtime)
    newest = max(cache_files, key=lambda f: f.stat().st_mtime)

    table = Table(title="📊 Instrument Cache Statistics", header_style="bold magenta")
    table.add_column("Metric", style="bold white")
    table.add_column("Value", justify="right")

    table.add_row("Total Cache Files", str(len(cache_files)))
    table.add_row("Total Size", f"{total_size / 1024 / 1024:.2f} MB")
    table.add_row("Oldest Cache", oldest.name)
    table.add_row("Newest Cache", newest.name)
    table.add_row("Cache Directory", str(cache_dir))

    console.print(table)

    return CommandResult(
        success=True,
        data={
            "file_count": len(cache_files),
            "total_size_mb": round(total_size / 1024 / 1024, 2),
        },
    )


def run(args: list[str], broker_service: BrokerService, console: Console) -> CommandResult:
    """Entry point for cache commands."""
    if not args:
        console.print("[yellow]Usage: tradex cache [status|clear|refresh|stats][/yellow]")
        return CommandResult(success=False, error="Missing subcommand")

    subcmd = args[0].lower()

    if subcmd == "status":
        return show_cache_status(args[1:], broker_service, console)
    elif subcmd == "clear":
        return clear_cache(args[1:], broker_service, console)
    elif subcmd == "refresh":
        return refresh_cache(args[1:], broker_service, console)
    elif subcmd == "stats":
        return show_cache_stats(args[1:], broker_service, console)
    else:
        console.print(f"[red]Unknown cache subcommand: {subcmd}[/red]")
        return CommandResult(success=False, error=f"Unknown subcommand: {subcmd}")
