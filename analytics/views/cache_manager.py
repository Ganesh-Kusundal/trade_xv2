"""Cache manager — materialization, caching strategies, and version management."""

from __future__ import annotations

import json
import logging
import shutil
import time
from pathlib import Path
from typing import Any

import duckdb

logger = logging.getLogger(__name__)

MATERIALIZED_DIR = Path("analytics_cache")
VERSION_KEEP_COUNT = 3


class CacheManager:
    """Manages materialized Parquet tables with versioning and atomic updates.

    Handles:
    - Materializing query results to versioned Parquet files
    - Atomic table swaps via latest.json manifest
    - Cleanup of old versions (retains VERSION_KEEP_COUNT)
    - Registration of materialized tables in DuckDB
    """

    def __init__(self, conn: duckdb.DuckDBPyConnection | None = None) -> None:
        """Initialize with optional DuckDB connection for DDL operations."""
        self._conn = conn
        MATERIALIZED_DIR.mkdir(parents=True, exist_ok=True)

    def materialize(
        self,
        table_name: str,
        sql: str,
        conn: duckdb.DuckDBPyConnection | None = None,
        partition_by: str | None = None,
    ) -> float:
        """Materialize a query result into a versioned Parquet table.

        Writes to a timestamped directory first, then atomically promotes the
        new version to "latest". Old versions are retained (see VERSION_KEEP_COUNT)
        so readers always see a consistent snapshot.

        Args:
            table_name: Name of the materialized table.
            sql: SQL query to materialize.
            conn: DuckDB connection (uses self._conn if not provided).
            partition_by: Optional partition column.

        Returns:
            Elapsed time in seconds.
        """
        db_conn = conn or self._conn
        if db_conn is None:
            raise ValueError("No DuckDB connection provided")

        version_dir = MATERIALIZED_DIR / "versions" / table_name
        version_dir.mkdir(parents=True, exist_ok=True)
        version_ts = str(int(time.time() * 1_000_000))

        start = time.perf_counter()

        if partition_by:
            part_dir = version_dir / version_ts
            part_dir.mkdir(parents=True, exist_ok=True)
            db_conn.execute(f"""
                COPY ({sql}) TO '{part_dir}'
                (FORMAT PARQUET, PARTITION_BY ({partition_by}))
            """)
            self._write_latest(
                table_name, f"versions/{table_name}/{version_ts}", partitioned=True
            )
        else:
            parquet_path = version_dir / f"{version_ts}.parquet"
            db_conn.execute(f"""
                COPY ({sql}) TO '{parquet_path}'
                (FORMAT PARQUET, COMPRESSION 'SNAPPY')
            """)
            self._write_latest(
                table_name, f"versions/{table_name}/{version_ts}.parquet", partitioned=False
            )

        self._cleanup_old_versions(table_name)

        elapsed = time.perf_counter() - start
        logger.info(
            "Materialized %s version %s in %.2fs", table_name, version_ts, elapsed
        )
        return elapsed

    def _write_latest(
        self, table_name: str, version_path: str, partitioned: bool
    ) -> None:
        """Write the latest.json manifest for atomic version promotion."""
        latest_file = MATERIALIZED_DIR / "versions" / table_name / "latest.json"
        latest_file.write_text(
            json.dumps({"path": version_path, "partitioned": partitioned})
        )

    def _read_latest(self, table_name: str) -> dict[str, Any] | None:
        """Read the latest.json manifest. Returns None if not found or invalid."""
        latest_file = MATERIALIZED_DIR / "versions" / table_name / "latest.json"
        if not latest_file.exists():
            return None
        try:
            return json.loads(latest_file.read_text())
        except Exception:
            return None

    def _cleanup_old_versions(self, table_name: str) -> None:
        """Remove old materialized versions, keeping only VERSION_KEEP_COUNT."""
        version_dir = MATERIALIZED_DIR / "versions" / table_name
        if not version_dir.exists():
            return
        entries = sorted(
            [p for p in version_dir.iterdir() if p.name != "latest.json"],
            key=lambda p: p.stat().st_mtime,
        )
        to_remove = entries[:-VERSION_KEEP_COUNT]
        for entry in to_remove:
            try:
                if entry.is_dir():
                    shutil.rmtree(entry)
                else:
                    entry.unlink()
            except Exception as exc:
                logger.warning(
                    "Failed to remove old materialized version %s: %s", entry, exc
                )

    def register_materialized(
        self,
        table_name: str,
        conn: duckdb.DuckDBPyConnection | None = None,
        partition_by: str | None = None,
    ) -> None:
        """Register the latest materialized Parquet table as a DuckDB table.

        Creates a new table with a temporary name, then atomically swaps it in
        via ALTER TABLE ... RENAME TO so readers never see a missing table.

        Args:
            table_name: Name of the table to register.
            conn: DuckDB connection (uses self._conn if not provided).
            partition_by: Optional partition column.
        """
        db_conn = conn or self._conn
        if db_conn is None:
            raise ValueError("No DuckDB connection provided")

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
                    f"CREATE TABLE {temp_table} AS "  # noqa: S608
                    "SELECT * FROM read_parquet(?, hive_partitioning=true)"
                )
                db_conn.execute(sql, [f"{version_path}/**/*.parquet"])
            else:
                sql = (
                    f"CREATE TABLE {temp_table} AS "  # noqa: S608
                    "SELECT * FROM read_parquet(?)"
                )
                db_conn.execute(sql, [str(version_path)])
            # Atomic swap: drop old, rename new.
            db_conn.execute(f"DROP TABLE IF EXISTS {table_name}")
            db_conn.execute(f"ALTER TABLE {temp_table} RENAME TO {table_name}")
        except Exception:
            db_conn.execute(f"DROP TABLE IF EXISTS {temp_table}")
            raise

    def drop_materialized(
        self, table_name: str, conn: duckdb.DuckDBPyConnection | None = None
    ) -> None:
        """Drop a materialized table and remove all its versions.

        Args:
            table_name: Name of the table to drop.
            conn: DuckDB connection (uses self._conn if not provided).
        """
        db_conn = conn or self._conn
        if db_conn is None:
            raise ValueError("No DuckDB connection provided")

        db_conn.execute(f"DROP TABLE IF EXISTS {table_name}")
        version_dir = MATERIALIZED_DIR / "versions" / table_name
        if version_dir.exists():
            shutil.rmtree(version_dir)
