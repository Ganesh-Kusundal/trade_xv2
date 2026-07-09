"""CLI command for syncing option data from Trade_J DuckDB to TradeXV2 Parquet."""

from __future__ import annotations

import logging

from rich.console import Console

from datalake.ingestion.sync_options import sync_options

# Initialize logging if not already configured
if not logging.getLogger().handlers:
    from infrastructure.logging_config import configure_logging

    configure_logging()
logger = logging.getLogger(__name__)


def run_options_sync(args: list[str], console: Console) -> None:
    """Sync option data from Trade_J DuckDB into TradeXV2 Parquet.

    Usage: tradex options sync [--dry-run]
    """
    dry_run = "--dry-run" in args

    if dry_run:
        console.print("[yellow]DRY-RUN: not writing to disk[/yellow]")

    console.print("[dim]Syncing option data from Trade_J DuckDB → TradeXV2...[/dim]")

    try:
        summary = sync_options()
    except Exception as exc:
        console.print(f"[red]Sync failed: {exc}[/red]")
        return

    if dry_run:
        console.print("[green]DRY-RUN complete. No data written.[/green]")
        return

    console.print(
        f"[bold green]Sync complete:[/bold green] "
        f"{summary['files_created']} created, "
        f"{summary['files_merged']} merged, "
        f"{summary['new_rows']:,} new rows, "
        f"{summary['total_rows_after']:,} total"
    )

    if summary["new_rows"] == 0 and summary["files_created"] == 0:
        console.print("[dim]No new data — all up to date.[/dim]")
