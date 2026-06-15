"""Probability scoring engine for analytics signals."""

from __future__ import annotations

from analytics.core.models import AnalysisResult


class ProbabilityEngine:
    def scores(self, metrics: dict[str, float]) -> dict[str, float]:
        trend = self._score(metrics.get("trend", 50.0))
        momentum = self._score(metrics.get("momentum", 50.0))
        volume = self._score(metrics.get("volume", 50.0))
        oi = self._score(metrics.get("oi", 50.0))
        relative_strength = self._score(metrics.get("relative_strength", 50.0))
        composite = (trend * 0.25) + (momentum * 0.25) + (volume * 0.15) + (oi * 0.15) + (relative_strength * 0.20)
        return {
            "trend_score": trend,
            "momentum_score": momentum,
            "volume_score": volume,
            "oi_score": oi,
            "relative_strength_score": relative_strength,
            "composite_score": composite,
        }

    def analyze(self, metrics: dict[str, float], *, symbol: str | None = None) -> AnalysisResult:
        scores = self.scores(metrics)
        composite = scores["composite_score"]
        regime = "High Probability Long" if composite >= 70 else "High Probability Short" if composite <= 30 else "Neutral"
        return AnalysisResult(
            name="probability",
            symbol=symbol,
            summary=f"{regime}: composite score {composite:.2f}.",
            metrics=metrics,
            scores=scores,
            signals=[regime],
            recommendations=["Use probability scores as research inputs, not standalone order signals."],
        )

    def _score(self, value: float) -> float:
        if value < 0:
            return 0.0
        if value > 100:
            return 100.0
        return float(value)
