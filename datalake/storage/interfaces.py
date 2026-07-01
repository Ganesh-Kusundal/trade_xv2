"""Storage Layer Interfaces — Abstract base classes for storage operations.

Defines the contracts that storage implementations must fulfill.
These interfaces enforce module boundaries and prevent direct access to internals.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Any

import pandas as pd


class MarketDataStorage(ABC):
    """Abstract interface for market data storage operations."""
    
    @abstractmethod
    def load_candles(
        self, 
        symbol: str, 
        timeframe: str,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None
    ) -> pd.DataFrame:
        """Load historical candle data for a symbol."""
        pass
    
    @abstractmethod
    def resample(self, df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
        """Resample candle data to a different timeframe."""
        pass
    
    @abstractmethod
    def get_candle_path(self, symbol: str, timeframe: str = "1m") -> Path:
        """Get the filesystem path for a symbol's candle data."""
        pass


class DataCatalogInterface(ABC):
    """Abstract interface for data catalog operations."""
    
    @abstractmethod
    def get_symbols(self, exchange: str = "NSE") -> list[str]:
        """Get list of all symbols in the catalog."""
        pass
    
    @abstractmethod
    def get_symbol_metadata(self, symbol: str) -> dict[str, Any]:
        """Get metadata for a specific symbol."""
        pass
    
    @abstractmethod
    def update_symbol_metadata(self, symbol: str, metadata: dict[str, Any]) -> None:
        """Update metadata for a symbol."""
        pass


class DataQualityInterface(ABC):
    """Abstract interface for data quality operations."""
    
    @abstractmethod
    def validate_candles(
        self, 
        df: pd.DataFrame,
        symbol: str = "",
        drop_invalid: bool = True
    ) -> pd.DataFrame:
        """Validate candle data quality."""
        pass
    
    @abstractmethod
    def check_symbol_quality(self, symbol: str) -> dict[str, Any]:
        """Check data quality for a symbol."""
        pass


class DataLoadingServiceInterface(ABC):
    """Abstract interface for data loading operations."""
    
    @abstractmethod
    def load_symbol(
        self,
        symbol: str,
        years: int = 5,
        timeframe: str = "1m",
        gateway=None,
        **kwargs
    ) -> dict[str, Any]:
        """Load historical data for a symbol."""
        pass
    
    @abstractmethod
    def load_universe(
        self,
        universe: str,
        years: int = 5,
        timeframe: str = "1m",
        gateway=None,
        **kwargs
    ) -> dict[str, Any]:
        """Load historical data for all symbols in a universe."""
        pass
    
    @abstractmethod
    def update_daily(
        self,
        universe: str,
        gateway=None,
        **kwargs
    ) -> dict[str, Any]:
        """Update all symbols in a universe with latest daily data."""
        pass


__all__ = [
    "MarketDataStorage",
    "DataCatalogInterface",
    "DataQualityInterface",
    "DataLoadingServiceInterface"
]