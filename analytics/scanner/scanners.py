"""Concrete scanner implementations.

Each scanner:
1. Runs FeaturePipeline on the universe
2. Scores stocks on specific criteria
3. Returns top candidates

P5.1 Performance Optimization: Removed unnecessary DataFrame .copy() calls.
All scoring methods now mutate in-place on isolated DataFrames returned by
pipeline or groupby operations, eliminating redundant memory allocations.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import pandas as pd

from analytics.pipeline.pipeline import FeaturePipeline
from analytics.scanner.models import BaseScanner, ScanResult


def _build_momentum_pipeline() -> FeaturePipeline:
    from analytics.pipeline import ROC, RSI, SMA, Momentum, RelativeVolume, Trend
    return (
        FeaturePipeline()
        .add(RSI(period=14))
        .add(ROC(period=5))
        .add(Momentum(period=5))
        .add(Trend(fast_period=10, slow_period=50))
        .add(RelativeVolume(period=20))
        .add(SMA(period=20))
    )


def _build_volume_pipeline() -> FeaturePipeline:
    from analytics.pipeline import ATR, RSI, VWAP, RelativeVolume, VolumeSMA
    return (
        FeaturePipeline()
        .add(RelativeVolume(period=20))
        .add(VolumeSMA(period=20))
        .add(ATR(period=14))
        .add(VWAP())
        .add(RSI(period=14))
    )


def _build_rs_pipeline() -> FeaturePipeline:
    from analytics.pipeline import ATR, ROC, RSI, SMA, Momentum, Trend
    return (
        FeaturePipeline()
        .add(RSI(period=14))
        .add(SMA(period=20))
        .add(Trend(fast_period=10, slow_period=50))
        .add(ROC(period=5))
        .add(Momentum(period=5))
        .add(ATR(period=14))
    )


def _build_breakout_pipeline() -> FeaturePipeline:
    from analytics.pipeline import ATR, RSI, VWAP, BollingerBands, RelativeVolume, SwingHighLow
    return (
        FeaturePipeline()
        .add(ATR(period=14))
        .add(VWAP())
        .add(RSI(period=14))
        .add(RelativeVolume(period=20))
        .add(BollingerBands(period=20))
        .add(SwingHighLow(lookback=5))
    )


# ---------------------------------------------------------------------------
# Momentum Scanner
# ---------------------------------------------------------------------------


@dataclass
class MomentumScanner(BaseScanner):
    """Finds stocks with strong momentum (RSI, ROC, trend alignment)."""

    name: str = "momentum"
    top_n: int = 10
    pipeline: FeaturePipeline = field(default_factory=_build_momentum_pipeline)

    def scan(self, universe: pd.DataFrame) -> ScanResult:
        if universe.empty:
            return ScanResult(scanner=self.name, universe_size=0)

        # Run pipeline on full universe (features need time series)
        df = self._compute_features(universe)

        # Aggregate to latest row per symbol AFTER feature computation
        # Use view operations: sort + drop_duplicates + groupby are non-copying
        if "symbol" in df.columns:
            df = (
                df.sort_values("timestamp")
                .drop_duplicates(["symbol", "timestamp"], keep="last")
                .groupby("symbol")
                .last()
                .reset_index()
            )
        # No copy needed when no symbol column — pipeline output is already isolated

        scored = self._score(df)
        scored = scored.sort_values(
            ["composite_score", "symbol"], ascending=[False, True], kind="mergesort"
        ).head(self.top_n)
        return self._score_candidates(scored)

    def _score(self, df: pd.DataFrame) -> pd.DataFrame:
        # Mutate in-place to avoid unnecessary copy — DataFrame is isolated from caller
        result = df

        # RSI score: 50 center, +25 for 70, -25 for 30
        rsi = result.get("rsi", pd.Series(50.0, index=result.index)).fillna(50.0)
        result["score_rsi"] = (50.0 + (rsi - 50.0) * 1.0).clip(0, 100)

        # ROC score
        roc = result.get("roc", pd.Series(0.0, index=result.index)).fillna(0.0)
        result["score_roc"] = (50.0 + roc.clip(-10, 10) * 3.0).clip(0, 100)

        # Trend score
        trend = result.get("trend", pd.Series("neutral", index=result.index)).fillna("neutral")
        result["score_trend"] = 50.0
        result.loc[trend == "up", "score_trend"] = 75.0
        result.loc[trend == "down", "score_trend"] = 25.0

        # Volume score
        rel_vol = result.get("relative_volume", pd.Series(1.0, index=result.index)).fillna(1.0)
        result["score_volume"] = (50.0 + (rel_vol - 1.0).clip(-1, 3) * 15.0).clip(0, 100)

        # Momentum score
        mom = result.get("momentum", pd.Series(0.0, index=result.index)).fillna(0.0)
        result["score_momentum"] = (50.0 + mom.clip(-5, 5) * 5.0).clip(0, 100)

        # Composite
        result["composite_score"] = (
            result["score_rsi"] * 0.20
            + result["score_roc"] * 0.20
            + result["score_trend"] * 0.25
            + result["score_volume"] * 0.15
            + result["score_momentum"] * 0.20
        )

        return result


# ---------------------------------------------------------------------------
# Volume Scanner
# ---------------------------------------------------------------------------


@dataclass
class VolumeScanner(BaseScanner):
    """Finds stocks with unusual volume activity."""

    name: str = "volume"
    top_n: int = 10
    pipeline: FeaturePipeline = field(default_factory=_build_volume_pipeline)

    def scan(self, universe: pd.DataFrame) -> ScanResult:
        if universe.empty:
            return ScanResult(scanner=self.name, universe_size=0)

        # Run pipeline on full universe (features need time series)
        df = self._compute_features(universe)

        # Aggregate to latest row per symbol AFTER feature computation
        if "symbol" in df.columns:
            df = (
                df.sort_values("timestamp")
                .drop_duplicates(["symbol", "timestamp"], keep="last")
                .groupby("symbol")
                .last()
                .reset_index()
            )

        scored = self._score(df)
        scored = scored.sort_values(
            ["composite_score", "symbol"], ascending=[False, True], kind="mergesort"
        ).head(self.top_n)
        return self._score_candidates(scored)

    def _score(self, df: pd.DataFrame) -> pd.DataFrame:
        # Mutate in-place to avoid unnecessary copy
        result = df

        # Relative volume is the primary signal
        rel_vol = result.get("relative_volume", pd.Series(1.0, index=result.index)).fillna(1.0)
        result["score_rel_vol"] = (50.0 + (rel_vol - 1.0).clip(-1, 5) * 12.0).clip(0, 100)

        # Volume trend (increasing volume is bullish)
        vol_sma = result.get("volume_sma", pd.Series(0.0, index=result.index)).fillna(1.0)
        volume = result.get("volume", pd.Series(0.0, index=result.index))
        vol_ratio = volume / vol_sma.replace(0, math.inf)
        result["score_vol_trend"] = (50.0 + (vol_ratio - 1.0).clip(-2, 3) * 10.0).clip(0, 100)

        # ATR expansion (volatility with volume = conviction)
        atr_val = result.get("atr", pd.Series(0.0, index=result.index)).fillna(0.0)
        result["score_atr"] = (50.0 + atr_val.clip(0, 10) * 3.0).clip(0, 100)

        # RSI confirmation
        rsi = result.get("rsi", pd.Series(50.0, index=result.index)).fillna(50.0)
        result["score_rsi"] = (50.0 + (rsi - 50.0) * 0.5).clip(0, 100)

        # Composite (volume-heavy)
        result["composite_score"] = (
            result["score_rel_vol"] * 0.40
            + result["score_vol_trend"] * 0.25
            + result["score_atr"] * 0.20
            + result["score_rsi"] * 0.15
        )

        return result


# ---------------------------------------------------------------------------
# Relative Strength Scanner
# ---------------------------------------------------------------------------


@dataclass
class RSScanner(BaseScanner):
    """Finds stocks with strong relative strength vs benchmark."""

    name: str = "rs"
    top_n: int = 10
    pipeline: FeaturePipeline = field(default_factory=_build_rs_pipeline)

    def scan(self, universe: pd.DataFrame) -> ScanResult:
        if universe.empty:
            return ScanResult(scanner=self.name, universe_size=0)

        # Run pipeline on full universe (features need time series)
        df = self._compute_features(universe)

        # Aggregate to latest row per symbol AFTER feature computation
        if "symbol" in df.columns:
            df = (
                df.sort_values("timestamp")
                .drop_duplicates(["symbol", "timestamp"], keep="last")
                .groupby("symbol")
                .last()
                .reset_index()
            )

        scored = self._score(df)
        scored = scored.sort_values(
            ["composite_score", "symbol"], ascending=[False, True], kind="mergesort"
        ).head(self.top_n)
        return self._score_candidates(scored)

    def _score(self, df: pd.DataFrame) -> pd.DataFrame:
        # Mutate in-place to avoid unnecessary copy
        result = df

        # RSI
        rsi = result.get("rsi", pd.Series(50.0, index=result.index)).fillna(50.0)
        result["score_rsi"] = (50.0 + (rsi - 50.0) * 1.0).clip(0, 100)

        # Trend alignment
        trend = result.get("trend", pd.Series("neutral", index=result.index)).fillna("neutral")
        result["score_trend"] = 50.0
        result.loc[trend == "up", "score_trend"] = 75.0
        result.loc[trend == "down", "score_trend"] = 25.0

        # ROC (recent performance)
        roc = result.get("roc", pd.Series(0.0, index=result.index)).fillna(0.0)
        result["score_roc"] = (50.0 + roc.clip(-10, 10) * 3.0).clip(0, 100)

        # Momentum
        mom = result.get("momentum", pd.Series(0.0, index=result.index)).fillna(0.0)
        result["score_momentum"] = (50.0 + mom.clip(-5, 5) * 5.0).clip(0, 100)

        # ATR (volatility expansion = strength)
        atr = result.get("atr", pd.Series(0.0, index=result.index)).fillna(0.0)
        result["score_atr"] = (50.0 + atr.clip(0, 10) * 3.0).clip(0, 100)

        # Composite (trend-heavy for RS)
        result["composite_score"] = (
            result["score_rsi"] * 0.15
            + result["score_trend"] * 0.30
            + result["score_roc"] * 0.25
            + result["score_momentum"] * 0.15
            + result["score_atr"] * 0.15
        )

        return result


# ---------------------------------------------------------------------------
# Breakout Scanner
# ---------------------------------------------------------------------------


@dataclass
class BreakoutScanner(BaseScanner):
    """Finds stocks near breakout (Bollinger squeeze, volume, swing levels)."""

    name: str = "breakout"
    top_n: int = 10
    pipeline: FeaturePipeline = field(default_factory=_build_breakout_pipeline)

    def scan(self, universe: pd.DataFrame) -> ScanResult:
        if universe.empty:
            return ScanResult(scanner=self.name, universe_size=0)

        # Run pipeline on full universe (features need time series)
        df = self._compute_features(universe)

        # Aggregate to latest row per symbol AFTER feature computation
        if "symbol" in df.columns:
            df = (
                df.sort_values("timestamp")
                .drop_duplicates(["symbol", "timestamp"], keep="last")
                .groupby("symbol")
                .last()
                .reset_index()
            )

        scored = self._score(df)
        scored = scored.sort_values(
            ["composite_score", "symbol"], ascending=[False, True], kind="mergesort"
        ).head(self.top_n)
        return self._score_candidates(scored)

    def _score(self, df: pd.DataFrame) -> pd.DataFrame:
        # Mutate in-place to avoid unnecessary copy
        result = df

        # Bollinger %B near upper = breakout potential
        pct_b = result.get("bb_pct_b", pd.Series(0.5, index=result.index))
        result["score_bb"] = (50.0 + (pct_b - 0.5) * 60.0).clip(0, 100)

        # Volume spike
        rel_vol = result.get("relative_volume", pd.Series(1.0, index=result.index))
        result["score_volume"] = (50.0 + (rel_vol - 1.0).clip(-1, 4) * 15.0).clip(0, 100)

        # RSI momentum
        rsi = result.get("rsi", pd.Series(50.0, index=result.index))
        result["score_rsi"] = (50.0 + (rsi - 50.0) * 0.8).clip(0, 100)

        # VWAP proximity (price near VWAP = balanced)
        close = result.get("close", pd.Series(0.0, index=result.index))
        vwap_val = result.get("vwap", pd.Series(0.0, index=result.index))
        vwap_dist = ((close - vwap_val) / vwap_val.replace(0, math.inf) * 100).clip(-5, 5)
        result["score_vwap"] = (50.0 + vwap_dist * 5.0).clip(0, 100)

        # Composite
        result["composite_score"] = (
            result["score_bb"] * 0.30
            + result["score_volume"] * 0.30
            + result["score_rsi"] * 0.20
            + result["score_vwap"] * 0.20
        )

        return result
