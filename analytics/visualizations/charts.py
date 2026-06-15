"""Visualization payload builders for analytics charts."""

from __future__ import annotations

import pandas as pd

from analytics.core.models import AnalysisResult


def ohlcv_chart(data: pd.DataFrame, *, symbol: str | None = None) -> dict[str, object]:
    if data.empty:
        return {"type": "ohlcv", "symbol": symbol, "data": []}
    columns = ["timestamp", "open", "high", "low", "close", "volume"]
    return {"type": "ohlcv", "symbol": symbol or data.get("symbol", pd.Series([""])).iloc[-1], "data": data[columns].to_dict("records")}


def score_chart(scores: dict[str, float]) -> dict[str, object]:
    return {"type": "score_bar", "data": [{"name": name, "value": value} for name, value in scores.items()]}


def attach_charts(result: AnalysisResult) -> AnalysisResult:
    if not result.charts and result.metrics:
        result.charts.append(score_chart({key: float(value) for key, value in result.metrics.items() if isinstance(value, int | float)}))
    return result
