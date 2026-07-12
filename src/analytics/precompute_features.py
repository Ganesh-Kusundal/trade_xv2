"""Pre-compute and materialize technical features as partitioned Parquet.

Features are computed once, stored with point-in-time columns (published_at),
and sorted by (symbol, event_time) for efficient as-of joins.

Usage:
    python -m analytics.precompute_features [--date-to 2024-03-15] [--force]

    # Or programmatically:
    from analytics.precompute_features import FeaturePrecomputer
    pc = FeaturePrecomputer()
    pc.compute_daily_features()
    pc.compute_intraday_features()
"""

from __future__ import annotations

import argparse
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import duckdb

from analytics._daily_sql import build_daily_features_sql
from analytics._intraday_sql import build_intraday_features_sql
from analytics._options_sql import build_options_features_sql
from datalake.core.duckdb_utils import get_pool
from domain.ports.data_catalog import DEFAULT_CATALOG_PATH, DEFAULT_DATA_ROOT

logger = logging.getLogger(__name__)

FEATURES_ROOT = Path(DEFAULT_DATA_ROOT) / "features"
TARGET_FILE_MB = 150


@dataclass
class FeaturePrecomputer:
    """Pre-computes and materializes technical features into partitioned Parquet."""

    catalog_path: str | Path = DEFAULT_CATALOG_PATH
    intraday_days: int = 30
    force: bool = False
    features_root: Path = FEATURES_ROOT
    target_file_mb: int = TARGET_FILE_MB

    def _get_conn(self) -> duckdb.DuckDBPyConnection:
        return get_pool().acquire(self.catalog_path, read_only=False)

    def _release_conn(self, conn: duckdb.DuckDBPyConnection) -> None:
        get_pool().release(self.catalog_path)

    def _ensure_views(self, conn: duckdb.DuckDBPyConnection) -> None:
        from analytics.views.base import BaseViews
        BaseViews().create_views(conn)

    def _compute_published_at(self, conn: duckdb.DuckDBPyConnection) -> datetime:
        result = conn.execute("SELECT MAX(timestamp) FROM v_candles_1m").fetchone()
        return result[0] if result[0] else datetime.now()

    @staticmethod
    def _feature_path(feature_name: str) -> Path:
        return FEATURES_ROOT / feature_name

    def _feature_exists(self, feature_name: str) -> bool:
        feature_dir = self._feature_path(feature_name)
        if not feature_dir.exists():
            return False
        parquet_files = list(feature_dir.rglob("data_*.parquet"))
        return len(parquet_files) > 0

    def compute_daily_features(
        self, conn: duckdb.DuckDBPyConnection | None = None, published_at: datetime | None = None
    ) -> list[str]:
        if conn is None:
            conn = self._get_conn()
            should_release = True
        else:
            should_release = False

        try:
            self._ensure_views(conn)
            if published_at is None:
                published_at = self._compute_published_at(conn)

            written: list[str] = []
            daily_sql = build_daily_features_sql(published_at)

            if not self.force and self._feature_exists("daily_features"):
                logger.info("daily_features already exists, skipping (use --force to re-compute)")
            else:
                self._write_feature_table(conn, "daily_features", daily_sql)
                written.append("daily_features")
                logger.info("Wrote daily_features")

            return written
        finally:
            if should_release:
                self._release_conn(conn)

    def compute_intraday_features(
        self, conn: duckdb.DuckDBPyConnection | None = None, published_at: datetime | None = None
    ) -> list[str]:
        if conn is None:
            conn = self._get_conn()
            should_release = True
        else:
            should_release = False

        try:
            self._ensure_views(conn)
            if published_at is None:
                published_at = self._compute_published_at(conn)

            written: list[str] = []
            intraday_sql = build_intraday_features_sql(published_at, self.intraday_days)

            if not self.force and self._feature_exists("intraday_features"):
                logger.info("intraday_features already exists, skipping")
            else:
                self._write_feature_table(conn, "intraday_features", intraday_sql)
                written.append("intraday_features")
                logger.info("Wrote intraday_features")

            return written
        finally:
            if should_release:
                self._release_conn(conn)

    def compute_options_features(
        self, conn: duckdb.DuckDBPyConnection | None = None, published_at: datetime | None = None
    ) -> list[str]:
        if conn is None:
            conn = self._get_conn()
            should_release = True
        else:
            should_release = False

        try:
            if published_at is None:
                published_at = self._compute_published_at(conn)

            written: list[str] = []
            options_sql = build_options_features_sql(published_at)

            if not self.force and self._feature_exists("options_features"):
                logger.info("options_features already exists, skipping")
            else:
                self._write_feature_table(conn, "options_features", options_sql)
                written.append("options_features")
                logger.info("Wrote options_features")

            return written
        finally:
            if should_release:
                self._release_conn(conn)

    def _write_feature_table(self, conn: duckdb.DuckDBPyConnection, name: str, sql: str) -> Path:
        feature_dir = self._feature_path(name)
        feature_dir.mkdir(parents=True, exist_ok=True)

        temp_table = f"_precompute_{name}_{int(time.time() * 1_000_000)}"
        try:
            conn.execute(f"DROP TABLE IF EXISTS {temp_table}")

            copy_sql = f"""
                COPY ({sql}) TO '{feature_dir}/'
                (FORMAT PARQUET, PER_THREAD_OUTPUT TRUE,
                 PARTITION_BY (year, month),
                 ORDER BY (symbol, event_time))
            """
            conn.execute(copy_sql)

            return feature_dir
        except Exception:
            raise
        finally:
            conn.execute(f"DROP TABLE IF EXISTS {temp_table}")

    def compute_all(self, conn: duckdb.DuckDBPyConnection | None = None) -> dict[str, list[str]]:
        if conn is None:
            conn = self._get_conn()
            should_release = True
        else:
            should_release = False

        try:
            published_at = self._compute_published_at(conn)
            results: dict[str, list[str]] = {}
            results["daily"] = self.compute_daily_features(conn, published_at)
            results["intraday"] = self.compute_intraday_features(conn, published_at)
            results["options"] = self.compute_options_features(conn, published_at)
            return results
        finally:
            if should_release:
                self._release_conn(conn)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="Pre-compute technical features")
    parser.add_argument(
        "--date-to",
        default=None,
        help="Compute features up to this date (YYYY-MM-DD). Default: latest data",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-compute even if output already exists",
    )
    args = parser.parse_args()

    pc = FeaturePrecomputer(force=args.force)
    results = pc.compute_all()
    total = sum(len(v) for v in results.values())
    logger.info("Pre-computed %d feature groups: %s", total, results)


if __name__ == "__main__":
    main()
