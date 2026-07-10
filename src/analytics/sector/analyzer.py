"""Sector Analyzer — unified facade for sector analysis.

Combines:
    - Sector Rotation analysis (RRG quadrants, risk-on/off)
    - Sector Volume analysis (volume profile, concentration)
    - Sector Strength scoring (momentum, breadth, RS, trend)

Usage:
    analyzer = SectorAnalyzer()
    result = analyzer.analyze(market_data)
    print(result.rotation.rotation_regime)
    print(result.volume.top_volume_sector)
    print(result.strength.strongest)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import pandas as pd

from analytics.core.models import AnalysisResult
from analytics.sector.mapping import SectorMapper
from analytics.sector.rotation import RotationAnalyzer, RotationResult
from analytics.sector.strength import SectorStrengthResult, SectorStrengthScorer
from analytics.sector.volume import SectorVolumeAnalyzer, SectorVolumeResult

logger = logging.getLogger(__name__)


@dataclass
class SectorAnalysisResult:
    """Combined result from all sector analyses."""

    rotation: RotationResult = field(default_factory=RotationResult)
    volume: SectorVolumeResult = field(default_factory=SectorVolumeResult)
    strength: SectorStrengthResult = field(default_factory=SectorStrengthResult)
    mapper: SectorMapper | None = None
    metadata: dict = field(default_factory=dict)


class SectorAnalyzer:
    """Unified sector analysis facade.

    Parameters
    ----------
    mapper:
        SectorMapper for stock-to-sector mapping. Uses default NIFTY mapping if None.
    rotation_lookback:
        Lookback periods for rotation analysis.
    volume_period:
        Period for volume analysis.
    strength_period:
        Period for strength scoring.
    """

    def __init__(
        self,
        mapper: SectorMapper | None = None,
        rotation_lookback: int = 20,
        volume_period: int = 20,
        strength_period: int = 20,
    ) -> None:
        self.mapper = mapper or SectorMapper.default()
        self._rotation = RotationAnalyzer(lookback=rotation_lookback)
        self._volume = SectorVolumeAnalyzer(period=volume_period)
        self._strength = SectorStrengthScorer(period=strength_period)

    def analyze(
        self,
        data: pd.DataFrame,
        *,
        returns_mode: bool = False,
    ) -> SectorAnalysisResult:
        """Run full sector analysis on market data.

        Parameters
        ----------
        data:
            If returns_mode=False: DataFrame with columns [symbol, timestamp, open, high, low, close, volume].
            If returns_mode=True: DataFrame with columns = sector names, values = period returns.
        returns_mode:
            If True, treats data as sector returns (for rotation analysis only).

        Returns
        -------
        SectorAnalysisResult
        """
        if data.empty:
            return SectorAnalysisResult(mapper=self.mapper)

        # 1. Assign sectors if needed
        df = data.copy()
        if "sector" not in df.columns and "symbol" in df.columns:
            df = self.mapper.assign_sectors(df)

        # 2. Rotation analysis
        if returns_mode:
            # Data is already returns per sector
            benchmark = df.mean(axis=1) if df.shape[1] > 1 else None
            rotation_result = self._rotation.analyze(df, benchmark)
        else:
            rotation_result = self._analyze_rotation_from_ohlcv(df)

        # 3. Volume analysis
        volume_result = self._volume.analyze(df)

        # 4. Strength analysis
        sector_data = self._split_by_sector(df)
        strength_result = self._strength.score(sector_data)

        return SectorAnalysisResult(
            rotation=rotation_result,
            volume=volume_result,
            strength=strength_result,
            mapper=self.mapper,
        )

    def analyze_rotation(
        self,
        sector_returns: pd.DataFrame,
        benchmark_returns: pd.Series | None = None,
    ) -> RotationResult:
        """Analyze rotation from sector return time series."""
        return self._rotation.analyze(sector_returns, benchmark_returns)

    def analyze_volume(self, data: pd.DataFrame) -> SectorVolumeResult:
        """Analyze volume across sectors."""
        return self._volume.analyze(data)

    def analyze_strength(
        self,
        sector_data: dict[str, pd.DataFrame],
    ) -> SectorStrengthResult:
        """Score sector strength from per-sector DataFrames."""
        return self._strength.score(sector_data)

    def to_analysis_result(self, result: SectorAnalysisResult) -> AnalysisResult:
        """Convert SectorAnalysisResult to the standard AnalysisResult format."""
        metrics = {}
        scores = {}
        signals = []

        # Rotation
        if result.rotation.sectors:
            metrics["rotation_regime"] = result.rotation.rotation_regime
            metrics["leading_sectors"] = result.rotation.leading_sectors
            metrics["lagging_sectors"] = result.rotation.lagging_sectors
            metrics["sector_rotation"] = [
                {
                    "sector": s.sector,
                    "phase": s.phase.value,
                    "rs_ratio": s.rs_ratio,
                    "momentum": s.rs_momentum,
                    "score": s.score,
                }
                for s in result.rotation.sectors
            ]
            signals.append(result.rotation.rotation_regime)

        # Volume
        if result.volume.profiles:
            metrics["volume_concentration"] = result.volume.volume_concentration
            metrics["top_volume_sector"] = result.volume.top_volume_sector
            metrics["sector_volume"] = [
                {
                    "sector": p.sector,
                    "volume": p.total_volume,
                    "change_pct": p.volume_change_pct,
                    "trend": p.volume_trend,
                }
                for p in result.volume.profiles
            ]

        # Strength
        if result.strength.sectors:
            metrics["strongest_sector"] = result.strength.strongest
            metrics["weakest_sector"] = result.strength.weakest
            metrics["market_strength"] = result.strength.market_strength
            metrics["sector_strength"] = [
                {
                    "sector": s.sector,
                    "score": s.score,
                    "momentum": s.momentum_score,
                    "volume": s.volume_score,
                    "breadth": s.breadth_score,
                    "signal": s.signal,
                }
                for s in result.strength.sectors
            ]
            scores["market_strength"] = result.strength.market_strength

        return AnalysisResult(
            name="sector_analysis",
            summary=self._build_summary(result),
            metrics=metrics,
            scores=scores,
            signals=signals,
        )

    def _analyze_rotation_from_ohlcv(self, df: pd.DataFrame) -> RotationResult:
        """Compute sector returns from OHLCV data and run rotation analysis."""
        if "sector" not in df.columns or "close" not in df.columns:
            return RotationResult()

        # Pivot to get per-sector returns
        ts_col = (
            "timestamp" if "timestamp" in df.columns else "date" if "date" in df.columns else None
        )
        if ts_col is None:
            return RotationResult()

        df = df.copy()
        df[ts_col] = pd.to_datetime(df[ts_col])

        # Compute daily returns per sector
        sector_returns = {}
        for sector in df["sector"].unique():
            if sector == "Unknown":
                continue
            sec_data = df[df["sector"] == sector].copy()
            if "symbol" in sec_data.columns:
                # Average close across symbols per day
                daily = sec_data.groupby(ts_col)["close"].mean()
            else:
                daily = sec_data.set_index(ts_col)["close"]
            daily = daily.sort_index()
            returns = daily.pct_change().dropna()
            if len(returns) > 0:
                sector_returns[sector] = returns

        if not sector_returns:
            return RotationResult()

        returns_df = pd.DataFrame(sector_returns)
        benchmark = returns_df.mean(axis=1) if returns_df.shape[1] > 1 else None
        return self._rotation.analyze(returns_df, benchmark)

    def _split_by_sector(self, df: pd.DataFrame) -> dict[str, pd.DataFrame]:
        """Split OHLCV data into per-sector DataFrames."""
        if "sector" not in df.columns:
            return {}
        result = {}
        for sector in df["sector"].unique():
            if sector == "Unknown":
                continue
            result[sector] = df[df["sector"] == sector].copy()
        return result

    @staticmethod
    def _build_summary(result: SectorAnalysisResult) -> str:
        parts = []
        if result.rotation.sectors:
            parts.append(f"Rotation: {result.rotation.rotation_regime}")
            if result.rotation.leading_sectors:
                parts.append(f"Leading: {', '.join(result.rotation.leading_sectors[:3])}")
        if result.strength.sectors:
            parts.append(
                f"Strongest: {result.strength.strongest}, Weakest: {result.strength.weakest}"
            )
        if result.volume.top_volume_sector:
            parts.append(f"Highest volume: {result.volume.top_volume_sector}")
        return ". ".join(parts) if parts else "No sector data available."
