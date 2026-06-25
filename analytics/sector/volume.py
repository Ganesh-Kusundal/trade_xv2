"""Sector-wise volume analysis.

Analyzes:
    - Volume profile per sector (relative volume, volume trend)
    - Sector volume rank (which sectors see most activity)
    - Volume concentration (is volume集中在少数 sector 还是分散)
    - Volume rotation (volume shifting between sectors)

Usage:
    analyzer = SectorVolumeAnalyzer()
    result = analyzer.analyze(market_data_with_sectors)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class SectorVolumeProfile:
    """Volume profile for a single sector."""

    sector: str
    total_volume: float  # Sum of volume over period
    avg_daily_volume: float  # Average daily volume
    volume_change_pct: float  # Volume change vs previous period (%)
    relative_volume: float  # Volume vs market average (1.0 = average)
    high_volume_days: int  # Days with > 1.5x average volume
    volume_trend: str  # "increasing" / "decreasing" / "stable"
    vwap_deviation: float  # Avg price deviation from VWAP (%)
    score: float  # Composite volume score 0-100


@dataclass
class SectorVolumeResult:
    """Aggregated sector volume analysis."""

    profiles: list[SectorVolumeProfile] = field(default_factory=list)
    total_market_volume: float = 0.0
    volume_concentration: float = 0.0  # HHI index (0=分散, 1=集中)
    top_volume_sector: str = ""
    low_volume_sector: str = ""
    volume_rotation_signal: str = "neutral"  # "rotating" / "concentrating" / "neutral"
    metadata: dict = field(default_factory=dict)


class SectorVolumeAnalyzer:
    """Analyze volume patterns across sectors.

    Parameters
    ----------
    period:
        Number of periods to analyze.
    high_vol_threshold:
        Multiplier for "high volume day" detection (default 1.5x).
    """

    def __init__(self, period: int = 20, high_vol_threshold: float = 1.5) -> None:
        self.period = period
        self.high_vol_threshold = high_vol_threshold

    def analyze(
        self,
        data: pd.DataFrame,
        sector_col: str = "sector",
    ) -> SectorVolumeResult:
        """Analyze volume across sectors.

        Parameters
        ----------
        data:
            DataFrame with columns: symbol, timestamp/date, open, high, low, close, volume, sector.
            If 'sector' column is missing, tries to load from SectorMapper.
        sector_col:
            Name of the sector column.

        Returns
        -------
        SectorVolumeResult
        """
        if data.empty or "volume" not in data.columns:
            return SectorVolumeResult()

        df = data.copy()

        # If no sector column, try to assign
        if sector_col not in df.columns:
            try:
                from analytics.sector.mapping import SectorMapper

                mapper = SectorMapper.default()
                df = mapper.assign_sectors(df)
                sector_col = "sector"
            except Exception:
                logger.warning("No sector column and no mapping available")
                return SectorVolumeResult()

        # Filter to recent period
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            cutoff = df["timestamp"].max() - pd.Timedelta(days=self.period * 2)
            df = df[df["timestamp"] >= cutoff]
        elif "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            cutoff = df["date"].max() - pd.Timedelta(days=self.period * 2)
            df = df[df["date"] >= cutoff]

        # Group by sector
        sectors = df[sector_col].unique()
        profiles: list[SectorVolumeProfile] = []

        total_market_volume = float(df["volume"].sum())

        for sector in sorted(sectors):
            if sector == "Unknown":
                continue
            sec_df = df[df[sector_col] == sector]
            profile = self._compute_profile(sector, sec_df, total_market_volume)
            profiles.append(profile)

        profiles.sort(key=lambda p: p.total_volume, reverse=True)

        # Volume concentration (HHI)
        if profiles:
            shares = [
                p.total_volume / total_market_volume for p in profiles if total_market_volume > 0
            ]
            volume_concentration = sum(s**2 for s in shares)
        else:
            volume_concentration = 0.0

        # Top / low
        top_sector = profiles[0].sector if profiles else ""
        low_sector = profiles[-1].sector if profiles else ""

        # Volume rotation signal
        vol_changes = [p.volume_change_pct for p in profiles]
        if len(vol_changes) > 2:
            std_change = float(np.std(vol_changes))
            if std_change > 20:
                vol_signal = "rotating"
            elif std_change < 5:
                vol_signal = "concentrating"
            else:
                vol_signal = "neutral"
        else:
            vol_signal = "neutral"

        return SectorVolumeResult(
            profiles=profiles,
            total_market_volume=total_market_volume,
            volume_concentration=round(volume_concentration, 4),
            top_volume_sector=top_sector,
            low_volume_sector=low_sector,
            volume_rotation_signal=vol_signal,
        )

    def _compute_profile(
        self,
        sector: str,
        data: pd.DataFrame,
        total_market_volume: float,
    ) -> SectorVolumeProfile:
        vol = data["volume"]
        total_volume = float(vol.sum())
        avg_daily = float(vol.mean())

        # Volume change: compare last half vs first half
        mid = len(vol) // 2
        if mid > 0:
            first_half = float(vol.iloc[:mid].mean())
            second_half = float(vol.iloc[mid:].mean())
            vol_change = ((second_half - first_half) / first_half * 100) if first_half > 0 else 0.0
        else:
            vol_change = 0.0

        # Relative volume vs market average
        market_avg = total_market_volume / max(len(data), 1) if total_market_volume > 0 else 1
        avg_per_symbol = total_volume / max(len(data), 1)
        relative_volume = avg_per_symbol / market_avg if market_avg > 0 else 1.0

        # High volume days
        high_vol_days = (
            int((vol > avg_daily * self.high_vol_threshold).sum()) if avg_daily > 0 else 0
        )

        # Volume trend
        if len(vol) >= 10:
            recent_avg = float(vol.tail(10).mean())
            earlier_avg = float(vol.head(10).mean())
            if recent_avg > earlier_avg * 1.1:
                trend = "increasing"
            elif recent_avg < earlier_avg * 0.9:
                trend = "decreasing"
            else:
                trend = "stable"
        else:
            trend = "stable"

        # VWAP deviation
        if "close" in data.columns and "volume" in data.columns:
            vwap = (
                (data["close"] * data["volume"]).sum() / vol.sum()
                if vol.sum() > 0
                else data["close"].mean()
            )
            avg_price = data["close"].mean()
            vwap_dev = ((avg_price - vwap) / vwap * 100) if vwap > 0 else 0.0
        else:
            vwap_dev = 0.0

        # Composite score
        score = self._compute_score(relative_volume, vol_change, high_vol_days, trend)

        return SectorVolumeProfile(
            sector=sector,
            total_volume=total_volume,
            avg_daily_volume=avg_daily,
            volume_change_pct=round(vol_change, 1),
            relative_volume=round(relative_volume, 2),
            high_volume_days=high_vol_days,
            volume_trend=trend,
            vwap_deviation=round(vwap_dev, 2),
            score=round(score, 1),
        )

    @staticmethod
    def _compute_score(
        relative_volume: float,
        vol_change: float,
        high_vol_days: int,
        trend: str,
    ) -> float:
        # Relative volume score (0-40)
        rv_score = min(40, max(0, relative_volume * 20))

        # Volume change score (0-30)
        vc_score = min(30, max(0, 15 + vol_change * 0.5))

        # High volume days score (0-20)
        hv_score = min(20, high_vol_days * 2)

        # Trend score (0-10)
        trend_score = {"increasing": 10, "stable": 5, "decreasing": 0}.get(trend, 5)

        return rv_score + vc_score + hv_score + trend_score
