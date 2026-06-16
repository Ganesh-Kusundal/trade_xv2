"""Sector Strength scoring.

Computes a composite strength score for each sector based on:
    - Momentum (ROC, RSI)
    - Volume (relative volume, volume trend)
    - Breadth (% of stocks above SMA)
    - Relative Strength vs benchmark
    - Trend (price vs moving averages)

Usage:
    scorer = SectorStrengthScorer()
    result = scorer.score(sector_data_dict)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class SectorStrength:
    """Strength score for a single sector."""

    sector: str
    score: float                # 0-100 composite
    momentum_score: float       # 0-100
    volume_score: float         # 0-100
    breadth_score: float        # 0-100
    rs_score: float             # 0-100
    trend_score: float          # 0-100
    stock_count: int            # Number of stocks in sector
    avg_return: float           # Average return over period (%)
    advancing_pct: float        # % of stocks with positive return
    rank: int                   # Rank among all sectors (1 = strongest)
    signal: str                 # "strong" / "neutral" / "weak"


@dataclass
class SectorStrengthResult:
    """Aggregated strength analysis across all sectors."""

    sectors: list[SectorStrength] = field(default_factory=list)
    market_strength: float = 50.0    # Overall market strength
    strongest: str = ""
    weakest: str = ""
    rotation_signal: str = ""
    metadata: dict = field(default_factory=dict)


class SectorStrengthScorer:
    """Score sector strength from multi-stock data.

    Parameters
    ----------
    period:
        Number of periods to evaluate.
    momentum_weight:
        Weight for momentum sub-score.
    volume_weight:
        Weight for volume sub-score.
    breadth_weight:
        Weight for breadth sub-score.
    rs_weight:
        Weight for relative strength sub-score.
    trend_weight:
        Weight for trend sub-score.
    """

    def __init__(
        self,
        period: int = 20,
        momentum_weight: float = 0.25,
        volume_weight: float = 0.20,
        breadth_weight: float = 0.20,
        rs_weight: float = 0.20,
        trend_weight: float = 0.15,
    ) -> None:
        self.period = period
        self.weights = {
            "momentum": momentum_weight,
            "volume": volume_weight,
            "breadth": breadth_weight,
            "rs": rs_weight,
            "trend": trend_weight,
        }
        total = sum(self.weights.values())
        if abs(total - 1.0) > 0.01:
            logger.warning("Weights sum to %.2f, normalizing to 1.0", total)
            self.weights = {k: v / total for k, v in self.weights.items()}

    def score(
        self,
        sector_data: dict[str, pd.DataFrame],
        benchmark: pd.DataFrame | None = None,
        sector_col: str = "sector",
    ) -> SectorStrengthResult:
        """Score strength for each sector.

        Parameters
        ----------
        sector_data:
            Mapping of sector name -> DataFrame with OHLCV data for stocks in that sector.
            Each DataFrame should have columns: symbol, timestamp, open, high, low, close, volume.
        benchmark:
            Benchmark DataFrame (e.g. NIFTY 50). If None, uses equal-weight average.
        sector_col:
            Column name for sector in the DataFrames.

        Returns
        -------
        SectorStrengthResult
        """
        if not sector_data:
            return SectorStrengthResult()

        results: list[SectorStrength] = []

        for sector, data in sorted(sector_data.items()):
            if data.empty:
                continue
            strength = self._score_sector(sector, data)
            results.append(strength)

        # Rank sectors
        results.sort(key=lambda s: s.score, reverse=True)
        for i, s in enumerate(results):
            s.rank = i + 1

        # Market strength: average of all sector scores
        market_strength = float(np.mean([s.score for s in results])) if results else 50.0

        # Rotation signal
        rotation = self._determine_rotation(results)

        return SectorStrengthResult(
            sectors=results,
            market_strength=round(market_strength, 1),
            strongest=results[0].sector if results else "",
            weakest=results[-1].sector if results else "",
            rotation_signal=rotation,
        )

    def _score_sector(self, sector: str, data: pd.DataFrame) -> SectorStrength:
        """Compute strength for a single sector."""
        # Get per-symbol data
        symbols = data["symbol"].unique() if "symbol" in data.columns else ["SECTOR"]

        stock_count = len(symbols)

        # Compute per-symbol metrics
        returns = []
        advancing = 0
        symbol_scores = []

        for sym in symbols:
            if "symbol" in data.columns:
                sym_data = data[data["symbol"] == sym].sort_values("timestamp" if "timestamp" in data.columns else "date")
            else:
                sym_data = data.sort_values("timestamp" if "timestamp" in data.columns else "date")

            if len(sym_data) < 2:
                continue

            # Period return
            first_close = float(sym_data["close"].iloc[0])
            last_close = float(sym_data["close"].iloc[-1])
            ret = ((last_close / first_close) - 1) * 100 if first_close > 0 else 0.0
            returns.append(ret)
            if ret > 0:
                advancing += 1

            # RSI
            rsi = self._compute_rsi(sym_data["close"])
            symbol_scores.append(rsi)

        avg_return = float(np.mean(returns)) if returns else 0.0
        advancing_pct = (advancing / stock_count * 100) if stock_count > 0 else 50.0

        # Sub-scores
        momentum_score = self._momentum_score(returns)
        volume_score = self._volume_score(data)
        breadth_score = advancing_pct  # Direct mapping
        rs_score = self._rs_score(avg_return)
        trend_score = self._trend_score(data)

        # Composite
        score = (
            momentum_score * self.weights["momentum"]
            + volume_score * self.weights["volume"]
            + breadth_score * self.weights["breadth"]
            + rs_score * self.weights["rs"]
            + trend_score * self.weights["trend"]
        )

        # Signal
        if score >= 65:
            signal = "strong"
        elif score <= 35:
            signal = "weak"
        else:
            signal = "neutral"

        return SectorStrength(
            sector=sector,
            score=round(score, 1),
            momentum_score=round(momentum_score, 1),
            volume_score=round(volume_score, 1),
            breadth_score=round(breadth_score, 1),
            rs_score=round(rs_score, 1),
            trend_score=round(trend_score, 1),
            stock_count=stock_count,
            avg_return=round(avg_return, 2),
            advancing_pct=round(advancing_pct, 1),
            rank=0,  # Set later
            signal=signal,
        )

    def _momentum_score(self, returns: list[float]) -> float:
        if not returns:
            return 50.0
        avg_ret = float(np.mean(returns))
        # Map -20%..+20% -> 0..100
        return max(0.0, min(100.0, 50 + avg_ret * 2.5))

    def _volume_score(self, data: pd.DataFrame) -> float:
        if "volume" not in data.columns or len(data) < 10:
            return 50.0
        vol = data["volume"]
        recent = float(vol.tail(10).mean())
        earlier = float(vol.head(10).mean())
        if earlier == 0:
            return 50.0
        change = (recent / earlier - 1) * 100
        return max(0.0, min(100.0, 50 + change * 2))

    def _rs_score(self, avg_return: float) -> float:
        # Relative to market (assume 0% = neutral)
        return max(0.0, min(100.0, 50 + avg_return * 2.5))

    def _trend_score(self, data: pd.DataFrame) -> float:
        if "close" not in data.columns or len(data) < 20:
            return 50.0
        close = data["close"]
        sma20 = close.rolling(20).mean()
        last_close = float(close.iloc[-1])
        last_sma = float(sma20.iloc[-1]) if not pd.isna(sma20.iloc[-1]) else last_close
        if last_sma == 0:
            return 50.0
        deviation = (last_close / last_sma - 1) * 100
        return max(0.0, min(100.0, 50 + deviation * 10))

    @staticmethod
    def _compute_rsi(prices: pd.Series, period: int = 14) -> float:
        if len(prices) < period + 1:
            return 50.0
        delta = prices.diff()
        gain = delta.clip(lower=0).rolling(period).mean()
        loss = (-delta.clip(upper=0)).rolling(period).mean()
        rs = gain / loss
        rsi = 100 - 100 / (1 + rs)
        last_rsi = rsi.iloc[-1]
        return float(last_rsi) if not pd.isna(last_rsi) else 50.0

    @staticmethod
    def _determine_rotation(sectors: list[SectorStrength]) -> str:
        if len(sectors) < 2:
            return "Neutral"
        scores = [s.score for s in sectors]
        top = scores[0]
        bottom = scores[-1]
        spread = top - bottom
        if spread > 30 and top > 60:
            return "Rotational (leaders emerging)"
        elif spread < 10:
            return "Broad-based"
        elif top < 40:
            return "Weak (defensive)"
        return "Neutral"
