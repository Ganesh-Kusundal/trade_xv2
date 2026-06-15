from __future__ import annotations

from rich.console import Console

from cli.commands.analytics import run


def test_analytics_cli_scan_csv(tmp_path) -> None:
    path = tmp_path / "universe.csv"
    path.write_text("symbol,close,high,low,volume,relative_volume\nA,100,105,99,5000,3.0\nB,90,92,89,1000,0.8\n", encoding="utf-8")
    console = Console(record=True)

    run(["scan", "volume_spike", "--file", str(path), "--limit", "1"], broker_service=None, console=console)

    output = console.export_text()
    assert "A" in output
    assert "B" not in output


def test_analytics_cli_rank_csv(tmp_path) -> None:
    path = tmp_path / "universe.csv"
    path.write_text("symbol,trend,momentum,volume,relative_strength,oi\nA,80,90,70,85,60\nB,30,20,40,25,30\n", encoding="utf-8")
    console = Console(record=True)

    run(["rank", "--file", str(path), "--limit", "1"], broker_service=None, console=console)

    output = console.export_text()
    assert "A" in output
    assert "B" not in output
