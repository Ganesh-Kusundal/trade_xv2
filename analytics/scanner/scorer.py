"""Scorer Protocol - Configurable scoring for scanner candidates.

Enables consistent score normalization across scanners.
All scores are normalized to 0-100 range.

Usage:
    scorer = LinearScorer(center=50, scale=12.0)
    candidate.score = scorer.score(rsi_value, reference=50.0)

This module provides a protocol-based approach to scoring, allowing
different scoring strategies (linear, sigmoid, etc.) to be used
interchangeably across the scanner framework.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass


class Scorer(ABC):
    """Protocol for score computation and normalization.

    All scorers must implement two methods:
    - score(): Compute a score from a raw indicator value
    - normalize(): Clip/bound a raw score to the valid range

    The default range is [0, 100], suitable for percentile-style
    ranking across scanner candidates.
    """

    @abstractmethod
    def score(self, value: float, reference: float) -> float:
        """Compute score from indicator value.

        Args:
            value: Raw indicator value (e.g., RSI=65.3)
            reference: Reference/baseline value (e.g., neutral RSI=50.0)

        Returns:
            Score normalized to 0-100 range
        """
        ...

    @abstractmethod
    def normalize(self, raw_score: float) -> float:
        """Normalize raw score to 0-100 range.

        Args:
            raw_score: Unbounded score (may be negative or >100)

        Returns:
            Score clipped to [min_score, max_score]
        """
        ...


@dataclass
class LinearScorer(Scorer):
    """Linear scoring with configurable center and scale.

    Formula: score = center + (value - reference) * scale
    Then clipped to [min_score, max_score].

    Example:
        # RSI-based scoring: center=50, scale=1.0
        # RSI=60 vs reference=50 → score = 50 + (60-50)*1.0 = 60
        # RSI=40 vs reference=50 → score = 50 + (40-50)*1.0 = 40

    Attributes:
        center: Base score when value equals reference (default 50)
        scale: Multiplier for deviation from reference (default 1.0)
        min_score: Minimum allowed score (default 0)
        max_score: Maximum allowed score (default 100)
    """

    center: float = 50.0
    scale: float = 1.0
    min_score: float = 0.0
    max_score: float = 100.0

    def score(self, value: float, reference: float) -> float:
        """Compute linear score.

        Args:
            value: Raw indicator value
            reference: Reference/baseline value

        Returns:
            Score clipped to [min_score, max_score]
        """
        raw = self.center + (value - reference) * self.scale
        return self.normalize(raw)

    def normalize(self, raw_score: float) -> float:
        """Clip to [min_score, max_score]."""
        return max(self.min_score, min(self.max_score, raw_score))


@dataclass
class SigmoidScorer(Scorer):
    """Sigmoid scoring for smooth saturation.

    Formula: score = center + (max_score - center) * sigmoid(value - reference)

    The sigmoid function provides smooth saturation at extremes,
    making it ideal for indicators where extreme values shouldn't
    linearly increase the score.

    Example:
        # Steepness=0.1 means:
        #   value - reference = 0  → score = 50 (neutral)
        #   value - reference = 10 → score ≈ 71
        #   value - reference = 20 → score ≈ 86
        #   value - reference = -10 → score ≈ 29

    Attributes:
        center: Base score when value equals reference (default 50)
        steepness: Controls how quickly score saturates (default 0.1)
        min_score: Minimum allowed score (default 0)
        max_score: Maximum allowed score (default 100)
    """

    center: float = 50.0
    steepness: float = 0.1
    min_score: float = 0.0
    max_score: float = 100.0

    def score(self, value: float, reference: float) -> float:
        """Compute sigmoid score.

        Args:
            value: Raw indicator value
            reference: Reference/baseline value

        Returns:
            Score clipped to [min_score, max_score]
        """
        x = (value - reference) * self.steepness
        sigmoid = 1.0 / (1.0 + math.exp(-x))
        raw = self.center + (self.max_score - self.center) * (sigmoid - 0.5) * 2
        return self.normalize(raw)

    def normalize(self, raw_score: float) -> float:
        """Clip to [min_score, max_score]."""
        return max(self.min_score, min(self.max_score, raw_score))
