"""Layer 1: Base Market Views — standardized candle data, daily summaries, latest quotes."""

from __future__ import annotations

import glob as _glob
import logging
import os

import duckdb

from domain.ports.data_catalog import DEFAULT_DATA_ROOT

logger = logging.getLogger(__name__)


class BaseViews:
    """Creates base market data views in DuckDB.

    Parameters
    ----------
    root:
        Root directory of the data lake.  The curated Parquet path is
        derived as ``<root>/curated/equities/candles/``.
    """

    def __init__(self, root: str = DEFAULT_DATA_ROOT) -> None:
        self._root = root

    @property
    def _curated_glob(self) -> str:
        return os.path.join(self._root, "curated", "equities", "candles",
                            "year=*", "month=*", "data_*.parquet")

    def create_views(self, conn: duckdb.DuckDBPyConnection) -> None:
        """Create all base market views."""
        self._create_candles_1m(conn)
        self._create_daily_summary(conn)
        self._create_latest_candle(conn)

    def _create_candles_1m(self, conn: duckdb.DuckDBPyConnection) -> None:
        """v_candles_1m — standardized 1-minute candle view.

        Reads from the curated Parquet layout (date-partitioned) with
        hive partitioning enabled.  If no curated files exist yet, an
        empty view with the correct schema is created so downstream
        queries do not fail.
        """
        pattern = self._curated_glob
        if _glob.glob(pattern):
            conn.execute(f"""
                CREATE OR REPLACE VIEW v_candles_1m AS
                SELECT
                    timestamp,
                    symbol,
                    'NSE' as exchange,
                    open,
                    high,
                    low,
                    close,
                    volume,
                    0 as oi
                FROM read_parquet(
                    '{pattern}',
                    hive_partitioning=true
                )
            """)
            logger.debug("Created v_candles_1m (curated layout)")
        else:
            conn.execute("""
                CREATE OR REPLACE VIEW v_candles_1m AS
                SELECT
                    CAST(NULL AS TIMESTAMP) as timestamp,
                    CAST(NULL AS VARCHAR) as symbol,
                    CAST(NULL AS VARCHAR) as exchange,
                    CAST(NULL AS DOUBLE) as open,
                    CAST(NULL AS DOUBLE) as high,
                    CAST(NULL AS DOUBLE) as low,
                    CAST(NULL AS DOUBLE) as close,
                    CAST(NULL AS BIGINT) as volume,
                    CAST(NULL AS BIGINT) as oi
                WHERE 1 = 0
            """)
            logger.debug("Created v_candles_1m (empty — no curated parquet files found)")

    def _create_daily_summary(self, conn: duckdb.DuckDBPyConnection) -> None:
        """v_daily_summary — daily OHLCV aggregates from 1m candles."""
        conn.execute("""
            CREATE OR REPLACE VIEW v_daily_summary AS
            SELECT
                CAST(timestamp AS DATE) as trade_date,
                symbol,
                FIRST(open ORDER BY timestamp) as day_open,
                MAX(high) as day_high,
                MIN(low) as day_low,
                LAST(close ORDER BY timestamp) as day_close,
                SUM(volume) as day_volume,
                SUM(oi) as day_oi
            FROM v_candles_1m
            GROUP BY CAST(timestamp AS DATE), symbol
        """)
        logger.debug("Created v_daily_summary")

    def _create_latest_candle(self, conn: duckdb.DuckDBPyConnection) -> None:
        """v_latest_candle — most recent candle per symbol.

        P1-2 fix: Replaced self-join with MAX(timestamp) subquery with
        DISTINCT ON which is O(n) instead of O(n^2). The self-join scanned
        the entire table twice; DISTINCT ON uses a single pass with hash
        aggregation.
        """
        conn.execute("""
            CREATE OR REPLACE VIEW v_latest_candle AS
            SELECT DISTINCT ON (symbol)
                timestamp,
                symbol,
                open,
                high,
                low,
                close,
                volume,
                oi
            FROM v_candles_1m
            ORDER BY symbol, timestamp DESC
        """)
        logger.debug("Created v_latest_candle (DISTINCT ON — O(n) single pass)")
