"""TradeXV2 Market Data Lake — Parquet + DuckDB.

Provides:
- Hive-partitioned Parquet storage for OHLCV bars
- DuckDB catalog for metadata and fast queries
- Research API for scanner/strategy/backtest
- Incremental update engine
- Data quality tracking

Usage:
    from datalake import DataLake

    lake = DataLake("market_data")

    # Research API
    df = lake.history("RELIANCE", years=5)
    df = lake.universe("NIFTY500", lookback_days=365)

    # Loader
    lake.loader.download_symbol("TCS", years=5)
    lake.loader.download_universe("NIFTY500")

    # Quality
    report = lake.quality.check("RELIANCE")
"""

from datalake.research import ResearchAPI
from datalake.catalog import DataCatalog
from datalake.quality import DataQualityEngine
from datalake.loader import HistoricalDataLoader
from datalake.updater import IncrementalUpdater

__all__ = [
    "DataLake",
    "ResearchAPI",
    "DataCatalog",
    "DataQualityEngine",
    "HistoricalDataLoader",
    "IncrementalUpdater",
]


class DataLake:
    """Unified entry point for the market data lake."""

    def __init__(self, root: str = "market_data") -> None:
        self._root = root
        self._catalog = DataCatalog(root)
        self._quality = DataQualityEngine(root, self._catalog)
        self._loader = HistoricalDataLoader(root, self._catalog)
        self._updater = IncrementalUpdater(root, self._catalog, self._loader)
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

    @property
    def updater(self) -> IncrementalUpdater:
        return self._updater

    # Research API shortcuts
    def history(self, symbol: str, years: int = 5, timeframe: str = "1m"):
        return self._api.history(symbol, years=years, timeframe=timeframe)

    def universe(self, universe: str = "NIFTY500", lookback_days: int = 365):
        return self._api.universe(universe, lookback_days=lookback_days)

    def scan(self, universe: str = "NIFTY500"):
        return self._api.scan(universe)
