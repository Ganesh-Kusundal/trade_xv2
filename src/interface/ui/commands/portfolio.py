"""CLI command handler for portfolio (holdings and positions) operations."""

from __future__ import annotations

import logging

from rich.console import Console

from interface.ui.commands.registry import CommandResult
from interface.ui.services.broker_ops import get_holdings, get_positions
from interface.ui.commands._broker import broker_id_from
from interface.ui.services.renderers import render_holdings, render_positions

logger = logging.getLogger(__name__)


def show_holdings(broker_service=None, console: Console | None = None) -> CommandResult:
    """Print the holdings table and return CommandResult."""
    if console is None:
        console = Console()
    try:
        holdings = get_holdings(broker_id_from(broker_service)) or []
        render_holdings(console, holdings)
        holdings_data = [
            {
                "symbol": getattr(h, "symbol", "?"),
                "quantity": getattr(h, "quantity", 0),
                "avg_price": str(getattr(h, "avg_price", 0)),
                "ltp": str(getattr(h, "ltp", 0)),
                "pnl": str(getattr(h, "pnl", 0)),
            }
            for h in holdings
        ]
        return CommandResult(
            success=True,
            data={"holdings": holdings_data, "count": len(holdings)},
        )
    except Exception as exc:
        logger.exception("holdings_fetch_failed")
        console.print(f"[red]Error fetching holdings: {exc}[/red]")
        return CommandResult(success=False, error=str(exc))


def show_positions(broker_service=None, console: Console | None = None) -> None:
    """Print positions categorized by side and product."""
    if console is None:
        console = Console()
    try:
        positions = get_positions(broker_id_from(broker_service)) or []
        render_positions(console, positions)
    except Exception as exc:
        console.print(f"[red]Error fetching positions: {exc}[/red]")


def run(args: list[str], broker_service=None, console: Console | None = None) -> None:
    """Entry point for portfolio subcommands."""
    pass
