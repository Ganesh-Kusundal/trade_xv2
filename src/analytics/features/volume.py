"""Volume analytics."""

from __future__ import annotations

import pandas as pd

from analytics.core.models import AnalysisResult


class VolumeAnalytics:
    def analyze(self, features: pd.DataFrame) -> AnalysisResult:
        if features.empty:
            return AnalysisResult(name="volume", summary="No volume data")

        last = features.iloc[-1]
        relative_volume = (
            float(last.get("relative_volume", 0.0))
            if pd.notna(last.get("relative_volume", 0.0))
            else 0.0
        )
        volume_spike = bool(last.get("volume_spike", False))
        dry_up = bool(last.get("volume_dry_up", False))
        accumulation = (
            float(last.get("volume_accumulation", 0.0))
            if pd.notna(last.get("volume_accumulation", 0.0))
            else 0.0
        )
        score = min(100.0, max(0.0, 50.0 + (relative_volume - 1.0) * 20.0))
        if volume_spike:
            score = min(100.0, score + 20.0)
        if dry_up:
            score = max(0.0, score - 20.0)

        signal = "Volume Spike" if volume_spike else "Volume Dry-Up" if dry_up else "Normal Volume"
        return AnalysisResult(
            name="volume",
            summary=f"{signal}; relative volume {relative_volume:.2f}x.",
            metrics={
                "relative_volume": relative_volume,
                "volume_accumulation": accumulation,
                "volume_spike": volume_spike,
                "volume_dry_up": dry_up,
            },
            scores={"volume": score},
            signals=[signal],
            recommendations=["Confirm breakouts with volume expansion."]
            if volume_spike
            else ["Treat dry-up near support/resistance as compression, not confirmation."],
        )
