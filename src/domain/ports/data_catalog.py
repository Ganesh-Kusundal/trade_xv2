"""Data catalog ports — constants and protocols for data lake access.

Analytics and other consumer layers import from here instead of reaching
into ``datalake.core.*`` internals. The concrete implementation is wired
by the composition root.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ContextManager, Protocol, runtime_checkable

# Canonical constants — single source of truth for all consumers.
DEFAULT_DATA_ROOT: str = "market_data"
"""Root directory for market data storage."""

DEFAULT_CATALOG_PATH: Path = Path("market_data/catalog.duckdb")
"""Default path for DuckDB catalog database."""


@runtime_checkable
class DuckDBCatalogPort(Protocol):
    """Protocol for DuckDB connection pool access.

    Implemented by ``datalake.core.duckdb_utils`` singletons.
    """

    def get_pool(self) -> Any:
        """Return the read-write DuckDB connection pool."""
        ...

    def get_read_pool(self) -> Any:
        """Return the read-only DuckDB connection pool."""
        ...

    def duckdb_connection(self, *, read_only: bool = False) -> ContextManager:
        """Context manager that yields a DuckDB connection."""
        ...
