"""Centralized constants for the datalake module.

All shared constants, magic values, and configuration parameters should be
defined here to prevent duplication and ensure consistency across the codebase.
"""

from __future__ import annotations

from pathlib import Path

# Re-export from domain canonical home for backward compatibility.
from domain.ports.data_catalog import DEFAULT_CATALOG_PATH, DEFAULT_DATA_ROOT  # noqa: F401
from domain.ports.data_catalog import DEFAULT_DATA_PATHS  # noqa: F401

CURATED_ROOT: str = DEFAULT_DATA_PATHS.curated_root
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

# Data quality — session constants derived from the active exchange calendar
# via datalake.exchange_registry.  The NSE-specific hardcoding has been removed
# (ADR-005 / G3).  Import from exchange_registry for new code.

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
]