"""TUI widget for executing load tests and displaying performance metrics."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Button, DataTable, Label, Select, Static

from cli.load_testing.runner import LoadTestRunner
from cli.services.broker_service import BrokerService


class PerformanceConsoleWidget(Static):
    """Performance load-testing dashboard allowing developers to measure API throughput and latency."""

    def __init__(self, broker_service: BrokerService, **kwargs):
        super().__init__(**kwargs)
        self._broker_service = broker_service
        self._test_running = False

    def compose(self) -> ComposeResult:
        with Container(classes="panel"):
            yield Label("API Performance Load Tester", classes="title")
            yield Label(
                "Run stress tests against selected broker endpoints to evaluate "
                "concurrency handling, response latency, and rate-limiting thresholds."
            )

            with Horizontal(id="perf-options-row"):
                yield Select(
                    [
                        ("Quotes Endpoint", "quotes"),
                        ("Historical Candles", "historical"),
                        ("Option Chain Grid", "option-chain"),
                        ("Websocket Client", "websocket"),
                    ],
                    value="quotes",
                    id="perf-test-select",
                )
                yield Button("Execute Performance Test", variant="primary", id="btn-run-perf")

            yield Label("Idle", id="lbl-perf-status")
            yield DataTable(id="perf-results-table")

    def on_mount(self) -> None:
        self.query_one("#perf-options-row", Horizontal).styles.height = 5
        self.query_one("#perf-options-row", Horizontal).styles.margin = (1, 0)
        status_lbl = self.query_one("#lbl-perf-status", Label)
        status_lbl.styles.text_style = "bold"
        status_lbl.styles.color = "yellow"

        table = self.query_one("#perf-results-table", DataTable)
        table.add_columns("Performance Metric", "Value")
        table.styles.height = 12
        table.styles.margin = (1, 0)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-run-perf" and not self._test_running:
            await self.execute_load_test()

    async def execute_load_test(self) -> None:
        """Run the selected load test asynchronously and update metrics."""
        self._test_running = True
        btn = self.query_one("#btn-run-perf", Button)
        btn.disabled = True

        category = self.query_one("#perf-test-select", Select).value
        status_lbl = self.query_one("#lbl-perf-status", Label)
        status_lbl.update("[yellow]Running load test. Please wait...[/yellow]")

        table = self.query_one("#perf-results-table", DataTable)
        table.clear()

        runner = LoadTestRunner(self._broker_service)
        try:
            # Run test with 3.0s duration
            metrics = await runner.run_test(category, duration_seconds=3.0, concurrency=5)

            status_lbl.update("[green]Test completed successfully![/green]")
            table.add_row("Execution Duration", f"{metrics['duration']:.2f} seconds")
            table.add_row("Total Requests Sent", f"{metrics['requests_sent']:,}")
            table.add_row("Success Count", f"{metrics['success_count']:,}")
            table.add_row("Failure Count", f"{metrics['failure_count']:,}")
            table.add_row("Rate Limit Hits (429)", f"{metrics['rate_limit_hits']:,}")
            table.add_row("Throughput (RPS)", f"{metrics['rps']:.1f} reqs/sec")
            table.add_row("Average Latency", f"{metrics['avg_latency_ms']:.1f} ms")
            table.add_row(
                "Min / Max Latency",
                f"{metrics['min_latency_ms']:.1f} ms / {metrics['max_latency_ms']:.1f} ms",
            )

        except Exception as exc:
            status_lbl.update(f"[red]Error during load test: {exc}[/red]")
        finally:
            self._test_running = False
            btn.disabled = False
