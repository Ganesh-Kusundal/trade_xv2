"""CLI command handler for Event Bus diagnostics."""

from __future__ import annotations

import time

from rich.console import Console
from rich.live import Live
from rich.table import Table

from cli.services.event_bus_service import EventBusService


def generate_event_table(event_bus_service: EventBusService) -> Table:
    """Generate a table representing Event Bus diagnostics."""
    table = Table(title="Event Bus Diagnostics", header_style="bold magenta")
    table.add_column("Event Category", style="bold white")
    table.add_column("Processed Count", justify="center")

    counters = event_bus_service.get_counters()
    for cat, count in counters.items():
        table.add_row(cat, str(count))

    return table


def run(args: list[str], event_bus_service: EventBusService, console: Console) -> None:
    """Entry point for events subcommand."""
    # We can run a live updating dashboard for 5 iterations, simulating events
    console.print("[yellow]Starting Event Bus monitor. Simulating events stream...[/yellow]")
    console.print("Press Ctrl+C to exit.")
    console.print()

    with Live(
        generate_event_table(event_bus_service), console=console, refresh_per_second=2
    ) as live:
        try:
            for _ in range(8):
                # Simulate a few events
                event_bus_service.simulate_event()
                live.update(generate_event_table(event_bus_service))
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass

    # Print recent logs at the end
    console.print("\n[bold white]Recent Event Bus Activity Logs:[/bold white]")
    logs = event_bus_service.get_logs(10)
    for log in logs:
        console.print(f"  {log}")
