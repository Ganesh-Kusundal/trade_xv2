"""Data catalog ports — constants and protocols for data lake access.

Analytics and other consumer layers import from here instead of reaching
into ``datalake.core.*`` internals. The concrete implementation is wired
by the composition root.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, ContextManager, Protocol, runtime_checkable

# Canonical constants — single source of truth for all consumers.
# These are the legacy defaults; prefer DataPaths for new code.
DEFAULT_DATA_ROOT: str = "data/lake"
"""Root directory for market data storage (data lake)."""

DEFAULT_CATALOG_PATH: Path = Path("data/lake/catalog.duckdb")
"""Default path for DuckDB catalog database."""


@dataclass(frozen=True)
class DataPaths:
    """Centralized, injectable paths for all storage roots.

    Separates three concerns that the old ``market_data/`` directory conflated:

    - **lake_root**: Parquet OHLCV / options / indices (large, append-heavy)
    - **state_root**: OMS SQLite, execution ledger, event log, research cache
    - **catalog_path**: Single DuckDB catalog (must be under lake_root)

    After running ``scripts/migrate/split_market_data.py``, defaults point
    at the new split layout. Override via ``AppConfig`` or environment
    variables for custom deployments.
    """

    lake_root: str = "data/lake"
    state_root: str = "data/state"
    catalog_path: Path = Path("data/lake/catalog.duckdb")

    # ── Derived paths (read-only) ───────────────────────────────────

    @property
    def lake_path(self) -> Path:
        return Path(self.lake_root)

    @property
    def state_path(self) -> Path:
        return Path(self.state_root)

    @property
    def oms_orders_path(self) -> Path:
        return Path(self.state_root) / "oms" / "orders.sqlite"

    @property
    def execution_ledger_path(self) -> Path:
        return Path(self.state_root) / "oms" / "execution_ledger.sqlite"

    @property
    def events_dir(self) -> Path:
        return Path(self.state_root) / "events"

    @property
    def backtest_results_path(self) -> Path:
        return Path(self.state_root) / "research" / "backtest_results.sqlite"

    @property
    def journal_path(self) -> Path:
        return Path(self.state_root) / "research" / "journal.sqlite"

    @property
    def live_snapshot_path(self) -> Path:
        return Path(self.state_root) / "live_snapshot.json"

    @property
    def curated_root(self) -> str:
        return str(Path(self.lake_root) / "curated")

    @property
    def features_root(self) -> Path:
        return Path(self.lake_root) / "features"

    @property
    def options_greeks_root(self) -> Path:
        return Path(self.lake_root) / "options" / "greeks"

    @property
    def research_datasets_root(self) -> Path:
        return Path(self.state_root) / "research_datasets"


# Module-level default instance for backward compatibility.
# New code should receive DataPaths via injection, not import this.
DEFAULT_DATA_PATHS = DataPaths()


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
