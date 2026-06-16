"""Tests for analytics reports."""

from __future__ import annotations

from io import StringIO

from rich.console import Console

from analytics.core.models import AnalysisResult
from analytics.reports.reports import print_result, to_dataframe


class TestReports:
    def test_to_dataframe(self) -> None:
        result = AnalysisResult(
            name="test",
            summary="test summary",
            metrics={"a": 1, "b": 2.5},
            scores={"x": 80, "y": 60},
        )
        df = to_dataframe(result)
        assert len(df) >= 2

    def test_print_result(self) -> None:
        result = AnalysisResult(name="test", summary="test summary")
        console = Console(file=StringIO())
        print_result(result, console)
        output = console.file.getvalue()
        assert "test" in output.lower() or "test summary" in output.lower()
