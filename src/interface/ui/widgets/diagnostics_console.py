"""TUI widget for running doctor connectivity checks."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Button, DataTable, Label, Static

from interface.ui.diagnostics.doctor import DoctorDiagnostics
from interface.ui.services.broker_service import BrokerService


class DiagnosticsConsoleWidget(Static):
    """Diagnostics panel allowing developers to execute full system connectivity checks."""

    def __init__(self, broker_service: BrokerService, **kwargs):
        super().__init__(**kwargs)
        self._broker_service = broker_service

    def compose(self) -> ComposeResult:
        with Container(classes="panel"):
            yield Label("Broker Connectivity Doctor & Diagnostics", classes="title")
            yield Label(
                "Run automated tests against the broker endpoints to verify authentication, "
                "data feeds, OMS routing, and portfolio sync states."
            )

            yield DataTable(id="doctor-results-table")

            with Horizontal():
                yield Button("Run Diagnostics Suite", variant="primary", id="btn-run-doctor")

    def on_mount(self) -> None:
        table = self.query_one("#doctor-results-table", DataTable)
        table.add_columns("Diagnostics Check Item", "Status", "Observation & Details")
        table.styles.height = 15
        table.styles.margin = (1, 0)

        self.execute_diagnostics()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-run-doctor":
            self.execute_diagnostics()

    def execute_diagnostics(self) -> None:
        """Run all diagnostics checks and populate table."""
        table = self.query_one("#doctor-results-table", DataTable)
        table.clear()

        doctor = DoctorDiagnostics(self._broker_service)
        results = doctor.run_all_checks()

        for name, status, details in results:
            if status == "PASS":
                status_txt = Text("PASS", style="bold green")
            elif status == "WARNING":
                status_txt = Text("WARN", style="bold yellow")
            else:
                status_txt = Text("FAIL", style="bold red")

            table.add_row(name, status_txt, details)


pre_execution = True
