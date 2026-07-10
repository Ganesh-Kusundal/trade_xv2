"""Relative-strength analytics."""

from __future__ import annotations

import logging

import pandas as pd

from analytics.core.models import AnalysisResult, normalize_ohlcv

logger = logging.getLogger(__name__)


class RelativeStrengthAnalyzer:
    def __init__(self, period: int = 20) -> None:
        if period < 2:
            raise ValueError("period must be >= 2")
        self._period = period

    def analyze(
        self,
        symbol: str,
        prices: pd.DataFrame,
        benchmark_prices: pd.DataFrame | None = None,
        benchmark_symbol: str = "NIFTY",
    ) -> AnalysisResult:
        asset = normalize_ohlcv(prices, symbol=symbol)
        if asset.empty:
            return AnalysisResult(name="relative_strength", symbol=symbol, summary="No price data")

        if benchmark_prices is None or benchmark_prices.empty:
            return AnalysisResult(
                name="relative_strength",
                symbol=symbol,
                summary="Relative strength is neutral because no benchmark was supplied.",
                metrics={"benchmark": benchmark_symbol, "period": self._period},
                scores={"relative_strength": 50.0},
                signals=["Neutral"],
            )

        benchmark = normalize_ohlcv(benchmark_prices, symbol=benchmark_symbol)
        aligned = self._align(asset, benchmark)
        if aligned.empty or len(aligned) < self._period + 1:
            logger.debug("RS: insufficient aligned data for %s (%d bars)", symbol, len(aligned))
            return AnalysisResult(
                name="relative_strength",
                symbol=symbol,
                summary="Insufficient aligned data for relative strength.",
                metrics={"benchmark": benchmark_symbol, "aligned_bars": len(aligned)},
                scores={"relative_strength": 50.0},
                signals=["Neutral"],
            )

        ratio = aligned["asset_close"] / aligned["benchmark_close"]
        ratio_return = ratio.pct_change(periods=self._period).iloc[-1] * 100
        score = 50.0 + ratio_return * 2.5
        score = max(0.0, min(100.0, score))
        regime = "Strong" if score >= 60.0 else "Weak" if score <= 40.0 else "Neutral"
        return AnalysisResult(
            name="relative_strength",
            symbol=symbol,
            summary=f"{regime} relative strength against {benchmark_symbol}.",
            metrics={
                "benchmark": benchmark_symbol,
                "period": self._period,
                "ratio_return_pct": float(ratio_return),
                "aligned_bars": len(aligned),
            },
            scores={"relative_strength": float(score)},
            signals=[regime],
            recommendations=[
                f"Prefer long setups in {symbol} while relative strength remains Strong.",
                "Avoid fresh longs while relative strength remains Weak.",
            ],
        )

    def _align(self, asset: pd.DataFrame, benchmark: pd.DataFrame) -> pd.DataFrame:
        left = asset[["timestamp", "close"]].rename(columns={"close": "asset_close"})
        right = benchmark[["timestamp", "close"]].rename(columns={"close": "benchmark_close"})
        aligned = left.merge(right, on="timestamp", how="inner")
        aligned = aligned.dropna(subset=["asset_close", "benchmark_close"])
        return aligned[aligned["asset_close"] > 0][aligned["benchmark_close"] > 0]
