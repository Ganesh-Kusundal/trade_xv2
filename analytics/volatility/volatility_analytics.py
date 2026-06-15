"""Volatility analytics."""

from __future__ import annotations

import logging
import math

import pandas as pd

from analytics.core.feature_builder import FeatureBuilder
from analytics.core.models import AnalysisResult
from analytics.indicators.technical import historical_volatility, realized_volatility

logger = logging.getLogger(__name__)


class VolatilityAnalytics:
    def __init__(self, feature_builder: FeatureBuilder | None = None) -> None:
        self._features = feature_builder or FeatureBuilder()

    def analyze(
        self,
        symbol: str,
        prices: pd.DataFrame,
        *,
        implied_volatility: float | None = None,
        iv_history: list[float] | pd.Series | None = None,
        lookback: int = 20,
    ) -> AnalysisResult:
        feature_set = self._features.build(prices, symbol=symbol)
        if feature_set.data.empty:
            return AnalysisResult(name="volatility", symbol=symbol, summary="No price data")

        features = feature_set.data
        hv = historical_volatility(features["close"], periods=lookback)
        rv = realized_volatility(features["close"].pct_change().dropna(), annualization=252)
        current_hv = float(hv.iloc[-1]) if not hv.empty and pd.notna(hv.iloc[-1]) else 0.0
        current_iv = float(implied_volatility) if implied_volatility is not None else current_hv

        ivr = 50.0
        ivp = 50.0
        if iv_history is not None and len(iv_history) > 0:
            hist = pd.Series(iv_history, dtype="float64").dropna()
            if not hist.empty:
                iv_low, iv_high = float(hist.min()), float(hist.max())
                ivr = max(0.0, min(100.0, (current_iv - iv_low) / max(iv_high - iv_low, 1e-10) * 100))
                ivp = float((hist <= current_iv).mean() * 100)

        parkinson = self._parkinson_volatility(features)
        garman_klass = self._garman_klass_volatility(features)

        expansion = current_iv > current_hv * 1.25 if current_hv > 0 else False
        contraction = current_iv < current_hv * 0.75 if current_hv > 0 else False
        regime = "High" if ivr >= 70 else "Low" if ivr <= 30 else "Normal"
        score = max(0.0, min(100.0, 50.0 + (current_iv - current_hv) / max(current_hv, 0.0001) * 50.0))

        metrics = {
            "atr": float(features["atr"].iloc[-1]) if pd.notna(features["atr"].iloc[-1]) else 0.0,
            "historical_volatility": current_hv,
            "realized_volatility": rv,
            "implied_volatility": current_iv,
            "iv_rank": ivr,
            "iv_percentile": ivp,
            "parkinson_volatility": parkinson,
            "garman_klass_volatility": garman_klass,
            "iv_expansion": expansion,
            "iv_contraction": contraction,
            "volatility_regime": regime,
        }

        signals = [regime]
        if expansion:
            signals.append("IV expanding above HV")
        if contraction:
            signals.append("IV contracting below HV")

        return AnalysisResult(
            name="volatility",
            symbol=symbol,
            summary=f"{symbol}: {regime} volatility regime.",
            metrics=metrics,
            scores={"volatility": score},
            signals=signals,
        )

    @staticmethod
    def _parkinson_volatility(df: pd.DataFrame, annualization: int = 252) -> float:
        if "high" not in df.columns or "low" not in df.columns:
            return 0.0
        high = df["high"].astype(float)
        low = df["low"].astype(float)
        valid = (high > 0) & (low > 0)
        if valid.sum() < 2:
            return 0.0
        log_hl = (high[valid] / low[valid]).apply(math.log)
        return float(math.sqrt((log_hl**2).sum() / (4 * len(log_hl) * math.log(2))) * math.sqrt(annualization) * 100)

    @staticmethod
    def _garman_klass_volatility(df: pd.DataFrame, annualization: int = 252) -> float:
        required = {"open", "high", "low", "close"}
        if not required.issubset(df.columns):
            return 0.0
        o = df["open"].astype(float)
        h = df["high"].astype(float)
        lo = df["low"].astype(float)
        c = df["close"].astype(float)
        valid = (o > 0) & (h > 0) & (lo > 0) & (c > 0)
        if valid.sum() < 2:
            return 0.0
        log_hl = (h[valid] / lo[valid]).apply(math.log) ** 2
        log_co = (c[valid] / o[valid]).apply(math.log) ** 2
        n = len(log_hl)
        return float(math.sqrt((log_hl.sum() / n + (math.log(2) - 1) * log_co.sum() / n) / (2 * math.log(2))) * math.sqrt(annualization) * 100)
