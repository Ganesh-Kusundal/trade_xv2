"""Centralized constants for the datalake module.

All shared constants, magic values, and configuration parameters should be
defined here to prevent duplication and ensure consistency across the codebase.
"""

from __future__ import annotations

from pathlib import Path

# Re-export from domain canonical home for backward compatibility.
from domain.ports.data_catalog import DEFAULT_CATALOG_PATH, DEFAULT_DATA_ROOT  # noqa: F401

CURATED_ROOT: str = "market_data/curated"
"""Root directory for curated (date-partitioned) data layout."""

# Timeframes
SUPPORTED_TIMEFRAMES = frozenset({"1m", "5m", "15m", "1h", "1d"})
"""Supported candle timeframes."""

DEFAULT_TIMEFRAME: str = "1m"
"""Default timeframe for operations."""

# Data validation
MAX_PRICE: float = 10_000_000.0
"""Maximum valid price value (1 crore per share sanity cap)."""

MIN_VOLUME: int = 0
"""Minimum valid volume value."""

# Caching
DEFAULT_CACHE_TTL: int = 300  # 5 minutes in seconds
"""Default cache time-to-live for various caches."""

DEFAULT_CACHE_SIZE: int = 512
"""Default maximum cache size for various caches."""

# Concurrent operations
BATCH_MAX_WORKERS: int = 4
"""Default maximum workers for batch operations."""

# File formats
DEFAULT_COMPRESSION: str = "snappy"
"""Default compression algorithm for Parquet files."""

# Data quality
EXPECTED_CANDLES_PER_DAY: int = 375
"""Expected number of 1-minute candles in a full trading day."""

# NSE trading session length (9:15–15:30 IST)
TRADING_MINUTES_PER_DAY: int = EXPECTED_CANDLES_PER_DAY
"""Total traded minute-marks in a full session; alias of EXPECTED_CANDLES_PER_DAY."""

# NSE trading hours
MARKET_OPEN_HOUR: int = 9
"""Market open hour (IST)."""
MARKET_OPEN_MINUTE: int = 15
"""Market open minute (IST)."""
MARKET_CLOSE_HOUR: int = 15
"""Market close hour (IST)."""
MARKET_CLOSE_MINUTE: int = 30
"""Market close minute (IST)."""

__all__ = [
    "DEFAULT_DATA_ROOT",
    "CURATED_ROOT",
    "SUPPORTED_TIMEFRAMES",
    "DEFAULT_TIMEFRAME",
    "MAX_PRICE",
    "MIN_VOLUME",
    "DEFAULT_CACHE_TTL",
    "DEFAULT_CACHE_SIZE",
    "BATCH_MAX_WORKERS",
    "DEFAULT_COMPRESSION",
    "DEFAULT_CATALOG_PATH",
    "EXPECTED_CANDLES_PER_DAY",
    "TRADING_MINUTES_PER_DAY",
    "MARKET_OPEN_HOUR",
    "MARKET_OPEN_MINUTE",
    "MARKET_CLOSE_HOUR",
    "MARKET_CLOSE_MINUTE",
]