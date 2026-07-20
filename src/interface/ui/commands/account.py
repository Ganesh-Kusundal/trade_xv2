"""CLI command handler for account operations."""

from __future__ import annotations

import logging

from rich.console import Console

from interface.ui.services.broker_ops import get_funds, get_positions
from interface.ui.commands._broker import broker_id_from
from interface.ui.services.renderers import render_account_with_pnl

logger = logging.getLogger(__name__)


def show_account(broker_service=None, console: Console | None = None) -> None:
    """Print active account limits, margin, and day PnL."""
    if console is None:
        console = Console()
    try:
        funds = get_funds(broker_id_from(broker_service))
        positions = get_positions(broker_id_from(broker_service)) or []
        render_account_with_pnl(console, funds, positions)
    except Exception as exc:
        console.print(f"[red]Error fetching account details: {exc}[/red]")


def run(args: list[str], broker_service=None, console: Console | None = None) -> None:
    """Entry point for account subcommand."""
    show_account(broker_service, console)
