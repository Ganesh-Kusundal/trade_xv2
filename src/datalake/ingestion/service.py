"""Unified Data Loading Service — single entry point for all ingestion operations.

This service layer consolidates the fragmented data loading functionality from
HistoricalDataLoader, IncrementalUpdater, and converter modules into a cohesive
interface that follows the Single Responsibility Principle.

Responsibilities:
- Provide a clean, high-level API for data loading operations
- Coordinate between different loading strategies (historical, incremental, conversion)
- Handle error recovery and retry logic
- Maintain consistency in data loading workflows
- Enforce data quality standards

Usage:
    from datalake.ingestion.service import DataLoadingService
    
    service = DataLoadingService(root="market_data")
    
    # Load historical data for a symbol
    service.load_symbol("RELIANCE", years=5)
    
    # Update all symbols in a universe
    service.update_universe("NIFTY500")
    
    # Convert legacy data formats
    service.convert_tradej_directory("/path/to/tradej/data")
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional, Dict, Any

from datalake.core import normalize_symbol
from datalake.ingestion.converter import convert_tradej_directory, convert_tradej_parquet
from datalake.storage.interfaces import DataLoadingServiceInterface

# Import original implementations to avoid circular dependency
import sys
import importlib

# Import the original classes using their module paths
loader_module = importlib.import_module('datalake.ingestion.loader')
updater_module = importlib.import_module('datalake.ingestion.updater')
_OriginalHistoricalDataLoader = loader_module.HistoricalDataLoader
_OriginalIncrementalUpdater = updater_module.IncrementalUpdater

logger = logging.getLogger(__name__)


class DataLoadingService(DataLoadingServiceInterface):
    """Unified service for all data loading operations."""
    
    def __init__(
        self,
        root: str = "market_data",
        catalog=None,
        max_workers: int = 4
    ) -> None:
        """Initialize the data loading service.
        
        Args:
            root: Root directory for data storage
            catalog: Optional data catalog for metadata tracking
            max_workers: Maximum workers for parallel operations
        """
        self._root = Path(root)
        self._catalog = catalog
        self._max_workers = max_workers
        
        # Initialize component services
        self._loader = _OriginalHistoricalDataLoader(root=root, catalog=catalog)
        self._updater = _OriginalIncrementalUpdater(root=root, catalog=catalog, loader=self._loader)
        
        logger.info("DataLoadingService initialized with root=%s", root)
    
    @property
    def root(self) -> Path:
        """Return the root data directory."""
        return self._root
    
    # -----------------------------------------------------------------------
    # High-Level Loading Operations
    # -----------------------------------------------------------------------
    
    def load_symbol(
        self,
        symbol: str,
        years: int = 5,
        timeframe: str = "1m",
        gateway=None,
        **kwargs
    ) -> Dict[str, Any]:
        """Load historical data for a single symbol.
        
        Args:
            symbol: Symbol to load (e.g., "RELIANCE")
            years: Number of years of history to load
            timeframe: Candle timeframe ("1m", "5m", "15m", "1h", "1d")
            gateway: Broker gateway for data fetching
            **kwargs: Additional arguments for the gateway
            
        Returns:
            Dictionary with loading results including row counts and status
        """
        symbol = normalize_symbol(symbol)
        logger.info("Loading %s years of %s data for %s", years, timeframe, symbol)
        
        try:
            result = self._loader.download_symbol(
                symbol, gateway, years, timeframe, **kwargs
            )
            logger.info("Successfully loaded %s: %s rows", symbol, result.get("rows_written", 0))
            return result
        except Exception as exc:
            logger.error("Failed to load %s: %s", symbol, exc)
            raise
    
    def load_universe(
        self,
        universe: str,
        years: int = 5,
        timeframe: str = "1m",
        gateway=None,
        **kwargs
    ) -> Dict[str, Any]:
        """Load historical data for all symbols in a universe.
        
        Args:
            universe: Universe name (e.g., "NIFTY500")
            years: Number of years of history to load
            timeframe: Candle timeframe
            gateway: Broker gateway for data fetching
            **kwargs: Additional arguments for the gateway
            
        Returns:
            Dictionary with overall results and per-symbol statistics
        """
        logger.info("Loading %s years of %s data for universe %s", years, timeframe, universe)
        
        try:
            result = self._loader.download_universe(
                universe, gateway, years, timeframe, **kwargs
            )
            logger.info("Successfully loaded universe %s: %s symbols", universe, len(result.get("symbols", [])))
            return result
        except Exception as exc:
            logger.error("Failed to load universe %s: %s", universe, exc)
            raise
    
    def update_daily(
        self,
        universe: str,
        gateway=None,
        **kwargs
    ) -> Dict[str, Any]:
        """Update all symbols in a universe with latest daily data.
        
        Args:
            universe: Universe name (e.g., "NIFTY500")
            gateway: Broker gateway for data fetching
            **kwargs: Additional arguments for the gateway
            
        Returns:
            Dictionary with update results and statistics
        """
        logger.info("Updating daily data for universe %s", universe)
        
        try:
            result = self._updater.update_daily(universe, gateway, **kwargs)
            logger.info("Successfully updated universe %s: %s symbols updated", 
                       universe, result.get("updated_count", 0))
            return result
        except Exception as exc:
            logger.error("Failed to update universe %s: %s", universe, exc)
            raise
    
    def update_symbol(
        self,
        symbol: str,
        gateway=None,
        **kwargs
    ) -> Dict[str, Any]:
        """Update a single symbol with latest data.
        
        Args:
            symbol: Symbol to update
            gateway: Broker gateway for data fetching
            **kwargs: Additional arguments for the gateway
            
        Returns:
            Dictionary with update results
        """
        symbol = normalize_symbol(symbol)
        logger.info("Updating daily data for %s", symbol)
        
        try:
            result = self._updater._update_symbol(symbol, gateway, **kwargs)
            logger.info("Successfully updated %s: %s rows", symbol, result.get("rows_written", 0))
            return result
        except Exception as exc:
            logger.error("Failed to update %s: %s", symbol, exc)
            raise
    
    # -----------------------------------------------------------------------
    # Data Conversion Operations
    # -----------------------------------------------------------------------
    
    def convert_tradej_directory(
        self,
        source_dir: str,
        target_root: Optional[str] = None,
        symbols: Optional[List[str]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Convert Trade_J directory to canonical format.
        
        Args:
            source_dir: Directory containing Trade_J Parquet files
            target_root: Target root directory (defaults to service root)
            symbols: Optional list of symbols to convert
            **kwargs: Additional conversion options
            
        Returns:
            Dictionary with conversion results
        """
        target_root = target_root or str(self._root)
        logger.info("Converting Trade_J directory %s to %s", source_dir, target_root)
        
        try:
            result = convert_tradej_directory(
                source_dir, target_root, symbols, **kwargs
            )
            logger.info("Successfully converted %s files", result.get("files_converted", 0))
            return result
        except Exception as exc:
            logger.error("Failed to convert Trade_J directory: %s", exc)
            raise
    
    def convert_tradej_parquet(
        self,
        source_file: str,
        target_root: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Convert a single Trade_J Parquet file to canonical format.
        
        Args:
            source_file: Path to Trade_J Parquet file
            target_root: Target root directory (defaults to service root)
            **kwargs: Additional conversion options
            
        Returns:
            Dictionary with conversion results
        """
        target_root = target_root or str(self._root)
        logger.info("Converting Trade_J file %s to %s", source_file, target_root)
        
        try:
            result = convert_tradej_parquet(source_file, target_root, **kwargs)
            logger.info("Successfully converted %s", source_file)
            return result
        except Exception as exc:
            logger.error("Failed to convert Trade_J file %s: %s", source_file, exc)
            raise
    
    # -----------------------------------------------------------------------
    # Data Quality Operations
    # -----------------------------------------------------------------------
    
    def repair_missing(
        self,
        symbol: str,
        timeframe: str = "1m",
        gateway=None,
        **kwargs
    ) -> Dict[str, Any]:
        """Repair missing data for a symbol.
        
        Args:
            symbol: Symbol to repair
            timeframe: Timeframe to check
            gateway: Broker gateway for data fetching
            **kwargs: Additional arguments for the gateway
            
        Returns:
            Dictionary with repair results
        """
        symbol = normalize_symbol(symbol)
        logger.info("Repairing missing data for %s (%s)", symbol, timeframe)
        
        try:
            result = self._loader.repair_missing(symbol, timeframe, gateway, **kwargs)
            logger.info("Successfully repaired %s: %s rows added", symbol, result.get("rows_added", 0))
            return result
        except Exception as exc:
            logger.error("Failed to repair %s: %s", symbol, exc)
            raise
    
    # -----------------------------------------------------------------------
    # Utility Methods
    # -----------------------------------------------------------------------
    
    def get_loader(self):
        """Get the underlying historical data loader."""
        return self._loader
    
    def get_updater(self):
        """Get the underlying incremental updater."""
        return self._updater


# Backward compatibility aliases
HistoricalDataLoader = DataLoadingService  # type: ignore
IncrementalUpdater = DataLoadingService  # type: ignore


__all__ = [
    "DataLoadingService",
    "HistoricalDataLoader",  # Backward compatibility
    "IncrementalUpdater",    # Backward compatibility
]