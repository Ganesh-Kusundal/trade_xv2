"""TradeXV2 Market Data Lake — Parquet + DuckDB.

Provides:
- Hive-partitioned Parquet storage for OHLCV bars
- DuckDB catalog for metadata and fast queries
- Research API for scanner/strategy/backtest
- Data quality tracking

Usage:
    from datalake import DataLake

    lake = DataLake()

    # Research API
    df = lake.history("RELIANCE", years=5)
    df = lake.universe("NIFTY500", lookback_days=365)

    # Loader
    lake.loader.download_symbol("TCS", years=5)
    lake.loader.download_universe("NIFTY500")

    # Quality
    report = lake.quality.check("RELIANCE")
"""

from datalake.storage.catalog import DataCatalog
from datalake.analytics.corporate_actions import CorporateActionStore
from datalake.ingestion.loader import HistoricalDataLoader
from datalake.quality.engine import DataQualityEngine
from datalake.quality.universe import UniverseQualityEngine
from datalake.research.api import ResearchAPI
from datalake.analytics.vwap import compute_daily_vwap, compute_vwap

__all__ = [
    "CorporateActionStore",
    "DataCatalog",
    "DataLake",
    "DataQualityEngine",
    "HistoricalDataLoader",
    "ResearchAPI",
    "UniverseQualityEngine",
    "compute_daily_vwap",
    "compute_vwap",
]


class DataLake:
    """Unified entry point for the market data lake."""

    def __init__(self, root: str | None = None) -> None:
        if root is None:
            from domain.ports.data_catalog import DEFAULT_DATA_PATHS
            root = DEFAULT_DATA_PATHS.lake_root
        self._root = root
        self._catalog = DataCatalog(root)
        self._quality = DataQualityEngine(root, self._catalog)
        self._loader = HistoricalDataLoader(root, self._catalog)
        self._api = ResearchAPI(root, self._catalog)

    @property
    def catalog(self) -> DataCatalog:
        return self._catalog

    @property
    def quality(self) -> DataQualityEngine:
        return self._quality

    @property
    def loader(self) -> HistoricalDataLoader:
        return self._loader

    # Research API shortcuts
    def history(self, symbol: str, years: int = 5, timeframe: str = "1m"):
        return self._api.history(symbol, years=years, timeframe=timeframe)

    def universe(self, universe: str = "NIFTY500", lookback_days: int = 365):
        return self._api.universe(universe, lookback_days=lookback_days)

    def scan(self, universe: str = "NIFTY500"):
        return self._api.scan(universe)
