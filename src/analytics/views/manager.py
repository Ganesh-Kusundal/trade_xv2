"""View Manager — orchestrates creation, refresh, and management of DuckDB analytics views."""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import duckdb

from analytics.views.base import BaseViews
from analytics.views.cache_manager import MATERIALIZED_DIR, VERSION_KEEP_COUNT, CacheManager
from analytics.views.features import FeatureViews
from analytics.views.options_views import OptionViews
from analytics.views.quality import QualityViews
from analytics.views.query_executor import QueryExecutor
from analytics.views.scanner import DAILY_LOOKBACK_DAYS, MIN_SYMBOLS_FOR_FULL_DAY, ScannerViews
from analytics.views.strategy import StrategyViews
from analytics.views.view_registry import ViewRegistry
from datalake.core.duckdb_utils import duckdb_connection, get_pool
from domain.ports.data_catalog import DEFAULT_CATALOG_PATH

logger = logging.getLogger(__name__)

# Re-export constants for public/test compatibility
__all__ = [
    "DAILY_LOOKBACK_DAYS",
    "MATERIALIZED_DIR",
    "MIN_SYMBOLS_FOR_FULL_DAY",
    "VERSION_KEEP_COUNT",
    "ViewManager",
]


class ViewManager:
    """Manages all DuckDB analytics views.

    Thin orchestrator that composes:
    - ViewRegistry (introspection / drop)
    - QueryExecutor (queries / benchmarks)
    - CacheManager (materialization)
    - Domain view layers (base, features, scanner, strategy, quality, options)

    Usage:
        vm = ViewManager()
        vm.create_all()
        vm.refresh()
        result = vm.query("SELECT * FROM v_top3_candidates")
    """

    def __init__(self, catalog_path: str | Path | None = None, read_only: bool = False) -> None:
        self._path = Path(catalog_path) if catalog_path else DEFAULT_CATALOG_PATH
        self._path.parent.mkdir(parents=True, exist_ok=True)
        MATERIALIZED_DIR.mkdir(parents=True, exist_ok=True)
        self._read_only = read_only
        self._conn: duckdb.DuckDBPyConnection | None = None

        # Compose extracted modules
        self._registry = ViewRegistry(catalog_path, read_only)
        self._executor = QueryExecutor(
            get_connection=lambda: self.conn,
            get_query_connection=self._query_connection,
            read_only=read_only,
        )
        self._cache = CacheManager()

        self.base = BaseViews()
        self.features = FeatureViews()
        self.scanner = ScannerViews()
        self.strategy = StrategyViews()
        self.quality = QualityViews()
        self.options = OptionViews()

    @property
    def conn(self) -> duckdb.DuckDBPyConnection:
        """Return the cached read-write connection for materialization and DDL."""
        if self._conn is None:
            self._conn = get_pool().acquire(self._path, read_only=False)
        return self._conn

    @contextmanager
    def _query_connection(self) -> Iterator[duckdb.DuckDBPyConnection]:
        """Yield a connection for read queries (RO pool when read_only)."""
        if self._read_only:
            with duckdb_connection(self._path, read_only=True) as conn:
                yield conn
        else:
            yield self.conn

    def close(self) -> None:
        """Release all cached connections."""
        if self._conn is not None:
            get_pool().release(self._path)
            self._conn = None
        self._registry.close()

    # ─── Materialization (via CacheManager) ──────────────────────────────────

    def materialize(self, table_name: str, sql: str, partition_by: str | None = None) -> float:
        """Delegate to CacheManager."""
        return self._cache.materialize(table_name, sql, self.conn, partition_by)

    def register_materialized(self, table_name: str, partition_by: str | None = None) -> None:
        """Delegate to CacheManager."""
        self._cache.register_materialized(table_name, self.conn, partition_by)

    def drop_materialized(self, table_name: str) -> None:
        """Delegate to CacheManager."""
        self._cache.drop_materialized(table_name, self.conn)

    # ─── Introspection (via ViewRegistry) ────────────────────────────────────

    def list_views(self) -> list[dict]:
        """Delegate to ViewRegistry."""
        return self._registry.list_views()

    def view_exists(self, view_name: str) -> bool:
        """Delegate to ViewRegistry."""
        return self._registry.view_exists(view_name)

    def table_exists(self, table_name: str) -> bool:
        """Delegate to ViewRegistry."""
        return self._registry.table_exists(table_name)

    def view_columns(self, view_name: str) -> list[str]:
        """Delegate to ViewRegistry."""
        return self._registry.view_columns(view_name)

    def view_count(self) -> int:
        """Delegate to ViewRegistry."""
        return self._registry.view_count()

    def table_count(self) -> int:
        """Delegate to ViewRegistry."""
        return self._registry.table_count()

    # ─── Query Execution (via QueryExecutor) ─────────────────────────────────

    def query(self, sql: str, params: list | None = None) -> duckdb.DuckDBPyRelation:
        """Delegate to QueryExecutor."""
        return self._executor.query(sql, params)

    def query_df(self, sql: str, params: list | None = None) -> Any:
        """Delegate to QueryExecutor."""
        return self._executor.query_df(sql, params)

    def query_scalar(self, sql: str, params: list | None = None) -> Any:
        """Delegate to QueryExecutor."""
        return self._executor.query_scalar(sql, params)

    def benchmark(self, sql: str, iterations: int = 3) -> dict:
        """Delegate to QueryExecutor."""
        return self._executor.benchmark(sql, iterations)

    def benchmark_all(self) -> list[dict]:
        """Delegate to QueryExecutor with registry existence checks."""
        return self._executor.benchmark_all(self.view_exists, self.table_exists)

    # ─── View Lifecycle Orchestration ────────────────────────────────────────

    def create_all(self) -> dict[str, float]:
        """Create all analytics views. Returns timing for each layer."""
        timings: dict[str, float] = {}

        layers = [
            ("base", self.base.create_views),
            ("features", self.features.create_views),
            (
                "materialize",
                lambda conn: self._cache.materialize_tables(
                    self.scanner.materialization_sql(), conn
                ),
            ),
            ("scanner", self.scanner.create_views),
            ("strategy", self.strategy.create_views),
            (
                "materialize_quality",
                lambda conn: self._cache.materialize_tables(
                    self.quality.materialization_sql(), conn
                ),
            ),
            ("quality", self.quality.create_views),
            (
                "materialize_options",
                lambda conn: self._cache.materialize_tables(
                    self.options.materialization_sql(), conn
                ),
            ),
            ("options", self.options.create_views),
        ]

        for name, creator in layers:
            start = time.perf_counter()
            try:
                creator(self.conn)
                elapsed = time.perf_counter() - start
                timings[name] = elapsed
                logger.info("Created %s views in %.2fs", name, elapsed)
            except Exception as exc:
                logger.error("Failed to create %s views: %s", name, exc)
                timings[name] = -1.0

        return timings

    def drop_all(self) -> None:
        """Drop all analytics views and materialized tables (via ViewRegistry)."""
        self._registry.drop_all_views()

    def refresh(self) -> dict[str, float]:
        """Refresh all views (drop + recreate)."""
        self.drop_all()
        return self.create_all()
