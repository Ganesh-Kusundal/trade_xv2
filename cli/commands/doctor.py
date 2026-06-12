"""CLI command handler for the doctor connectivity checks."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from cli.diagnostics.doctor import DoctorDiagnostics
from cli.services.broker_service import BrokerService


def run_doctor(broker_service: BrokerService, console: Console) -> None:
    """Execute all connection and diagnostics checks."""
    console.print(
        f"Running connectivity diagnostics on active broker: [bold yellow]{broker_service.active_broker_name.upper()}[/bold yellow]"
    )
    console.print()

    doctor = DoctorDiagnostics(broker_service)
    results = doctor.run_all_checks()

    table = Table(title="System Doctor Diagnostics Report", header_style="bold yellow")
    table.add_column("Diagnostics Check Item", style="bold white")
    table.add_column("Status", justify="center")
    table.add_column("Detailed Observation & Result Info", style="dim white")

    for name, status, details in results:
        if status == "PASS":
            status_str = "[green]PASS[/green]"
        elif status == "WARNING":
            status_str = "[yellow]WARN[/yellow]"
        else:
            status_str = "[red]FAIL[/red]"

        table.add_row(name, status_str, details)

    console.print(table)


def run(args: list[str], broker_service: BrokerService, console: Console) -> None:
    """Entry point for doctor subcommand."""
    run_doctor(broker_service, console)
