"""CLI command handler for Event Bus diagnostics.

Phase 3: the previous implementation called ``simulate_event()`` which
fabricated random events on a separate, non-OMS event bus. That was a
silent safety bug — operators saw fake activity. The new implementation
prints a banner when no canonical OMS bus is attached and tails real
events from the OMS ``TradingContext.event_bus`` when one is available.
"""

from __future__ import annotations

import time

from rich.console import Console
from rich.live import Live
from rich.table import Table

from interface.ui.services.event_bus_service import EventBusService


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
    """Entry point for events subcommand.

    Phase 3: when the service is attached to the canonical OMS bus,
    tail real events. When it is not (e.g. a unit-test path or a
    command run without a live broker), print an explanatory banner
    and the rolling log of any captured events rather than fabricate
    activity.
    """
    if not event_bus_service.has_real_bus():
        console.print(
            "[yellow]No canonical OMS event bus attached to this CLI session.[/yellow]\n"
            "[dim]This usually means the OMS TradingContext is unavailable "
            "(no live broker credentials, or the runtime is in safe mode).\n"
            "Run `tradex broker` to verify the active broker connection, "
            "or `tradex doctor` for the readiness report.[/dim]"
        )
        return

    console.print("[bold]Event Bus monitor — real OMS events[/bold]")
    console.print("Press Ctrl+C to exit.")
    console.print()

    with Live(
        generate_event_table(event_bus_service), console=console, refresh_per_second=2
    ) as live:
        try:
            for _ in range(8):
                # No fabrication — refresh the counters from real events
                # captured by the subscriber registered in EventBusService.
                live.update(generate_event_table(event_bus_service))
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass

    console.print("\n[bold white]Recent Event Bus Activity Logs:[/bold white]")
    logs = event_bus_service.get_logs(10)
    if not logs:
        console.print("  [dim](no events captured in this session)[/dim]")
        return
    for log in logs:
        console.print(f"  {log}")
