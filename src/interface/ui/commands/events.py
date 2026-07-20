"""CLI command handler for Event Bus diagnostics.

Phase 3: the previous implementation called ``simulate_event()`` which
fabricated random events on a separate, non-OMS event bus. That was a
silent safety bug — operators saw fake activity. The new implementation
prints a banner when no canonical OMS bus is attached and tails real
events from the OMS ``TradingContext.event_bus`` when one is available.
"""

from __future__ import annotations

import contextlib
import time
from typing import TYPE_CHECKING

from rich.console import Console
from rich.live import Live
from rich.table import Table

if TYPE_CHECKING:
    from infrastructure.event_bus import EventBus


class EventBusService:
    """Read-only mirror over the canonical OMS EventBus."""

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self.event_bus = event_bus
        self._counters: dict[str, int] = {
            "MARKET": 0,
            "ORDER": 0,
            "POSITION": 0,
            "RISK": 0,
        }
        self._logs: list[str] = []
        self._max_logs = 500
        if event_bus is not None:
            with contextlib.suppress(AttributeError):
                event_bus.subscribe_all(self._on_event)

    def _on_event(self, event) -> None:
        event_type = getattr(event, "event_type", "")
        category = self._categorise(event_type)
        self._counters[category] = self._counters.get(category, 0) + 1
        line = self._format(event)
        self._logs.append(line)
        if len(self._logs) > self._max_logs:
            self._logs.pop(0)

    @staticmethod
    def _categorise(event_type: str) -> str:
        upper = event_type.upper()
        if "TICK" in upper or "QUOTE" in upper or "DEPTH" in upper or "MARKET" in upper:
            return "MARKET"
        if "ORDER" in upper:
            return "ORDER"
        if "POSITION" in upper or "TRADE" in upper:
            return "POSITION"
        if "RISK" in upper:
            return "RISK"
        return "MARKET"

    @staticmethod
    def _format(event) -> str:
        event_type = getattr(event, "event_type", "")
        symbol = getattr(event, "symbol", "") or ""
        source = getattr(event, "source", "") or ""
        ts = getattr(event, "timestamp", None)
        ts_str = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
        payload = getattr(event, "payload", {}) or {}
        order = payload.get("order")
        trade = payload.get("trade")
        if order is not None:
            detail = (
                f"{getattr(order, 'symbol', symbol)} "
                f"{getattr(order, 'side', '')} "
                f"{getattr(order, 'quantity', '')} @ "
                f"{getattr(order, 'price', '')} "
                f"status={getattr(order, 'status', '')}"
            )
            return f"[ORDER] {ts_str} {event_type} {detail}"
        if trade is not None:
            detail = (
                f"{getattr(trade, 'symbol', symbol)} "
                f"{getattr(trade, 'side', '')} "
                f"qty={getattr(trade, 'quantity', '')} "
                f"@ {getattr(trade, 'price', '')}"
            )
            return f"[POSITION] {ts_str} {event_type} {detail}"
        return f"[{source or 'EVENT'}] {ts_str} {event_type} symbol={symbol}"

    def get_counters(self) -> dict[str, int]:
        return dict(self._counters)

    def get_logs(self, limit: int = 50) -> list[str]:
        return self._logs[-limit:]

    def has_real_bus(self) -> bool:
        return self.event_bus is not None


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
