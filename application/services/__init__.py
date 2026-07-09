"""Cross-broker shared services (HistoricalDataService, etc.).

Canonical location: ``tradex.runtime.services``.
"""

from __future__ import annotations

from tradex.runtime.services.data_validator import (
    DataQualityValidator,
    Issue,
    ValidationReport,
)
from tradex.runtime.services.download_engine import (
    DownloadConfig,
    DownloadProgress,
    HistoricalDownloadEngine,
)
from tradex.runtime.services.historical_data import (
    GapRange,
    HistoricalDataRequest,
    HistoricalDataService,
    SupportsHistoricalCandles,
)
from tradex.runtime.services.instrument_registry import (
    CanonicalInstrument,
    CanonicalInstrumentRegistry,
)
from tradex.runtime.services.production_readiness import (
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
