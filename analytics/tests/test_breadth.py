"""Tests for market breadth."""

from __future__ import annotations

import pandas as pd

from analytics.market_breadth.breadth import BreadthAnalytics


class TestBreadth:
    def test_basic(self) -> None:
        df = pd.DataFrame({
            "symbol": ["A", "B", "C"],
            "close": [100, 200, 300],
            "prev_close": [95, 195, 310],
        })
        result = BreadthAnalytics().analyze(df)
        assert result.name == "breadth"
