"""Integration tests for analytics.ranking."""

import pandas as pd

from analytics.ranking.ranking import RankingEngine


def test_rank_dataframe_orders_by_score() -> None:
    engine = RankingEngine()
    df = pd.DataFrame({"symbol": ["A", "B", "C"], "composite_score": [10.0, 30.0, 20.0]})
    ranked = engine.rank_dataframe(df)
    assert list(ranked["symbol"]) == ["B", "C", "A"]


def test_composite_score_bounded() -> None:
    engine = RankingEngine()
    score = engine.composite_score({"trend": 100.0, "momentum": 0.0, "volume": 50.0, "relative_strength": 50.0, "oi": 50.0})
    assert 0.0 <= score <= 100.0
