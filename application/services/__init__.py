"""Cross-broker shared services (HistoricalDataService, etc.).

Canonical location: ``application.services``.
"""

from __future__ import annotations

from .data_validator import (
    DataQualityValidator,
    Issue,
    ValidationReport,
)
from .download_engine import (
    DownloadConfig,
    DownloadProgress,
    HistoricalDownloadEngine,
)
from .historical_data import (
    GapRange,
    HistoricalDataRequest,
    HistoricalDataService,
    SupportsHistoricalCandles,
)
from .instrument_registry import (
    CanonicalInstrument,
    CanonicalInstrumentRegistry,
)
from .production_readiness import (
    ProductionReadinessChecker,
    ProductionReadinessError,
    ReadinessCheck,
    ReadinessReport,
)

__all__ = [
    "CanonicalInstrument",
    "CanonicalInstrumentRegistry",
    "DataQualityValidator",
    "DownloadConfig",
    "DownloadProgress",
    "GapRange",
    "HistoricalDataRequest",
    "HistoricalDataService",
    "HistoricalDownloadEngine",
    "Issue",
    "ProductionReadinessChecker",
    "ProductionReadinessError",
    "ReadinessCheck",
    "ReadinessReport",
    "SupportsHistoricalCandles",
    "ValidationReport",
]
