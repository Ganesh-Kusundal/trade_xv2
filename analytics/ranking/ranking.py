"""Ranking engine."""

from __future__ import annotations

import logging

import pandas as pd

from analytics.core.models import AnalysisResult

logger = logging.getLogger(__name__)


class RankingFacade:
    def __init__(self, engine: RankingEngine) -> None:
        self._engine = engine

    def top_stocks(self, data: pd.DataFrame | None = None, *, limit: int = 10) -> AnalysisResult:
        return self._result("top_stocks", self._engine.top_stocks(data, limit) if data is not None else [])

    def top_futures(self, data: pd.DataFrame | None = None, *, limit: int = 10) -> AnalysisResult:
        return self._result("top_futures", self._engine.top_futures(data, limit) if data is not None else [])

    def top_options(self, data: pd.DataFrame | None = None, *, limit: int = 10) -> AnalysisResult:
        return self._result("top_options", self._engine.top_options(data, limit) if data is not None else [])

    def top_momentum(self, data: pd.DataFrame | None = None, *, limit: int = 10) -> AnalysisResult:
        return self._result("top_momentum", self._engine.top_momentum(data, limit) if data is not None else [])

    def top_relative_strength(self, data: pd.DataFrame | None = None, *, limit: int = 10) -> AnalysisResult:
        return self._result("top_relative_strength", self._engine.top_relative_strength(data, limit) if data is not None else [])

    def _result(self, name: str, records: list[dict[str, object]]) -> AnalysisResult:
        return AnalysisResult(
            name=name,
            summary="Ranking is ready. Pass a universe DataFrame to return ranked instruments." if not records else f"Ranked {len(records)} instruments.",
            metrics={"count": len(records)},
            charts=[{"type": "ranking", "ranking": name, "data": records}],
        )


class RankingEngine:
    def __init__(self, weights: dict[str, float] | None = None) -> None:
        self.weights = weights or {
            "trend": 0.25,
            "momentum": 0.25,
            "volume": 0.15,
            "relative_strength": 0.20,
            "oi": 0.15,
        }
        self._validate_weights(self.weights)

    @staticmethod
    def _validate_weights(weights: dict[str, float]) -> None:
        if not weights:
            return
        total = sum(weights.values())
        for k, v in weights.items():
            if v < 0:
                raise ValueError(f"Weight for '{k}' must be non-negative, got {v}")
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"Weights must sum to 1.0, got {total}")

    def composite_score(self, metrics: dict[str, float]) -> float:
        score = 0.0
        weight_total = 0.0
        for name, weight in self.weights.items():
            raw = metrics.get(name, 50.0)
            try:
                value = float(raw)
            except (TypeError, ValueError):
                value = 50.0
            score += value * weight
            weight_total += weight
        return max(0.0, min(100.0, score / weight_total if weight_total else 50.0))

    def rank_dataframe(self, data: pd.DataFrame, *, score_column: str = "composite_score", ascending: bool = False) -> pd.DataFrame:
        if data.empty:
            return data.copy()
        ranked = data.copy()
        if score_column not in ranked:
            metrics = ranked.to_dict("records")
            ranked[score_column] = [self.composite_score(item) for item in metrics]
        columns = [score_column, "symbol"] if "symbol" in ranked.columns else [score_column]
        order = [ascending, True] if "symbol" in ranked.columns else [ascending]
        return ranked.sort_values(columns, ascending=order, kind="mergesort").reset_index(drop=True)

    def top_stocks(self, data: pd.DataFrame, limit: int = 10) -> list[dict[str, object]]:
        return self.rank_dataframe(data, score_column="composite_score").head(limit).to_dict("records")

    def top_futures(self, data: pd.DataFrame, limit: int = 10) -> list[dict[str, object]]:
        return self.rank_dataframe(data, score_column="future_strength").head(limit).to_dict("records")

    def top_options(self, data: pd.DataFrame, limit: int = 10) -> list[dict[str, object]]:
        return self.rank_dataframe(data, score_column="composite").head(limit).to_dict("records")

    def top_momentum(self, data: pd.DataFrame, limit: int = 10) -> list[dict[str, object]]:
        ranked = data.copy()
        if "momentum" not in ranked:
            ranked["momentum"] = ranked.get("roc", 0)
        columns = ["momentum", "symbol"] if "symbol" in ranked.columns else ["momentum"]
        ascending = [False, True] if "symbol" in ranked.columns else [False]
        return ranked.sort_values(columns, ascending=ascending, kind="mergesort").head(limit).to_dict("records")

    def top_relative_strength(self, data: pd.DataFrame, limit: int = 10) -> list[dict[str, object]]:
        ranked = data.copy()
        if "relative_strength" not in ranked:
            ranked["relative_strength"] = ranked.get("composite_score", 50)
        columns = ["relative_strength", "symbol"] if "symbol" in ranked.columns else ["relative_strength"]
        ascending = [False, True] if "symbol" in ranked.columns else [False]
        return ranked.sort_values(columns, ascending=ascending, kind="mergesort").head(limit).to_dict("records")

    def analyze(self, data: pd.DataFrame, *, name: str = "ranking") -> AnalysisResult:
        ranked = self.rank_dataframe(data)
        top_score = float(ranked.iloc[0]["composite_score"]) if not ranked.empty else 0.0
        logger.debug("Ranked %d instruments, top score: %.1f", len(ranked), top_score)
        return AnalysisResult(
            name=name,
            summary=f"Ranked {len(ranked)} instruments.",
            metrics={"count": len(ranked)},
            scores={"top_score": top_score},
            charts=[{"type": "ranking", "data": ranked.to_dict("records")}],
        )
