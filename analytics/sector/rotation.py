"""Sector Rotation analysis.

Detects rotation patterns:
    - Risk-on vs Defensive rotation
    - Momentum rotation (money flowing into/out of sectors)
    - Sector leadership changes over time
    - Relative rotation graph (RRG) quadrants

Usage:
    analyzer = RotationAnalyzer()
    result = analyzer.analyze(sector_timeseries_df)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class RotationPhase(str, Enum):
    """RRG (Relative Rotation Graph) quadrants."""

    LEADING = "Leading"       # Strong RS + positive momentum
    IMPROVING = "Improving"   # Weak RS + positive momentum
    LAGGING = "Lagging"       # Weak RS + negative momentum
    WEAKENING = "Weakening"   # Strong RS + negative momentum


@dataclass
class SectorRotation:
    """Rotation state for a single sector."""

    sector: str
    phase: RotationPhase
    rs_ratio: float          # Relative strength vs benchmark (100 = neutral)
    rs_momentum: float       # Rate of change of RS ratio
    volume_trend: float      # Volume change vs 20-period average
    score: float             # Composite rotation score 0-100
    signal: str              # " inflow" / "outflow" / "neutral"


@dataclass
class RotationResult:
    """Aggregated rotation analysis across all sectors."""

    sectors: list[SectorRotation] = field(default_factory=list)
    rotation_regime: str = "Neutral"  # "Risk-on" / "Risk-off" / "Rotational" / "Neutral"
    leading_sectors: list[str] = field(default_factory=list)
    lagging_sectors: list[str] = field(default_factory=list)
    breadth_score: float = 50.0  # How many sectors are in uptrend
    metadata: dict = field(default_factory=dict)


class RotationAnalyzer:
    """Analyze sector rotation from time-series data.

    Parameters
    ----------
    lookback:
        Number of periods to compute RS ratio and momentum.
    rs_period:
        Lookback for relative strength ratio.
    momentum_period:
        Lookback for RS momentum (rate of change).
    """

    def __init__(
        self,
        lookback: int = 20,
        rs_period: int = 14,
        momentum_period: int = 10,
    ) -> None:
        self.lookback = lookback
        self.rs_period = rs_period
        self.momentum_period = momentum_period

    def analyze(
        self,
        sector_returns: pd.DataFrame,
        benchmark_returns: pd.Series | None = None,
    ) -> RotationResult:
        """Analyze sector rotation.

        Parameters
        ----------
        sector_returns:
            DataFrame with columns = sector names, values = period returns.
            Index should be datetime or integer periods.
        benchmark_returns:
            Benchmark index returns (e.g. NIFTY 50). If None, uses equal-weight average.

        Returns
        -------
        RotationResult
        """
        if sector_returns.empty or sector_returns.shape[1] == 0:
            return RotationResult()

        df = sector_returns.copy()

        # Benchmark: equal-weight average if not provided
        if benchmark_returns is None:
            benchmark_returns = df.mean(axis=1)

        # Compute RS ratio for each sector
        rs_data = {}
        for col in df.columns:
            sector_cum = (1 + df[col]).cumprod()
            bench_cum = (1 + benchmark_returns).cumprod()
            rs_ratio = (sector_cum / bench_cum) * 100  # 100 = in line with benchmark
            rs_data[col] = rs_ratio

        rs_df = pd.DataFrame(rs_data)

        # RS momentum: rate of change of RS ratio
        sectors: list[SectorRotation] = []

        for col in df.columns:
            if col not in rs_df.columns:
                continue

            rs = rs_df[col].dropna()
            if len(rs) < max(self.rs_period, self.momentum_period) + 1:
                continue

            # Current RS ratio (latest value)
            rs_current = float(rs.iloc[-1])

            # RS momentum: % change over momentum_period
            if len(rs) >= self.momentum_period:
                rs_momentum = ((rs.iloc[-1] / rs.iloc[-self.momentum_period]) - 1) * 100
            else:
                rs_momentum = 0.0

            # Volume trend (if volume data available in sector_returns)
            # For now use return magnitude as proxy
            recent_returns = df[col].tail(self.lookback)
            vol_trend = float(recent_returns.std()) * 100  # Volatility as volume proxy

            # Determine RRG quadrant
            phase = self._classify_phase(rs_current, rs_momentum)

            # Composite rotation score
            score = self._compute_score(rs_current, rs_momentum)

            # Signal
            if rs_momentum > 2 and rs_current > 100:
                signal = "inflow"
            elif rs_momentum < -2 and rs_current < 100:
                signal = "outflow"
            else:
                signal = "neutral"

            sectors.append(SectorRotation(
                sector=col,
                phase=phase,
                rs_ratio=round(rs_current, 2),
                rs_momentum=round(rs_momentum, 2),
                volume_trend=round(vol_trend, 2),
                score=round(score, 1),
                signal=signal,
            ))

        # Sort by score descending
        sectors.sort(key=lambda s: s.score, reverse=True)

        # Overall regime
        regime = self._determine_regime(sectors)

        # Leading / lagging
        leading = [s.sector for s in sectors if s.phase == RotationPhase.LEADING]
        lagging = [s.sector for s in sectors if s.phase in (RotationPhase.LAGGING, RotationPhase.WEAKENING)]

        # Breadth: % of sectors with positive momentum
        positive_momentum = sum(1 for s in sectors if s.rs_momentum > 0)
        breadth = (positive_momentum / len(sectors) * 100) if sectors else 50.0

        return RotationResult(
            sectors=sectors,
            rotation_regime=regime,
            leading_sectors=leading,
            lagging_sectors=lagging,
            breadth_score=round(breadth, 1),
        )

    @staticmethod
    def _classify_phase(rs_ratio: float, rs_momentum: float) -> RotationPhase:
        if rs_momentum >= 0 and rs_ratio >= 100:
            return RotationPhase.LEADING
        elif rs_momentum >= 0 and rs_ratio < 100:
            return RotationPhase.IMPROVING
        elif rs_momentum < 0 and rs_ratio < 100:
            return RotationPhase.LAGGING
        else:
            return RotationPhase.WEAKENING

    @staticmethod
    def _compute_score(rs_ratio: float, rs_momentum: float) -> float:
        # RS ratio contributes 50%, momentum contributes 50%
        rs_score = max(0, min(100, rs_ratio))  # 0-100 scale
        mom_score = max(0, min(100, 50 + rs_momentum * 5))  # 0 at mom=-10, 100 at mom=10
        return rs_score * 0.5 + mom_score * 0.5

    @staticmethod
    def _determine_regime(sectors: list[SectorRotation]) -> str:
        if not sectors:
            return "Neutral"
        leading = sum(1 for s in sectors if s.phase == RotationPhase.LEADING)
        lagging = sum(1 for s in sectors if s.phase == RotationPhase.LAGGING)
        total = len(sectors)
        leading_pct = leading / total
        lagging_pct = lagging / total

        if leading_pct >= 0.5:
            return "Risk-on"
        elif lagging_pct >= 0.5:
            return "Risk-off"
        elif leading_pct > 0 and lagging_pct > 0:
            return "Rotational"
        return "Neutral"
