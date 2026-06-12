"""CLI command handler for OMS, orders, and trade operations."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from cli.services.oms_service import OmsService


def show_orders(
    oms_service: OmsService, console: Console, status_filter: str | None = None
) -> None:
    """Print the orders book with optional status filtering."""
    try:
        orders = oms_service.get_orders(status_filter)
        title = "Today's Orders"
        if status_filter:
            title += f" (Filter: {status_filter.upper()})"

        table = Table(title=title, header_style="bold blue")
        table.add_column("Order ID", style="bold white")
        table.add_column("Symbol", style="bold white")
        table.add_column("Side", justify="center")
        table.add_column("Type", justify="center")
        table.add_column("Qty (Filled/Total)", justify="center")
        table.add_column("Limit Price", justify="right")
        table.add_column("Avg Price", justify="right")
        table.add_column("Status", justify="center")
        table.add_column("Time", justify="center")

        for o in orders:
            side_style = "green" if o.side.value == "BUY" else "red"

            # Status styling
            if o.status.value == "FILLED":
                status_style = "green"
            elif o.status.value in ("OPEN", "PARTIALLY_FILLED"):
                status_style = "yellow"
            elif o.status.value == "CANCELLED":
                status_style = "dim white"
            else:
                status_style = "red"

            time_str = o.timestamp.strftime("%H:%M:%S") if o.timestamp else "N/A"

            table.add_row(
                o.order_id,
                o.symbol,
                f"[{side_style}]{o.side.value}[/{side_style}]",
                o.order_type.value,
                f"{o.filled_quantity}/{o.quantity}",
                f"{o.price:,.2f}" if o.price > 0 else "MARKET",
                f"{o.avg_price:,.2f}" if o.avg_price > 0 else "-",
                f"[{status_style}]{o.status.value}[/{status_style}]",
                time_str,
            )

        console.print(table)
    except Exception as exc:
        console.print(f"[red]Error fetching orders: {exc}[/red]")


def show_trades(oms_service: OmsService, console: Console) -> None:
    """Print the trades execution list."""
    try:
        trades = oms_service.get_trades()
        table = Table(title="Today's Trades Execution Book", header_style="bold yellow")
        table.add_column("Trade ID", style="bold white")
        table.add_column("Order ID", style="dim white")
        table.add_column("Symbol", style="bold white")
        table.add_column("Side", justify="center")
        table.add_column("Qty", justify="right")
        table.add_column("Price", justify="right")
        table.add_column("Value", justify="right")
        table.add_column("Time", justify="center")

        for t in trades:
            side_style = "green" if t.side.value == "BUY" else "red"
            time_str = t.timestamp.strftime("%H:%M:%S") if t.timestamp else "N/A"
            table.add_row(
                t.trade_id,
                t.order_id,
                t.symbol,
                f"[{side_style}]{t.side.value}[/{side_style}]",
                str(t.quantity),
                f"{t.price:,.2f}",
                f"{t.value:,.2f}",
                time_str,
            )

        console.print(table)
    except Exception as exc:
        console.print(f"[red]Error fetching trades: {exc}[/red]")


def show_oms_summary(oms_service: OmsService, console: Console) -> None:
    """Print the general OMS dashboard."""
    try:
        stats = oms_service.get_order_stats()

        table = Table(title="OMS Diagnostics Summary", header_style="bold cyan")
        table.add_column("Metric / Status", style="bold white")
        table.add_column("Active Count", justify="center")

        table.add_row("Open Orders (OPEN)", f"[yellow]{stats['open']}[/yellow]")
        table.add_row("Pending / Partially Filled", f"[yellow]{stats['pending']}[/yellow]")
        table.add_row("Completed Fills (FILLED)", f"[green]{stats['filled']}[/green]")
        table.add_row("Rejected Orders (REJECTED)", f"[red]{stats['rejected']}[/red]")
        table.add_row(
            "Cancelled Orders (CANCELLED)", f"[dim white]{stats['cancelled']}[/dim white]"
        )

        console.print(table)
    except Exception as exc:
        console.print(f"[red]Error fetching OMS stats: {exc}[/red]")


def run(args: list[str], oms_service: OmsService, console: Console) -> None:
    """Entry point for OMS related subcommands."""
    pass
