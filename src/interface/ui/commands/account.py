"""CLI command handler for account operations."""

from __future__ import annotations

import logging

from rich.console import Console

from interface.ui.services.broker_ops import fetch_funds, fetch_positions
from interface.ui.services.renderers import render_account_with_pnl

logger = logging.getLogger(__name__)


def show_account(broker_service=None, console: Console | None = None) -> None:
    """Print active account limits, margin, and day PnL."""
    if console is None:
        console = Console()
    try:
        funds = fetch_funds(broker_service)
        positions = fetch_positions(broker_service) or []
        render_account_with_pnl(console, funds, positions)
    except Exception as exc:
        console.print(f"[red]Error fetching account details: {exc}[/red]")


def run(args: list[str], broker_service=None, console: Console | None = None) -> None:
    """Entry point for account subcommand."""
    show_account(broker_service, console)
