"""CLI command handler for running load tests."""

from __future__ import annotations

import asyncio

from rich.console import Console
from rich.table import Table

from interface.ui.load_testing.runner import LoadTestRunner
from interface.ui.services.broker_service import BrokerService


async def execute_load_test(
    category: str,
    broker_service: BrokerService,
    console: Console,
) -> None:
    """Run an async load test and print metrics."""
    console.print(
        f"Initializing load test for endpoint category: [bold yellow]{category}[/bold yellow]..."
    )
    console.print("Running concurrent async requests for 3 seconds...")
    console.print()

    runner = LoadTestRunner(broker_service)
    try:
        metrics = await runner.run_test(category, duration_seconds=3.0, concurrency=5)

        table = Table(title=f"Load Test Results: {category.upper()}", header_style="bold red")
        table.add_column("Metric Description", style="bold white")
        table.add_column("Value / Measurement", justify="right")

        table.add_row("Execution Duration", f"{metrics['duration']:.2f} seconds")
        table.add_row("Total Requests Sent", f"{metrics['requests_sent']:,}")
        table.add_row("Successful Requests", f"[green]{metrics['success_count']:,}[/green]")
        table.add_row(
            "Failed Requests",
            f"[red]{metrics['failure_count']:,}[/red]" if metrics["failure_count"] > 0 else "0",
        )
        table.add_row(
            "Rate Limit Hits (429)",
            f"[yellow]{metrics['rate_limit_hits']:,}[/yellow]"
            if metrics["rate_limit_hits"] > 0
            else "0",
        )
        table.add_row("Throughput (RPS)", f"[bold green]{metrics['rps']:.1f} reqs/sec[/bold green]")
        table.add_row("Average Latency", f"{metrics['avg_latency_ms']:.1f} ms")
        table.add_row("Minimum Latency", f"{metrics['min_latency_ms']:.1f} ms")
        table.add_row("Maximum Latency", f"{metrics['max_latency_ms']:.1f} ms")

        console.print(table)
    except Exception as exc:
        console.print(f"[red]Load testing failed: {exc}[/red]")


def run(args: list[str], broker_service: BrokerService, console: Console) -> None:
    """Entry point for load-test subcommand."""
    if not args:
        console.print(
            "[yellow]Usage: tradex load-test [historical | quotes | option-chain | websocket][/yellow]"
        )
        return

    category = args[0].lower()
    if category not in ("historical", "quotes", "option-chain", "websocket"):
        console.print(f"[red]Error: Invalid load test category '{category}'.[/red]")
        console.print(
            "[yellow]Available categories: historical, quotes, option-chain, websocket[/yellow]"
        )
        return

    # Run the async execution loop
    asyncio.run(execute_load_test(category, broker_service, console))
