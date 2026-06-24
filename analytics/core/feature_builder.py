"""Feature Builder for broker-neutral OHLCV analytics."""

from __future__ import annotations

import logging

import pandas as pd

from analytics.core.models import FeatureSet, normalize_ohlcv
from analytics.indicators.market_structure import MarketStructureAnalyzer
from analytics.pipeline.features import ATR, RSI, ROC, Momentum
from analytics.pipeline.pipeline import FeaturePipeline

logger = logging.getLogger(__name__)


class FeatureBuilder:
    def __init__(
        self,
        *,
        volume_bars: int = 20,
        rsi_period: int = 14,
        atr_period: int = 14,
    ) -> None:
        if volume_bars < 2:
            raise ValueError("volume_bars must be >= 2")
        self._volume_bars = volume_bars
        self._rsi_period = rsi_period
        self._atr_period = atr_period
        self._structure = MarketStructureAnalyzer()

    def build(
        self,
        data: pd.DataFrame,
        *,
        symbol: str | None = None,
        exchange: str | None = None,
        timeframe: str | None = None,
    ) -> FeatureSet:
        df = normalize_ohlcv(data, symbol=symbol, exchange=exchange, timeframe=timeframe)
        if df.empty:
            logger.debug("FeatureBuilder: empty data for %s", symbol)
            return FeatureSet(
                data=pd.DataFrame(),
                features={},
                summary={"bar_count": 0},
                symbol=symbol,
                exchange=exchange,
                timeframe=timeframe,
            )

        features = df.copy()
        close = features["close"]
        volume = features["volume"]

        # Use FeaturePipeline for canonical indicator computations (migrated from deprecated indicators.technical)
        pipeline = FeaturePipeline()
        pipeline.add(RSI(period=self._rsi_period))
        pipeline.add(ATR(period=self._atr_period))
        pipeline.add(ROC(period=1))
        pipeline.add(Momentum(period=1))
        features = pipeline.run(features)

        features["returns"] = close.pct_change().fillna(0)
        # acceleration = second derivative of returns (no direct Feature class equivalent)
        features["acceleration"] = features["close"].pct_change().diff().fillna(0)

        rolling_volume = volume.rolling(self._volume_bars, min_periods=1).mean()
        rolling_volume_std = volume.rolling(self._volume_bars, min_periods=2).std().fillna(0)
        features["volume_average"] = rolling_volume
        features["relative_volume"] = volume / rolling_volume.replace(0, pd.NA)
        features["relative_volume"] = features["relative_volume"].fillna(0)
        features["volume_zscore"] = (volume - rolling_volume) / rolling_volume_std.replace(0, pd.NA)
        features["volume_zscore"] = features["volume_zscore"].fillna(0)
        features["volume_spike"] = (features["relative_volume"] >= 2.0) | (
            features["volume_zscore"] >= 2.0
        )
        features["volume_dry_up"] = features["relative_volume"] <= 0.5
        signed_volume = volume * features["returns"].apply(lambda value: 1 if value > 0 else -1 if value < 0 else 0)
        features["volume_accumulation"] = signed_volume.rolling(self._volume_bars, min_periods=1).sum()
        features["rolling_high_20"] = features["high"].rolling(20, min_periods=5).max()
        features["rolling_low_20"] = features["low"].rolling(20, min_periods=5).min()

        features = self._structure.analyze(features)
        summary = self._summarize(features)
        return FeatureSet(
            data=features,
            features={
                "volume_bars": self._volume_bars,
                "rsi_period": self._rsi_period,
                "atr_period": self._atr_period,
            },
            summary=summary,
            symbol=symbol or str(features["symbol"].iloc[-1]),
            exchange=exchange or str(features["exchange"].iloc[-1]),
            timeframe=timeframe or str(features["timeframe"].iloc[-1]),
        )

    def _summarize(self, features: pd.DataFrame) -> dict[str, float]:
        last = features.iloc[-1]
        return {
            "bar_count": float(len(features)),
            "last_close": float(last["close"]),
            "last_volume": float(last["volume"]),
            "last_relative_volume": float(last["relative_volume"]),
            "last_rsi": float(last["rsi"]) if pd.notna(last["rsi"]) else 0.0,
            "last_atr": float(last["atr"]) if pd.notna(last["atr"]) else 0.0,
            "last_roc": float(last["roc"]) if pd.notna(last["roc"]) else 0.0,
            "last_acceleration": float(last["acceleration"]) if pd.notna(last["acceleration"]) else 0.0,
            "trend_score": self._trend_score(features),
        }

    def _trend_score(self, features: pd.DataFrame) -> float:
        last = features.iloc[-1]
        score = 50.0
        trend = str(last["trend"])
        if trend == "Uptrend":
            score += 25.0
        elif trend == "Downtrend":
            score -= 25.0
        structure = str(last["market_structure"])
        if structure == "Breakout":
            score += 15.0
        elif structure in {"Trend Continuation", "Pullback"}:
            score += 10.0
        elif structure == "Compression":
            score += 5.0
        rsi_value = float(last["rsi"]) if pd.notna(last["rsi"]) else 50.0
        score += (rsi_value - 50.0) * 0.2
        return max(0.0, min(100.0, score))
