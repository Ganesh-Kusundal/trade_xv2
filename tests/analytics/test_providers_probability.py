from __future__ import annotations

import pandas as pd

from analytics.core.providers import DataFrameMarketDataProvider
from analytics.probability.probability import ProbabilityEngine


def test_dataframe_market_data_provider() -> None:
    data = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=3),
            "open": [100, 101, 102],
            "high": [101, 102, 103],
            "low": [99, 100, 101],
            "close": [100, 101, 102],
            "volume": [1000, 1100, 1200],
        }
    )
    provider = DataFrameMarketDataProvider(history={"RELIANCE": data}, prices={"RELIANCE": 102.5})

    assert provider.history("reliance").equals(data)
    assert provider.ltp("reliance") == 102.5


def test_probability_engine_scores() -> None:
    result = ProbabilityEngine().analyze(
        {
            "trend": 80,
            "momentum": 75,
            "volume": 60,
            "oi": 70,
            "relative_strength": 90,
        },
        symbol="RELIANCE",
    )

    assert result.scores["composite_score"] == 76.25
    assert result.signals == ["High Probability Long"]
