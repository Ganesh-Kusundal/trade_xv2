"""Stock analytics engine."""

from __future__ import annotations

import logging

import pandas as pd

from analytics.core.feature_builder import FeatureBuilder
from analytics.core.models import AnalysisResult
from analytics.features.relative_strength import RelativeStrengthAnalyzer
from analytics.features.volume import VolumeAnalytics

logger = logging.getLogger(__name__)


class StockAnalytics:
    def __init__(self, feature_builder: FeatureBuilder | None = None) -> None:
        self._features = feature_builder or FeatureBuilder()

    def analyze(
        self,
        symbol: str,
        prices: pd.DataFrame,
        benchmark_prices: pd.DataFrame | None = None,
        benchmark_symbol: str = "NIFTY",
        sector_prices: pd.DataFrame | None = None,
    ) -> AnalysisResult:
        feature_set = self._features.build(prices, symbol=symbol)
        if feature_set.data.empty:
            return AnalysisResult(name="stock", symbol=symbol, summary="No stock price data")

        features = feature_set.data
        last = features.iloc[-1]
        relative_strength = RelativeStrengthAnalyzer().analyze(
            symbol,
            prices,
            benchmark_prices,
            benchmark_symbol,
        )
        volume_result = VolumeAnalytics().analyze(features)

        trend = str(last["trend"])
        structure = str(last["market_structure"])
        rsi_value = float(last["rsi"]) if pd.notna(last["rsi"]) else 50.0
        momentum_score = max(0.0, min(100.0, 50.0 + (rsi_value - 50.0) * 1.5))
        trend_score = float(feature_set.summary.get("trend_score", 50.0))
        composite = (
            trend_score * 0.30
            + momentum_score * 0.25
            + float(volume_result.scores.get("volume", 50.0)) * 0.20
            + float(relative_strength.scores.get("relative_strength", 50.0)) * 0.25
        )

        signals = [trend, structure, *volume_result.signals, *relative_strength.signals]
        recommendations = [
            "Use relative strength and volume confirmation before acting on breakouts.",
            "Treat pullbacks in an uptrend as higher-quality long setups than late breakouts.",
        ]
        if sector_prices is not None and not sector_prices.empty:
            recommendations.append("Compare stock relative strength against its sector before ranking.")

        return AnalysisResult(
            name="stock",
            symbol=symbol,
            summary=f"{symbol}: {trend}, {structure}, RS={relative_strength.signals[-1]}.",
            metrics={
                "trend": trend,
                "market_structure": structure,
                "rsi": rsi_value,
                "roc": float(last["roc"]) if pd.notna(last["roc"]) else 0.0,
                "momentum": float(last["momentum"]) if pd.notna(last["momentum"]) else 0.0,
                "acceleration": float(last["acceleration"]) if pd.notna(last["acceleration"]) else 0.0,
                "relative_volume": float(last["relative_volume"]) if pd.notna(last["relative_volume"]) else 0.0,
                "volume_accumulation": float(last["volume_accumulation"]) if pd.notna(last["volume_accumulation"]) else 0.0,
                "relative_strength": relative_strength.metrics,
            },
            scores={
                "trend": trend_score,
                "momentum": momentum_score,
                "volume": float(volume_result.scores.get("volume", 50.0)),
                "relative_strength": float(relative_strength.scores.get("relative_strength", 50.0)),
                "composite": composite,
            },
            signals=signals,
            charts=[
                {
                    "type": "ohlc",
                    "data": features[["timestamp", "open", "high", "low", "close", "volume"]].to_dict("records"),
                }
            ],
            recommendations=recommendations,
            raw={"features": feature_set.summary},
        )
