"""Shared DuckDB connection utilities — retry on lock conflicts.

Provides ``connect_with_retry`` used by DataCatalog, ViewManager, and ScanStore
to handle DuckDB's single-writer lock gracefully.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import duckdb

logger = logging.getLogger(__name__)

DEFAULT_CATALOG_PATH = Path("market_data/catalog.duckdb")


def connect_with_retry(
    path: str,
    read_only: bool = False,
    max_attempts: int = 10,
) -> duckdb.DuckDBPyConnection:
    """Open a DuckDB connection, retrying with exponential backoff on lock conflicts.

    DuckDB is single-writer. A writer holds an exclusive lock, so a concurrent
    reader may see ``IO Error: Could not set lock on file``. This retries with
    backoff so read commands don't fail transiently.
    """
    delay = 0.05
    for attempt in range(max_attempts):
        try:
            return duckdb.connect(path, read_only=read_only)
        except (duckdb.IOException, duckdb.OperationalError, duckdb.ConnectionException) as exc:
            msg = str(exc).lower()
            is_lock_error = "lock" in msg or "could not set" in msg
            if not is_lock_error or attempt == max_attempts - 1:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 1.0)
    raise RuntimeError("unreachable")
