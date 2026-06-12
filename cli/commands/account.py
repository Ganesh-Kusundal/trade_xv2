"""CLI command handler for account operations."""

from __future__ import annotations

from decimal import Decimal

from rich.console import Console
from rich.table import Table

from cli.services.broker_service import BrokerService


def show_account(broker_service: BrokerService, console: Console) -> None:
    """Print active account limits and margin information."""
    broker = broker_service.active_broker
    console.print(
        f"Active Account: [bold yellow]{broker.name.upper()}[/bold yellow] (ID: {broker.broker_id})"
    )

    try:
        limits = broker.get_fund_limits()
        positions = broker.get_positions()

        # Calculate PnLs
        realized = sum(pos.realized_pnl for pos in positions)
        unrealized = sum(pos.unrealized_pnl for pos in positions)
        total_pnl = realized + unrealized

        table = Table(
            title=f"{broker.name.capitalize()} Account Summary", header_style="bold magenta"
        )
        table.add_column("Metric", style="bold white")
        table.add_column("Value", justify="right")

        table.add_row("Total Margin / Equity", f"Rs. {limits.total_margin:,.2f}")
        table.add_row("Available Margin", f"Rs. {limits.available_balance:,.2f}")
        table.add_row("Used Margin", f"Rs. {limits.used_margin:,.2f}")

        # Mock collateral value for diagnostics visual richness
        collateral = limits.total_margin - limits.available_balance - limits.used_margin
        collateral_val = collateral if collateral > 0 else Decimal("0.00")
        table.add_row("Collateral Value", f"Rs. {collateral_val:,.2f}")

        # Colorize PnLs
        def colorize_val(val: Decimal) -> str:
            if val > 0:
                return f"[green]Rs. {val:,.2f}[/green]"
            elif val < 0:
                return f"[red]Rs. {val:,.2f}[/red]"
            return f"[white]Rs. {val:,.2f}[/white]"

        table.add_row("Realized Day PnL", colorize_val(realized))
        table.add_row("Unrealized Day PnL", colorize_val(unrealized))
        table.add_row("Total Day PnL", colorize_val(total_pnl))

        console.print(table)
    except Exception as exc:
        console.print(f"[red]Error fetching account details: {exc}[/red]")


def run(args: list[str], broker_service: BrokerService, console: Console) -> None:
    """Entry point for account subcommand."""
    show_account(broker_service, console)
