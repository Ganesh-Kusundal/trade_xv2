"""Core analytics contracts and feature construction."""

from analytics.core.feature_builder import FeatureBuilder
from analytics.core.instrument_analyzer import InstrumentAnalyzer
from analytics.core.models import AnalysisResult, FeatureSet, normalize_ohlcv
from analytics.core.providers import (
    CsvMarketDataProvider,
    DataFrameMarketDataProvider,
    GatewayMarketDataProvider,
    MarketDataProvider,
)

__all__ = [
    "AnalysisResult",
    "CsvMarketDataProvider",
    "DataFrameMarketDataProvider",
    "FeatureBuilder",
    "FeatureSet",
    "GatewayMarketDataProvider",
    "InstrumentAnalyzer",
    "MarketDataProvider",
    "normalize_ohlcv",
]
