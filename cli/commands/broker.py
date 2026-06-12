"""CLI command handler for broker operations."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from cli.services.broker_service import BrokerService


def list_brokers(broker_service: BrokerService, console: Console) -> None:
    """Print the registered brokers and their status."""
    table = Table(title="Broker Connections Status", header_style="bold cyan")
    table.add_column("Broker", style="bold white")
    table.add_column("Status", justify="center")

    statuses = broker_service.get_broker_statuses()
    for row in statuses:
        status_str = row["status"]
        if status_str == "Connected":
            style = "green"
        elif status_str == "Disconnected":
            style = "yellow"
        else:
            style = "dim white"
        table.add_row(row["broker"], f"[{style}]{status_str}[/{style}]")

    console.print(table)


def run(args: list[str], broker_service: BrokerService, console: Console) -> None:
    """Entry point for broker subcommand."""
    if not args or args[0] == "list":
        list_brokers(broker_service, console)
    elif args[0] == "use" and len(args) > 1:
        broker_name = args[1]
        try:
            broker_service.set_active_broker(broker_name)
            console.print(
                f"[green]Successfully switched active broker to [bold]{broker_name.capitalize()}[/bold].[/green]"
            )
        except ValueError as exc:
            console.print(f"[red]Error: {exc}[/red]")
    else:
        console.print("[yellow]Usage: tradex broker [list | use <broker_name>][/yellow]")
