"""Integration tests for analytics.reports."""

import pandas as pd

from analytics.core.models import AnalysisResult
from analytics.reports.reports import to_dataframe


def test_to_dataframe_flattens_metrics() -> None:
    result = AnalysisResult(name="test", summary="ok", metrics={"trades": 3}, scores={"pnl": 12.5})
    df = to_dataframe(result)
    assert len(df) == 2
    assert set(df["section"]) == {"metric", "score"}
