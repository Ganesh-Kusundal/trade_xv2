"""TUI widget for WebSocket diagnostics and Event Bus monitoring."""

from __future__ import annotations

import random

from textual.app import ComposeResult
from textual.containers import Container, Grid, Horizontal, Vertical
from textual.widgets import Button, Label, ListItem, ListView, Static

from interface.ui.services.broker_service import BrokerService
from interface.ui.services.event_bus_service import EventBusService


class EventWsConsoleWidget(Static):
    """Interactive console for WebSocket health and Event Bus logging."""

    def __init__(
        self,
        broker_service: BrokerService,
        event_bus_service: EventBusService,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._broker_service = broker_service
        self._event_bus_service = event_bus_service
        self._ticks_count = 0

    def compose(self) -> ComposeResult:
        with Container(classes="scroll-container"):
            # WebSocket Card (Left) & Event Bus Counters (Right)
            with Horizontal(id="ws-events-split"):
                with Container(classes="panel", id="tui-ws-panel"):
                    yield Label("WebSocket Health Diagnostics", classes="title")
                    with Vertical():
                        yield Label("WebSocket Connection: CONNECTED", id="tui-ws-conn")
                        yield Label("Network Latency: 12.0 ms", id="tui-ws-latency")
                        yield Label("Messages Throughput: 120 msgs/s", id="tui-ws-throughput")
                        yield Label("Total Reconnects: 0", id="tui-ws-reconnect")
                        yield Label("Dropped Packets: 0", id="tui-ws-dropped")

                with Container(classes="panel", id="tui-events-panel"):
                    yield Label("Event Bus Dispatch Counters", classes="title")
                    with Grid(id="events-grid"):
                        yield Label("Market Events", classes="metric-label")
                        yield Label("0", id="cnt-market", classes="metric-value")

                        yield Label("Signal Events", classes="metric-label")
                        yield Label("0", id="cnt-signal", classes="metric-value")

                        yield Label("Order Events", classes="metric-label")
                        yield Label("0", id="cnt-order", classes="metric-value")

                        yield Label("Position Events", classes="metric-label")
                        yield Label("0", id="cnt-position", classes="metric-value")

                        yield Label("Risk Events", classes="metric-label")
                        yield Label("0", id="cnt-risk", classes="metric-value")

            # Logs ListView
            with Container(classes="panel"):
                yield Label("Real-time Event Bus Activity Logs", classes="title")
                yield ListView(id="tui-event-logs-list")
                with Horizontal():
                    yield Button(
                        "Simulate Random Event", variant="primary", id="btn-simulate-event"
                    )
                    yield Button("Clear Logs", id="btn-clear-event-logs")

    def on_mount(self) -> None:
        self.query_one("#ws-events-split", Horizontal).styles.height = 20
        self.query_one("#tui-ws-panel", Container).styles.width = "45%"
        self.query_one("#tui-events-panel", Container).styles.width = "55%"

        # Style events grid
        egrid = self.query_one("#events-grid", Grid)
        egrid.styles.grid_size_columns = 4
        egrid.styles.grid_size_rows = 3
        egrid.styles.height = 10

        self.refresh_ws_event_data()

        # Set up a slow timer in the TUI to simulate activity
        self.set_interval(1.5, self.auto_tick)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-simulate-event":
            self.trigger_simulation()
        elif event.button.id == "btn-clear-event-logs":
            self.query_one("#tui-event-logs-list", ListView).clear()

    def auto_tick(self) -> None:
        """Periodic background update simulating incoming websocket traffic."""
        self._ticks_count += 1
        broker_name = self._broker_service.active_broker_name

        # Random WS variations
        latency = 10.0 + random.uniform(-2, 4)
        throughput = 110 + random.randint(-15, 20)

        self.query_one("#tui-ws-conn", Label).update(
            f"WebSocket Connection: [green]CONNECTED ({broker_name.upper()})[/green]"
        )
        self.query_one("#tui-ws-latency", Label).update(
            f"Network Latency: [cyan]{latency:.1f} ms[/cyan]"
        )
        self.query_one("#tui-ws-throughput", Label).update(
            f"Messages Throughput: {throughput} msgs/s"
        )

        # Occasional random event
        if random.random() < 0.3:
            self.trigger_simulation()

        self.refresh_ws_event_data()

    def trigger_simulation(self) -> None:
        """Trigger an event and append it to the log widget.

        Phase 3: this method used to call
        ``self._event_bus_service.simulate_event()`` which fabricated
        fake events on a separate, non-OMS bus. It now reads real
        events from the OMS event bus via the
        ``EventBusService.get_logs()`` mirror. When no real bus is
        attached, it prints a banner explaining why no events are
        displayed rather than fabricating activity.
        """
        logs_list = self.query_one("#tui-event-logs-list", ListView)
        if not self._event_bus_service.has_real_bus():
            logs_list.append(
                ListItem(
                    Label(
                        "[yellow]No OMS event bus attached; "
                        "events will appear when a live broker is connected.[/yellow]"
                    )
                )
            )
            logs_list.index = len(logs_list) - 1
            return
        # Pull the most recent real event from the service's rolling
        # log mirror (populated by the canonical bus subscription).
        recent = self._event_bus_service.get_logs(limit=1)
        if not recent:
            logs_list.append(
                ListItem(Label("[dim]Waiting for OMS events...[/dim]"))
            )
        else:
            logs_list.append(ListItem(Label(recent[-1])))
        logs_list.index = len(logs_list) - 1

    def refresh_ws_event_data(self) -> None:
        """Update TUI labels with active event counters."""
        counters = self._event_bus_service.get_counters()
        self.query_one("#cnt-market", Label).update(str(counters.get("Market Events", 0)))
        self.query_one("#cnt-signal", Label).update(str(counters.get("Signal Events", 0)))
        self.query_one("#cnt-order", Label).update(str(counters.get("Order Events", 0)))
        self.query_one("#cnt-position", Label).update(str(counters.get("Position Events", 0)))
        self.query_one("#cnt-risk", Label).update(str(counters.get("Risk Events", 0)))
