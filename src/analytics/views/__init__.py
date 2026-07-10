"""DuckDB Analytics Views — production-grade analytical layer."""

from analytics.views.base import BaseViews
from analytics.views.features import FeatureViews
from analytics.views.manager import ViewManager
from analytics.views.quality import QualityViews
from analytics.views.scanner import ScannerViews
from analytics.views.strategy import StrategyViews

__all__ = [
    "BaseViews",
    "FeatureViews",
    "QualityViews",
    "ScannerViews",
    "StrategyViews",
    "ViewManager",
]
