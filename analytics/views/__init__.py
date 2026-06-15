"""DuckDB Analytics Views — production-grade analytical layer."""

from analytics.views.manager import ViewManager
from analytics.views.base import BaseViews
from analytics.views.features import FeatureViews
from analytics.views.scanner import ScannerViews
from analytics.views.strategy import StrategyViews
from analytics.views.quality import QualityViews

__all__ = [
    "ViewManager",
    "BaseViews",
    "FeatureViews",
    "ScannerViews",
    "StrategyViews",
    "QualityViews",
]
