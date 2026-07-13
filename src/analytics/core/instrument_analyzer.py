"""InstrumentAnalyzer — instrument-aware analytics facade.

Provides analytics operations that accept Instrument as the
entry point, replacing raw symbol+exchange strings.

Usage::

    from domain.aggregates import Instrument
    from analytics.core.instrument_analyzer import InstrumentAnalyzer

    analyzer = InstrumentAnalyzer()
    result = analyzer.analyze_stock(instrument, lookback_days=120)
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from analytics.core.feature_builder import FeatureBuilder
from analytics.core.models import AnalysisResult
from analytics.options.options_analytics import OptionsAnalytics
from analytics.stocks.stock_analytics import StockAnalytics
from analytics.volatility.volatility_analytics import VolatilityAnalytics
from domain.instruments.instrument import Instrument

logger = logging.getLogger(__name__)


class InstrumentAnalyzer:
    """Instrument-aware analytics facade.

    Accepts Instrument as the primary entry point for all
    analytics operations.  Delegates to the instrument's own data
    methods (get_history, get_option_chain) for data access.
    """

    def __init__(self) -> None:
        self._feature_builder = FeatureBuilder()
        self._stock_engine = StockAnalytics(self._feature_builder)
        self._volatility_engine = VolatilityAnalytics(self._feature_builder)
        self._options_engine = OptionsAnalytics()

    def analyze_stock(
        self,
        instrument: Instrument,
        *,
        lookback_days: int = 120,
        timeframe: str = "1D",
    ) -> AnalysisResult:
        """Run stock analysis on an instrument."""
        df = instrument.get_history(
            timeframe=timeframe,
            lookback_days=lookback_days,
        )
        if df.empty:
            return AnalysisResult(
                name="stock",
                symbol=instrument.symbol,
                summary=f"No data available for {instrument.symbol}.",
            )
        return self._stock_engine.analyze(instrument.symbol, df)

    def analyze_volatility(
        self,
        instrument: Instrument,
        *,
        lookback_days: int = 120,
        timeframe: str = "1D",
        implied_volatility: float | None = None,
    ) -> AnalysisResult:
        """Run volatility analysis on an instrument."""
        df = instrument.get_history(
            timeframe=timeframe,
            lookback_days=lookback_days,
        )
        if df.empty:
            return AnalysisResult(
                name="volatility",
                symbol=instrument.symbol,
                summary=f"No data available for {instrument.symbol}.",
            )
        return self._volatility_engine.analyze(
            instrument.symbol,
            df,
            implied_volatility=implied_volatility,
        )

    def analyze_options(
        self,
        instrument: Instrument,
        *,
        expiry: str | None = None,
        spot_price: float | None = None,
    ) -> AnalysisResult:
        """Run options analysis on an instrument (must be an underlying)."""
        chain = instrument.get_option_chain()
        if not chain or not chain.strikes:
            return AnalysisResult(
                name="options",
                symbol=instrument.symbol,
                summary=f"No option chain available for {instrument.symbol}.",
            )
        return self._options_engine.analyze(
            instrument.symbol,
            chain.to_dict(),
            spot_price=spot_price,
        )

    def build_features(
        self,
        instrument: Instrument,
        *,
        lookback_days: int = 120,
        timeframe: str = "1D",
    ) -> AnalysisResult:
        """Build feature set for an instrument."""
        df = instrument.get_history(
            timeframe=timeframe,
            lookback_days=lookback_days,
        )
        if df.empty:
            return AnalysisResult(
                name="features",
                symbol=instrument.symbol,
                summary=f"No data available for {instrument.symbol}.",
            )
        feature_set = self._feature_builder.build(df, symbol=instrument.symbol)
        return AnalysisResult(
            name="features",
            symbol=instrument.symbol,
            summary=f"Built {len(feature_set.data.columns)} features for {instrument.symbol}.",
            metrics=feature_set.summary,
        )

    def __repr__(self) -> str:
        return "InstrumentAnalyzer()"
