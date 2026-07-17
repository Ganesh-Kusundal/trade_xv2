"""Core analytics output contracts and input normalization."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

OHLCV_COLUMNS = [
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "oi",
    "symbol",
    "exchange",
    "timeframe",
]


@dataclass(slots=True)
class AnalysisResult:
    """Broker-agnostic analytics result returned by every analytics engine."""

    name: str
    symbol: str | None = None
    summary: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)
    scores: dict[str, float] = field(default_factory=dict)
    signals: list[str] = field(default_factory=list)
    charts: list[dict[str, Any]] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    def add_score(self, name: str, value: float) -> None:
        self.scores[name] = _clamp_score(value)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "symbol": self.symbol,
            "summary": self.summary,
            "metrics": self.metrics,
            "scores": self.scores,
            "signals": self.signals,
            "charts": self.charts,
            "recommendations": self.recommendations,
        }


@dataclass(slots=True)
class FeatureSet:
    data: pd.DataFrame
    features: dict[str, Any]
    summary: dict[str, float]
    symbol: str | None = None
    exchange: str | None = None
    timeframe: str | None = None


def normalize_ohlcv(
    data: pd.DataFrame,
    *,
    symbol: str | None = None,
    exchange: str | None = None,
    timeframe: str | None = None,
) -> pd.DataFrame:
    """Normalize OHLCV input into TradeXV2's canonical market-data contract."""

    if data.empty:
        return pd.DataFrame(columns=OHLCV_COLUMNS)

    # Accept "datetime" as alias for "timestamp" (both names are in use across callers)
    if "timestamp" not in data.columns and "datetime" in data.columns:
        data = data.copy()
        data["timestamp"] = data["datetime"]

    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = required.difference(data.columns)
    if missing:
        raise ValueError(f"OHLCV data missing required columns: {sorted(missing)}")

    df = data.copy()
    if "timestamp" not in df:
        df["timestamp"] = pd.to_datetime(df["date"])
    else:
        df["timestamp"] = pd.to_datetime(df["timestamp"])

    for column in ["open", "high", "low", "close", "volume"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    df = df.dropna(subset=["timestamp", "open", "high", "low", "close", "volume"])
    if df.empty:
        return pd.DataFrame(columns=OHLCV_COLUMNS)

    if "oi" not in df:
        df["oi"] = 0
    else:
        df["oi"] = pd.to_numeric(df["oi"], errors="coerce").fillna(0)

    if symbol is not None:
        df["symbol"] = symbol
    elif "symbol" not in df:
        df["symbol"] = "UNKNOWN"

    if exchange is not None:
        df["exchange"] = exchange
    elif "exchange" not in df:
        df["exchange"] = "UNKNOWN"

    if timeframe is not None:
        df["timeframe"] = timeframe
    elif "timeframe" not in df:
        df["timeframe"] = "UNKNOWN"

    df = df.sort_values("timestamp").drop_duplicates("timestamp", keep="last")
    return df.loc[:, OHLCV_COLUMNS].reset_index(drop=True)


def _clamp_score(value: float) -> float:
    if pd.isna(value):
        return 0.0
    return max(0.0, min(100.0, float(value)))
