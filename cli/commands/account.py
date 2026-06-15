"""CLI command handler for account operations."""

from __future__ import annotations

from decimal import Decimal

from rich.console import Console
from rich.table import Table

from cli.services.broker_service import BrokerService


def show_account(broker_service: BrokerService, console: Console) -> None:
    """Print active account limits and margin information."""
    gw = broker_service.active_broker
    console.print(
        f"Active Account: [bold yellow]{broker_service.active_broker_name.upper()}[/bold yellow]"
    )

    try:
        balance = gw.portfolio.get_balance()
        positions = gw.portfolio.get_positions()

        # Calculate PnLs
        realized = sum(pos.realized_pnl for pos in positions)
        unrealized = sum(pos.unrealized_pnl for pos in positions)
        total_pnl = realized + unrealized

        table = Table(
            title=f"{broker_service.active_broker_name.capitalize()} Account Summary",
            header_style="bold magenta",
        )
        table.add_column("Metric", style="bold white")
        table.add_column("Value", justify="right")

        table.add_row("SOD Limit / Equity", f"Rs. {balance.sod_limit:,.2f}")
        table.add_row("Available Balance", f"Rs. {balance.available_balance:,.2f}")
        table.add_row("Utilized Amount", f"Rs. {balance.utilized_amount:,.2f}")
        table.add_row("Collateral Amount", f"Rs. {balance.collateral_amount:,.2f}")
        table.add_row("Withdrawable Balance", f"Rs. {balance.withdrawable_balance:,.2f}")

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
