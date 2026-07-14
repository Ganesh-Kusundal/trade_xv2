"""Centralized constants for the datalake module.

All shared constants, magic values, and configuration parameters should be
defined here to prevent duplication and ensure consistency across the codebase.
"""

from __future__ import annotations

from pathlib import Path

# Re-export from domain canonical home for backward compatibility.
from domain.constants import BATCH_MAX_WORKERS, DEFAULT_STORAGE_TIMEFRAME  # noqa: F401
from domain.ports.data_catalog import DEFAULT_CATALOG_PATH, DEFAULT_DATA_ROOT  # noqa: F401
from domain.ports.data_catalog import DEFAULT_DATA_PATHS  # noqa: F401

CURATED_ROOT: str = DEFAULT_DATA_PATHS.curated_root
"""Root directory for curated (date-partitioned) data layout."""

# Timeframes
SUPPORTED_TIMEFRAMES = frozenset({"1m", "5m", "15m", "1h", "1d"})
"""Supported candle timeframes."""

#: Deprecated alias of :data:`domain.constants.DEFAULT_STORAGE_TIMEFRAME`.
#: The datalake default timeframe is the *storage* granularity (minute bars);
#: it is distinct from the analysis default ``domain.constants.DEFAULT_TIMEFRAME``
#: (``"1D"``). Prefer importing ``DEFAULT_STORAGE_TIMEFRAME`` directly.
DEFAULT_TIMEFRAME: str = DEFAULT_STORAGE_TIMEFRAME

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
    "DEFAULT_STORAGE_TIMEFRAME",
    "DEFAULT_TIMEFRAME",
    "MAX_PRICE",
    "MIN_VOLUME",
    "DEFAULT_CACHE_TTL",
    "DEFAULT_CACHE_SIZE",
    "BATCH_MAX_WORKERS",
    "DEFAULT_COMPRESSION",
    "DEFAULT_CATALOG_PATH",
]