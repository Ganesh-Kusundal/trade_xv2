"""Determinism tests for the ranking engine."""

from __future__ import annotations

import pandas as pd

from analytics.ranking.ranking import RankingEngine


def _ranking_data_with_ties(n: int = 10) -> pd.DataFrame:
    """Create a DataFrame with tied composite scores across symbols."""
    return pd.DataFrame({
        "symbol": [f"SYM{i:02d}" for i in range(n)],
        "trend": [50.0] * n,
        "momentum": [50.0] * n,
        "volume": [50.0] * n,
        "relative_strength": [50.0] * n,
        "oi": [50.0] * n,
    })


class TestRankingEngineDeterminism:
    def test_rank_dataframe_stable_with_ties(self) -> None:
        data = _ranking_data_with_ties(10)
        engine = RankingEngine()
        ranked = engine.rank_dataframe(data)
        symbols = ranked["symbol"].tolist()
        assert symbols == sorted(symbols)

        for _ in range(20):
            rerun = engine.rank_dataframe(data)
            assert rerun["symbol"].tolist() == symbols

    def test_top_stocks_stable_with_ties(self) -> None:
        data = _ranking_data_with_ties(10)
        engine = RankingEngine()
        records = engine.top_stocks(data, limit=5)
        symbols = [r["symbol"] for r in records]
        assert symbols == sorted(symbols)

        for _ in range(20):
            rerun = engine.top_stocks(data, limit=5)
            assert [r["symbol"] for r in rerun] == symbols

    def test_top_momentum_stable_with_ties(self) -> None:
        data = _ranking_data_with_ties(10)
        data["roc"] = [1.0] * len(data)
        engine = RankingEngine()
        records = engine.top_momentum(data, limit=5)
        symbols = [r["symbol"] for r in records]
        assert symbols == sorted(symbols)

        for _ in range(20):
            rerun = engine.top_momentum(data, limit=5)
            assert [r["symbol"] for r in rerun] == symbols

    def test_top_relative_strength_stable_with_ties(self) -> None:
        data = _ranking_data_with_ties(10)
        engine = RankingEngine()
        records = engine.top_relative_strength(data, limit=5)
        symbols = [r["symbol"] for r in records]
        assert symbols == sorted(symbols)

        for _ in range(20):
            rerun = engine.top_relative_strength(data, limit=5)
            assert [r["symbol"] for r in rerun] == symbols

    def test_top_futures_stable_with_ties(self) -> None:
        data = pd.DataFrame({
            "symbol": [f"SYM{i:02d}" for i in range(10)],
            "future_strength": [75.0] * 10,
        })
        engine = RankingEngine()
        records = engine.top_futures(data, limit=5)
        symbols = [r["symbol"] for r in records]
        assert symbols == sorted(symbols)

    def test_top_options_stable_with_ties(self) -> None:
        data = pd.DataFrame({
            "symbol": [f"SYM{i:02d}" for i in range(10)],
            "composite": [75.0] * 10,
        })
        engine = RankingEngine()
        records = engine.top_options(data, limit=5)
        symbols = [r["symbol"] for r in records]
        assert symbols == sorted(symbols)
