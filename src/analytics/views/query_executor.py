"""Query executor — data fetching, aggregation, and result transformation."""

from __future__ import annotations

import logging
import time
from typing import Any

import duckdb

logger = logging.getLogger(__name__)


class QueryExecutor:
    """Executes queries against analytics views and provides benchmarking.

    Handles all read/query operations including scalar queries, DataFrame
    results, and performance benchmarking.
    """

    def __init__(
        self,
        get_connection,
        get_query_connection,
        *,
        read_only: bool = False,
    ) -> None:
        """Initialize with connection providers.

        Args:
            get_connection: Callable returning RW DuckDB connection.
            get_query_connection: Context manager yielding connection for queries.
            read_only: When True, query() materializes results via a short-lived
                RO connection (relations cannot outlive the context).
        """
        self._get_connection = get_connection
        self._get_query_connection = get_query_connection
        self._read_only = read_only

    def query(self, sql: str, params: list | None = None) -> duckdb.DuckDBPyRelation:
        """Execute a query against the analytics views."""
        if not self._read_only:
            conn = self._get_connection()
            if params:
                return conn.execute(sql, params)
            return conn.execute(sql)
        with self._get_query_connection() as conn:
            df = (
                conn.execute(sql, params).fetchdf()
                if params
                else conn.execute(sql).fetchdf()
            )
        return duckdb.from_df(df)

    def query_df(self, sql: str, params: list | None = None) -> Any:
        """Execute a query and return as pandas DataFrame."""
        with self._get_query_connection() as conn:
            if params:
                return conn.execute(sql, params).fetchdf()
            return conn.execute(sql).fetchdf()

    def query_scalar(self, sql: str, params: list | None = None) -> Any:
        """Execute a query and return single scalar value."""
        with self._get_query_connection() as conn:
            if params:
                result = conn.execute(sql, params).fetchone()
            else:
                result = conn.execute(sql).fetchone()
            return result[0] if result else None

    def benchmark(self, sql: str, iterations: int = 3) -> dict:
        """Benchmark a query over multiple iterations.

        Returns dict with query, iterations, avg_ms, min_ms, max_ms.
        """
        times = []
        for _ in range(iterations):
            start = time.perf_counter()
            with self._get_query_connection() as conn:
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

    def benchmark_all(self, view_exists_fn, table_exists_fn) -> list[dict]:
        """Benchmark key analytics queries.

        Args:
            view_exists_fn: Callable to check if a view exists.
            table_exists_fn: Callable to check if a table exists.
        """
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
            if view_exists_fn(name) or table_exists_fn(name):
                try:
                    bench = self.benchmark(sql, iterations=2)
                    bench["view"] = name
                    results.append(bench)
                except Exception as exc:
                    logger.warning("Benchmark failed for %s: %s", name, exc)

        return sorted(results, key=lambda x: x["avg_ms"])
