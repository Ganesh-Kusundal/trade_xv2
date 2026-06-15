"""Tests for visualizations."""

from __future__ import annotations

import pandas as pd
import pytest

from analytics.visualizations.charts import attach_charts, ohlcv_chart, score_chart

from .helpers import prices


class TestVisualizations:
    def test_ohlcv_chart(self) -> None:
        df = prices(10)
        chart = ohlcv_chart(df)
        assert chart is not None

    def test_score_chart(self) -> None:
        result = {"momentum": 80, "volume": 60, "volatility": 40}
        chart = score_chart(result)
        assert chart is not None

    def test_attach_charts(self) -> None:
        from analytics.core.models import AnalysisResult
        result = AnalysisResult(name="test", scores={"a": 80}, metrics={"a": 80})
        attach_charts(result)
        assert len(result.charts) > 0
