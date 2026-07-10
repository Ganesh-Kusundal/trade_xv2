"""Back-compat re-export of historical data service.

Implementation lives in ``infrastructure.historical_data`` so broker
packages can import without depending on ``application``.
"""

from infrastructure.historical_data import (
    GapRange,
    HistoricalDataRequest,
    HistoricalDataService,
    SupportsHistoricalCandles,
)

__all__ = [
    "GapRange",
    "HistoricalDataRequest",
    "HistoricalDataService",
    "SupportsHistoricalCandles",
]
