"""CLI command handler for portfolio (holdings and positions) operations."""

from __future__ import annotations

from decimal import Decimal

from rich.console import Console
from rich.table import Table

from cli.services.broker_service import BrokerService


def show_holdings(broker_service: BrokerService, console: Console) -> None:
    """Print the holdings table."""
    broker = broker_service.active_broker
    try:
        holdings = broker.get_holdings()
        table = Table(title=f"{broker.name.capitalize()} Demat Holdings", header_style="bold green")
        table.add_column("Symbol", style="bold white")
        table.add_column("Qty", justify="right")
        table.add_column("Avg Price", justify="right")
        table.add_column("LTP", justify="right")
        table.add_column("PnL", justify="right")

        total_pnl = Decimal("0.00")
        for h in holdings:
            pnl_val = h.pnl
            total_pnl += pnl_val
            pnl_style = "green" if pnl_val > 0 else ("red" if pnl_val < 0 else "white")
            table.add_row(
                h.symbol,
                str(h.quantity),
                f"{h.avg_price:,.2f}",
                f"{h.ltp:,.2f}",
                f"[{pnl_style}]Rs. {pnl_val:,.2f}[/{pnl_style}]",
            )

        pnl_style = "green" if total_pnl > 0 else ("red" if total_pnl < 0 else "white")
        table.add_section()
        table.add_row("Total", "", "", "", f"[{pnl_style}]Rs. {total_pnl:,.2f}[/{pnl_style}]")

        console.print(table)
    except Exception as exc:
        console.print(f"[red]Error fetching holdings: {exc}[/red]")


def show_positions(broker_service: BrokerService, console: Console) -> None:
    """Print positions categorized by side and product."""
    broker = broker_service.active_broker
    try:
        positions = broker.get_positions()

        # Categorize
        long_pos = [p for p in positions if p.quantity > 0]
        short_pos = [p for p in positions if p.quantity < 0]
        day_pos = [p for p in positions if p.product_type == "INTRADAY"]
        overnight_pos = [p for p in positions if p.product_type in ("CNC", "MARGIN", "MTF")]

        def render_position_table(title: str, pos_list: list[Position], style: str) -> None:
            table = Table(title=title, header_style=f"bold {style}")
            table.add_column("Symbol", style="bold white")
            table.add_column("Product", justify="center")
            table.add_column("Net Qty", justify="right")
            table.add_column("Avg Price", justify="right")
            table.add_column("LTP", justify="right")
            table.add_column("PnL", justify="right")

            total_pnl = Decimal("0.00")
            for p in pos_list:
                pnl_val = p.unrealized_pnl + p.realized_pnl
                total_pnl += pnl_val
                pnl_style = "green" if pnl_val > 0 else ("red" if pnl_val < 0 else "white")
                table.add_row(
                    p.symbol,
                    p.product_type.value,
                    str(p.quantity),
                    f"{p.avg_price:,.2f}",
                    f"{p.ltp:,.2f}",
                    f"[{pnl_style}]Rs. {pnl_val:,.2f}[/{pnl_style}]",
                )
            pnl_style = "green" if total_pnl > 0 else ("red" if total_pnl < 0 else "white")
            table.add_section()
            table.add_row(
                "Total PnL", "", "", "", "", f"[{pnl_style}]Rs. {total_pnl:,.2f}[/{pnl_style}]"
            )
            console.print(table)
            console.print()

        console.print(f"Positions Overview for [bold yellow]{broker.name.upper()}[/bold yellow]:")
        console.print()

        render_position_table("Long Positions", long_pos, "green")
        render_position_table("Short Positions", short_pos, "red")
        render_position_table("Day Positions (INTRADAY)", day_pos, "cyan")
        render_position_table("Overnight Positions (CNC/MARGIN)", overnight_pos, "magenta")

    except Exception as exc:
        console.print(f"[red]Error fetching positions: {exc}[/red]")


def run(args: list[str], broker_service: BrokerService, console: Console) -> None:
    """Entry point for portfolio subcommands."""
    # We route based on caller context (either 'holdings' or 'positions')
    # Passed command name will be verified in main.py.
    pass
