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
from analytics.views.cache_manager import CacheManager
from analytics.views.features import FeatureViews
from analytics.views.options_views import OptionViews
from analytics.views.quality import QualityViews
from analytics.views.query_executor import QueryExecutor
from analytics.views.scanner import ScannerViews
from analytics.views.strategy import StrategyViews
from analytics.views.view_registry import ViewRegistry
from datalake.duckdb_utils import DEFAULT_CATALOG_PATH, duckdb_connection, get_pool
from datalake.options_analytics_sql import SQL_M_IV_SURFACE, SQL_M_MAX_PAIN, SQL_M_PCR

logger = logging.getLogger(__name__)

MATERIALIZED_DIR = Path("analytics_cache")
VERSION_KEEP_COUNT = 3

# Named constants for magic numbers
MIN_SYMBOLS_FOR_FULL_DAY = 100  # minimum distinct symbols to consider a day "full"
DAILY_LOOKBACK_DAYS = 50  # days of daily candles for indicator warmup
TRADING_MINUTES_PER_DAY = 375  # NSE market hours: 9:15-15:30 = 375 minutes
TRADING_MINUTES_PARTIAL = 345  # threshold for "PARTIAL" day classification


class ViewManager:
    """Manages all DuckDB analytics views.

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
        self._executor = QueryExecutor(catalog_path, read_only)
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

    def materialize(self, table_name: str, sql: str, partition_by: str | None = None) -> float:
        """Delegate to CacheManager."""
        return self._cache.materialize(table_name, sql, self.conn, partition_by)

    def register_materialized(self, table_name: str, partition_by: str | None = None) -> None:
        """Delegate to CacheManager."""
        self._cache.register_materialized(table_name, self.conn, partition_by)

    def drop_materialized(self, table_name: str) -> None:
        """Delegate to CacheManager."""
        self._cache.drop_materialized(table_name, self.conn)

    # ─── Delegated Introspection (via ViewRegistry) ───────────────────────────

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

    # ─── Delegated Query Execution (via QueryExecutor) ────────────────────────

    def query(self, sql: str, params: list | None = None) -> list:
        """Delegate to QueryExecutor."""
        return self._executor.query(sql, params)

    def query_df(self, sql: str, params: list | None = None):
        """Delegate to QueryExecutor."""
        return self._executor.query_df(sql, params)

    def query_scalar(self, sql: str, params: list | None = None):
        """Delegate to QueryExecutor."""
        return self._executor.query_scalar(sql, params)

    # ─── Materialization ─────────────────────────────────────────────────────

    def materialize(self, table_name: str, sql: str, partition_by: str | None = None) -> float:
        """Materialize a query result into a versioned Parquet table.

        Writes to a timestamped directory first, then atomically promotes the
        new version to "latest". Old versions are retained (see ``VERSION_KEEP_COUNT``)
        so readers always see a consistent snapshot.
        """
        version_dir = MATERIALIZED_DIR / "versions" / table_name
        version_dir.mkdir(parents=True, exist_ok=True)
        version_ts = str(int(time.time() * 1_000_000))

        start = time.perf_counter()

        if partition_by:
            part_dir = version_dir / version_ts
            part_dir.mkdir(parents=True, exist_ok=True)
            self.conn.execute(f"""
                COPY ({sql}) TO '{part_dir}'
                (FORMAT PARQUET, PARTITION_BY ({partition_by}))
            """)
            self._write_latest(table_name, f"versions/{table_name}/{version_ts}", partitioned=True)
        else:
            parquet_path = version_dir / f"{version_ts}.parquet"
            self.conn.execute(f"""
                COPY ({sql}) TO '{parquet_path}'
                (FORMAT PARQUET, COMPRESSION 'SNAPPY')
            """)
            self._write_latest(
                table_name, f"versions/{table_name}/{version_ts}.parquet", partitioned=False
            )

        self._cleanup_old_versions(table_name)

        elapsed = time.perf_counter() - start
        logger.info("Materialized %s version %s in %.2fs", table_name, version_ts, elapsed)
        return elapsed

    def _write_latest(self, table_name: str, version_path: str, partitioned: bool) -> None:
        import json

        latest_file = MATERIALIZED_DIR / "versions" / table_name / "latest.json"
        latest_file.write_text(json.dumps({"path": version_path, "partitioned": partitioned}))

    def _read_latest(self, table_name: str) -> dict[str, Any] | None:
        import json

        latest_file = MATERIALIZED_DIR / "versions" / table_name / "latest.json"
        if not latest_file.exists():
            return None
        try:
            return json.loads(latest_file.read_text())
        except Exception:
            return None

    def _cleanup_old_versions(self, table_name: str) -> None:
        version_dir = MATERIALIZED_DIR / "versions" / table_name
        if not version_dir.exists():
            return
        entries = sorted(
            [p for p in version_dir.iterdir() if p.name != "latest.json"],
            key=lambda p: p.stat().st_mtime,
        )
        to_remove = entries[:-VERSION_KEEP_COUNT]
        import shutil

        for entry in to_remove:
            try:
                if entry.is_dir():
                    shutil.rmtree(entry)
                else:
                    entry.unlink()
            except Exception as exc:
                logger.warning("Failed to remove old materialized version %s: %s", entry, exc)

    def register_materialized(self, table_name: str, partition_by: str | None = None) -> None:
        """Register the latest materialized Parquet table as a DuckDB table.

        Creates a new table with a temporary name, then atomically swaps it in
        via ``ALTER TABLE ... RENAME TO`` so readers never see a missing table.
        """
        latest = self._read_latest(table_name)
        if latest is None:
            return

        version_path = MATERIALIZED_DIR / latest["path"]
        if not version_path.exists():
            return

        temp_table = f"{table_name}_new_{int(time.time() * 1_000_000)}"
        try:
            if latest.get("partitioned") or partition_by:
                sql = (
                    f"CREATE TABLE {temp_table} AS "
                    "SELECT * FROM read_parquet(?, hive_partitioning=true)"
                )
                self.conn.execute(sql, [f"{version_path}/**/*.parquet"])
            else:
                sql = (
                    f"CREATE TABLE {temp_table} AS "
                    "SELECT * FROM read_parquet(?)"
                )
                self.conn.execute(sql, [str(version_path)])
            # Atomic swap: drop old, rename new.
            self.conn.execute(f"DROP TABLE IF EXISTS {table_name}")
            self.conn.execute(f"ALTER TABLE {temp_table} RENAME TO {table_name}")
        except Exception:
            self.conn.execute(f"DROP TABLE IF EXISTS {temp_table}")
            raise

    def drop_materialized(self, table_name: str) -> None:
        """Drop a materialized table and remove all its versions."""
        self.conn.execute(f"DROP TABLE IF EXISTS {table_name}")
        version_dir = MATERIALIZED_DIR / "versions" / table_name
        if version_dir.exists():
            import shutil

            shutil.rmtree(version_dir)

    # ─── View Creation ───────────────────────────────────────────────────────

    def create_all(self) -> dict[str, float]:
        """Create all analytics views. Returns timing for each layer."""
        timings: dict[str, float] = {}

        layers = [
            ("base", self.base.create_views),
            ("features", self.features.create_views),
            ("materialize", self._materialize_intermediates),
            ("scanner", self.scanner.create_views),
            ("strategy", self.strategy.create_views),
            ("materialize_quality", self._materialize_quality),
            ("quality", self.quality.create_views),
            ("materialize_options", self._materialize_options),
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

    def _materialize_intermediates(self, conn: duckdb.DuckDBPyConnection) -> None:
        """Materialize intermediate tables for intraday trading.

        Strategy:
        - m_intraday: Current day's 1m candles (~187K rows)
        - m_recent_daily: Last 50 days daily candles for indicator warmup (~25K rows)
        - m_symbol_snapshot: Latest candle per symbol with indicators (~500 rows)
        """
        tables = [
            # ─── Intraday: Current day's 1m candles ────────────────────────────
            # Use the most recent date with >= 100 symbols (full trading day)
            (
                "m_intraday",
                """
                WITH latest_full_day AS (
                    SELECT CAST(timestamp AS DATE) as trade_date
                    FROM v_candles_1m
                    GROUP BY CAST(timestamp AS DATE)
                    HAVING COUNT(DISTINCT symbol) >= 100
                    ORDER BY trade_date DESC
                    LIMIT 1
                )
                SELECT
                    i.timestamp,
                    i.symbol,
                    i.open,
                    i.high,
                    i.low,
                    i.close,
                    i.volume,
                    i.oi
                FROM v_candles_1m i
                INNER JOIN latest_full_day d ON CAST(i.timestamp AS DATE) = d.trade_date
            """,
            ),
            # ─── Recent daily: Last 50 days for indicator warmup ────────────────
            (
                "m_recent_daily",
                """
                WITH daily AS (
                    SELECT
                        CAST(timestamp AS DATE) as trade_date,
                        symbol,
                        FIRST(open ORDER BY timestamp) as open,
                        MAX(high) as high,
                        MIN(low) as low,
                        LAST(close ORDER BY timestamp) as close,
                        SUM(volume) as volume
                    FROM v_candles_1m
                    WHERE CAST(timestamp AS DATE) >= (
                        SELECT MAX(CAST(timestamp AS DATE)) - INTERVAL '50 days'
                        FROM v_candles_1m
                    )
                    GROUP BY CAST(timestamp AS DATE), symbol
                )
                SELECT
                    trade_date,
                    symbol,
                    open,
                    high,
                    low,
                    close,
                    volume,
                    -- SMA indicators
                    AVG(close) OVER (PARTITION BY symbol ORDER BY trade_date
                        ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) as sma_20,
                    AVG(close) OVER (PARTITION BY symbol ORDER BY trade_date
                        ROWS BETWEEN 49 PRECEDING AND CURRENT ROW) as sma_50,
                    -- RSI
                    close - LAG(close) OVER (PARTITION BY symbol ORDER BY trade_date) as daily_change,
                    -- Volume
                    SUM(volume) OVER (PARTITION BY symbol ORDER BY trade_date
                        ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) / 20.0 as avg_volume_20,
                    -- Momentum
                    LAG(close, 5) OVER (PARTITION BY symbol ORDER BY trade_date) as close_5d,
                    LAG(close, 10) OVER (PARTITION BY symbol ORDER BY trade_date) as close_10d,
                    LAG(close, 20) OVER (PARTITION BY symbol ORDER BY trade_date) as close_20d
                FROM daily
            """,
            ),
            # ─── Symbol snapshot: Latest candle + all indicators (~500 rows) ────
            (
                "m_symbol_snapshot",
                """
                WITH latest AS (
                    SELECT
                        symbol,
                        LAST(timestamp ORDER BY timestamp) as last_ts,
                        LAST(close ORDER BY timestamp) as close,
                        LAST(high ORDER BY timestamp) as high,
                        LAST(low ORDER BY timestamp) as low,
                        LAST(open ORDER BY timestamp) as open,
                        LAST(volume ORDER BY timestamp) as volume,
                        SUM(volume) as total_volume_today
                    FROM m_intraday
                    GROUP BY symbol
                ),
                today_intraday AS (
                    SELECT
                        symbol,
                        COUNT(*) as bars_today,
                        MAX(high) as day_high,
                        MIN(low) as day_low,
                        FIRST(close ORDER BY timestamp) as day_open,
                        LAST(close ORDER BY timestamp) as day_close,
                        SUM(volume) as day_volume
                    FROM m_intraday
                    GROUP BY symbol
                )
                SELECT
                    l.symbol,
                    l.last_ts,
                    l.close,
                    l.high,
                    l.low,
                    l.open,
                    l.volume as last_volume,
                    t.bars_today,
                    t.day_high,
                    t.day_low,
                    t.day_open,
                    t.day_close,
                    t.day_volume,
                    r.sma_20,
                    r.sma_50,
                    r.close_5d,
                    r.close_10d,
                    r.close_20d,
                    CASE
                        WHEN r.close_5d > 0 THEN (l.close - r.close_5d) / r.close_5d * 100
                        ELSE 0
                    END as roc_5,
                    CASE
                        WHEN r.close_10d > 0 THEN (l.close - r.close_10d) / r.close_10d * 100
                        ELSE 0
                    END as roc_10,
                    CASE
                        WHEN r.close_20d > 0 THEN (l.close - r.close_20d) / r.close_20d * 100
                        ELSE 0
                    END as roc_20,
                    CASE
                        WHEN l.close > r.sma_20 AND r.sma_20 > r.sma_50 THEN 'Bullish'
                        WHEN l.close < r.sma_20 AND r.sma_20 < r.sma_50 THEN 'Bearish'
                        ELSE 'Neutral'
                    END as trend,
                    CASE
                        WHEN t.day_volume > 0 AND r.avg_volume_20 > 0
                        THEN t.day_volume / r.avg_volume_20
                        ELSE 1.0
                    END as relative_volume
                FROM latest l
                LEFT JOIN today_intraday t ON l.symbol = t.symbol
                LEFT JOIN m_recent_daily r ON l.symbol = r.symbol
                    AND r.trade_date = (SELECT MAX(trade_date) FROM m_recent_daily WHERE symbol = l.symbol)
            """,
            ),
            # ─── Intraday snapshot: Final scanner view (~500 rows) ─────────────
            (
                "m_intraday_snapshot",
                """
                SELECT
                    s.symbol,
                    s.close as ltp,
                    s.day_open,
                    s.day_high,
                    s.day_low,
                    s.day_close,
                    s.day_volume,
                    s.bars_today,
                    s.sma_20,
                    s.sma_50,
                    s.roc_5,
                    s.roc_10,
                    s.roc_20,
                    s.trend,
                    s.relative_volume,
                    s.close_5d,
                    s.close_10d,
                    s.close_20d,
                    -- RSI from daily data
                    CASE
                        WHEN s.close_5d > 0 THEN (s.close - s.close_5d) / s.close_5d * 100
                        ELSE 0
                    END as rsi_approx,
                    -- ATR approximation from daily range
                    (s.day_high - s.day_low) as atr_approx,
                    -- Composite intraday score
                    (
                        CASE
                            WHEN s.trend = 'Bullish' THEN 80
                            WHEN s.trend = 'Bearish' THEN 20
                            ELSE 50
                        END * 0.25 +
                        CASE
                            WHEN s.relative_volume > 2.0 THEN 90
                            WHEN s.relative_volume > 1.5 THEN 70
                            WHEN s.relative_volume > 1.0 THEN 50
                            ELSE 30
                        END * 0.25 +
                        CASE
                            WHEN s.roc_5 > 3 THEN 90
                            WHEN s.roc_5 > 1 THEN 70
                            WHEN s.roc_5 > 0 THEN 50
                            WHEN s.roc_5 > -1 THEN 30
                            ELSE 10
                        END * 0.25 +
                        CASE
                            WHEN s.close > s.sma_20 THEN 70
                            ELSE 30
                        END * 0.25
                    ) as intraday_score,
                    -- Signal
                    CASE
                        WHEN s.roc_5 > 0 AND s.trend = 'Bullish' AND s.relative_volume > 1.5
                        THEN 'BUY'
                        WHEN s.roc_5 < 0 AND s.trend = 'Bearish'
                        THEN 'SELL'
                        WHEN s.relative_volume > 2.0 AND s.trend = 'Bullish'
                        THEN 'BREAKOUT'
                        ELSE 'NEUTRAL'
                    END as signal
                FROM m_symbol_snapshot s
                WHERE s.bars_today > 0
            """,
            ),
        ]

        for table_name, sql in tables:
            try:
                start = time.perf_counter()
                self.materialize(table_name, sql)
                self.register_materialized(table_name)
                elapsed = time.perf_counter() - start
                logger.info("Materialized %s (%.2fs)", table_name, elapsed)
            except Exception as exc:
                logger.error("Failed to materialize %s: %s", table_name, exc)

    def _materialize_quality(self, conn: duckdb.DuckDBPyConnection) -> None:
        """Materialize quality-related tables from v_candles_1m.

        These are expensive GROUP BY operations over 231M Parquet rows that
        would take seconds as live views. Materializing them brings query time
        from ~14s to <50ms.
        """
        tables = [
            # ─── Trading days: distinct (symbol, trade_date) pairs ───────────
            # Used by v_quality_score for accurate completeness calculation
            # across full history (not just the 50-day m_recent_daily window).
            (
                "m_trading_days",
                """
                SELECT DISTINCT symbol, CAST(timestamp AS DATE) as trade_date
                FROM v_candles_1m
            """,
            ),
            # ─── Duplicate candles: GROUP BY symbol, timestamp on 231M rows ────
            (
                "m_duplicate_candles",
                """
                SELECT
                    symbol,
                    timestamp,
                    COUNT(*) as duplicate_count
                FROM v_candles_1m
                GROUP BY symbol, timestamp
                HAVING COUNT(*) > 1
            """,
            ),
            # ─── Missing candles: GROUP BY symbol, date on 231M rows ──────────
            (
                "m_missing_candles",
                """
                SELECT
                    symbol,
                    CAST(timestamp AS DATE) as trade_date,
                    COUNT(DISTINCT EXTRACT(HOUR FROM timestamp) * 60 + EXTRACT(MINUTE FROM timestamp)) as minute_count
                FROM v_candles_1m
                WHERE EXTRACT(HOUR FROM timestamp) BETWEEN 9 AND 15
                GROUP BY symbol, CAST(timestamp AS DATE)
            """,
            ),
        ]

        for table_name, sql in tables:
            try:
                start = time.perf_counter()
                self.materialize(table_name, sql)
                self.register_materialized(table_name)
                elapsed = time.perf_counter() - start
                logger.info("Materialized %s (%.2fs)", table_name, elapsed)
            except Exception as exc:
                logger.error("Failed to materialize %s: %s", table_name, exc)

    def _materialize_options(self, conn: duckdb.DuckDBPyConnection) -> None:
        """Materialize option analytics tables from market_data/options/candles/.

        Reads from migrated option Parquet data and computes:
        - m_pcr: Put-Call Ratio (volume + OI) per (timestamp, underlying, expiry)
        - m_max_pain: Max Pain strike per (timestamp, underlying, expiry)
        - m_iv_surface: ATM IV, OTM put IV, OTM call IV, IV skew

        These are expensive operations over 1M rows of option data
        (Max Pain uses a self-join). Materialized once, refreshed on data sync.
        """
        tables = [
            ("m_pcr", SQL_M_PCR),
            ("m_max_pain", SQL_M_MAX_PAIN),
            ("m_iv_surface", SQL_M_IV_SURFACE),
        ]
        for table_name, sql in tables:
            try:
                start = time.perf_counter()
                self.materialize(table_name, sql)
                self.register_materialized(table_name)
                elapsed = time.perf_counter() - start
                logger.info("Materialized %s (%.2fs)", table_name, elapsed)
            except Exception as exc:
                logger.error("Failed to materialize %s: %s", table_name, exc)

    def drop_all(self) -> None:
        """Drop all analytics views and materialized tables."""
        views = self.list_views()
        for v in views:
            # Skip internal/system views (duckdb_*, information_schema, etc.)
            if v["name"].startswith("duckdb_") or v["name"].startswith("information_"):
                continue
            try:
                self.conn.execute(f"DROP VIEW IF EXISTS {v['name']}")
            except Exception as exc:
                logger.debug("view_drop_failed: %s: %s", v["name"], exc)
        # Drop materialized tables
        for tbl in [
            "m_intraday",
            "m_recent_daily",
            "m_symbol_snapshot",
            "m_intraday_snapshot",
            "m_duplicate_candles",
            "m_missing_candles",
            "m_trading_days",
            "m_pcr",
            "m_max_pain",
            "m_iv_surface",
        ]:
            self.conn.execute(f"DROP TABLE IF EXISTS {tbl}")
        logger.info("Dropped views and materialized tables")

    def refresh(self) -> dict[str, float]:
        """Refresh all views (drop + recreate)."""
        self.drop_all()
        return self.create_all()

    # ─── Querying ────────────────────────────────────────────────────────────

    def query(self, sql: str, params: list | None = None) -> duckdb.DuckDBPyRelation:
        """Execute a query against the analytics views."""
        if not self._read_only:
            if params:
                return self.conn.execute(sql, params)
            return self.conn.execute(sql)
        with self._query_connection() as conn:
            df = conn.execute(sql, params).fetchdf() if params else conn.execute(sql).fetchdf()
        return duckdb.from_df(df)

    def query_df(self, sql: str, params: list | None = None) -> Any:
        """Execute a query and return as pandas DataFrame."""
        with self._query_connection() as conn:
            if params:
                return conn.execute(sql, params).fetchdf()
            return conn.execute(sql).fetchdf()

    def query_scalar(self, sql: str, params: list | None = None) -> Any:
        """Execute a query and return single scalar value."""
        with self._query_connection() as conn:
            if params:
                result = conn.execute(sql, params).fetchone()
            else:
                result = conn.execute(sql).fetchone()
            return result[0] if result else None

    # ─── Introspection ───────────────────────────────────────────────────────

    def list_views(self) -> list[dict]:
        """List all user-created views in the catalog."""
        with self._query_connection() as conn:
            results = conn.execute(
                "SELECT view_name, sql FROM duckdb_views() WHERE schema_name = 'main' AND internal = false"
            ).fetchall()
            return [{"name": r[0], "definition": r[1] or ""} for r in results]

    def view_exists(self, view_name: str) -> bool:
        """Check if a view exists."""
        with self._query_connection() as conn:
            result = conn.execute(
                "SELECT COUNT(*) FROM duckdb_views() WHERE view_name = ? AND schema_name = 'main'",
                [view_name],
            ).fetchone()
            return result[0] > 0

    def table_exists(self, table_name: str) -> bool:
        """Check if a table exists."""
        with self._query_connection() as conn:
            result = conn.execute(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ? AND table_schema = 'main'",
                [table_name],
            ).fetchone()
            return result[0] > 0

    def view_columns(self, view_name: str) -> list[str]:
        """Get column names for a view or table."""
        try:
            with self._query_connection() as conn:
                result = conn.execute(f"DESCRIBE {view_name}").fetchall()
                return [r[0] for r in result]
        except Exception:
            return []

    def view_count(self) -> int:
        """Count total number of user-created views."""
        with self._query_connection() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM duckdb_views() WHERE schema_name = 'main' AND internal = false"
            ).fetchone()[0]

    def table_count(self) -> int:
        """Count total number of tables."""
        with self._query_connection() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'main'"
            ).fetchone()[0]

    # ─── Performance ─────────────────────────────────────────────────────────

    def benchmark(self, sql: str, iterations: int = 3) -> dict:
        """Benchmark a query."""
        times = []
        for _ in range(iterations):
            start = time.perf_counter()
            with self._query_connection() as conn:
                conn.execute(sql).fetchall()
            elapsed = time.perf_counter() - start
            times.append(elapsed)

        return {
            "query": sql,
            "iterations": iterations,
            "avg_ms": (sum(times) / len(times)) * 1000,
            "min_ms": min(times) * 1000,
            "max_ms": max(times) * 1000,
        }

    def benchmark_all(self) -> list[dict]:
        """Benchmark key analytics queries."""
        queries = [
            ("v_candles_1m", "SELECT COUNT(*) FROM v_candles_1m"),
            ("v_daily_summary", "SELECT COUNT(*) FROM v_daily_summary"),
            ("v_latest_candle", "SELECT COUNT(*) FROM v_latest_candle"),
            ("v_feature_rsi", "SELECT * FROM v_feature_rsi WHERE symbol = 'RELIANCE' LIMIT 10"),
            ("v_feature_atr", "SELECT * FROM v_feature_atr WHERE symbol = 'RELIANCE' LIMIT 10"),
            ("v_feature_vwap", "SELECT * FROM v_feature_vwap WHERE symbol = 'RELIANCE' LIMIT 10"),
            ("v_intraday_snapshot", "SELECT * FROM v_intraday_snapshot LIMIT 10"),
            ("v_top3_candidates", "SELECT * FROM v_top3_candidates LIMIT 3"),
            ("v_top10_candidates", "SELECT * FROM v_top10_candidates LIMIT 10"),
            ("v_strategy_candidates", "SELECT * FROM v_strategy_candidates LIMIT 10"),
            ("v_quality_score", "SELECT * FROM v_quality_score LIMIT 10"),
        ]

        results = []
        for name, sql in queries:
            if self.view_exists(name) or self.table_exists(name):
                try:
                    bench = self.benchmark(sql, iterations=2)
                    bench["view"] = name
                    results.append(bench)
                except Exception as exc:
                    logger.warning("Benchmark failed for %s: %s", name, exc)

        return sorted(results, key=lambda x: x["avg_ms"])
