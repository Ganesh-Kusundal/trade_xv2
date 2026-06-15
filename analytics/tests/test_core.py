"""Tests for analytics core models."""

from __future__ import annotations

import pandas as pd
import pytest

from analytics.core.models import AnalysisResult, _clamp_score, normalize_ohlcv

from .helpers import prices


class TestAnalysisResult:
    def test_add_score_clamps(self) -> None:
        r = AnalysisResult(name="t")
        r.add_score("x", 150)
        assert r.scores["x"] == 100.0
        r.add_score("y", -10)
        assert r.scores["y"] == 0.0

    def test_to_dict(self) -> None:
        r = AnalysisResult(name="t", summary="s", metrics={"a": 1})
        d = r.to_dict()
        assert d["name"] == "t"
        assert d["metrics"]["a"] == 1

    def test_charts_list(self) -> None:
        r = AnalysisResult(name="t")
        assert r.charts == []


class TestNormalizeOhlcv:
    def test_raises_on_missing_columns(self) -> None:
        df = pd.DataFrame({"close": [1, 2]})
        with pytest.raises(ValueError, match="missing required columns"):
            normalize_ohlcv(df)

    def test_preserves_existing(self) -> None:
        df = prices(5)
        result = normalize_ohlcv(df)
        assert len(result) == 5


def test_clamp_score() -> None:
    assert _clamp_score(50) == 50
    assert _clamp_score(150) == 100
    assert _clamp_score(-10) == 0
