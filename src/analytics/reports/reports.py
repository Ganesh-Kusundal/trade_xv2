"""Analytics report helpers."""

from __future__ import annotations

from typing import Any

import pandas as pd
from rich.console import Console
from rich.table import Table

from analytics.core.models import AnalysisResult


def print_result(result: AnalysisResult, console: Console) -> None:
    title = result.symbol or result.name
    table = Table(title=f"Analytics: {title}", header_style="bold cyan")
    table.add_column("Field", style="bold white")
    table.add_column("Value")
    table.add_row("Summary", result.summary)
    for name, value in sorted(result.metrics.items()):
        table.add_row(name, _format_value(value))
    for name, value in sorted(result.scores.items()):
        table.add_row(f"score.{name}", f"{value:.2f}")
    table.add_row("signals", ", ".join(result.signals) if result.signals else "-")
    console.print(table)


def to_dataframe(result: AnalysisResult) -> pd.DataFrame:
    rows = []
    for section, values in (("metric", result.metrics), ("score", result.scores)):
        for name, value in values.items():
            rows.append({"section": section, "name": name, "value": value})
    return pd.DataFrame(rows)


def _format_value(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.4f}"
    if isinstance(value, list | dict):
        return str(value)[:240]
    return str(value)
