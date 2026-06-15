from __future__ import annotations

from rich.console import Console

from cli.commands.analytics import run


def test_analytics_cli_usage() -> None:
    console = Console(record=True)

    run([], broker_service=None, console=console)

    output = console.export_text()
    assert "Usage: tradex analytics" in output
