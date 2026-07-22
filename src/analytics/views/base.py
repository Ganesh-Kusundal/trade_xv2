"""Layer 1: Base Market Views — standardized candle data, daily summaries, latest quotes."""

from __future__ import annotations

import glob as _glob
import logging

import duckdb

from datalake.core.paths import curated_equity_glob, symbol_partition_glob
from domain.ports.data_catalog import DEFAULT_DATA_ROOT

logger = logging.getLogger(__name__)

_CANONICAL_COLUMNS = "timestamp, symbol, exchange, open, high, low, close, volume, oi"


class BaseViews:
    """Creates base market data views in DuckDB.

    Layout resolution order:
    1. Curated (date-partitioned) — ``{root}/curated/equities/candles/year=*/month=*/``
    2. Legacy (symbol-partitioned) — ``{root}/equities/candles/timeframe=1m/symbol=*/``
       plus ``{root}/indices/candles/timeframe=1m/symbol=*/``
    3. Empty stub with correct schema (no data on disk yet)
    """

    def __init__(self, root: str = DEFAULT_DATA_ROOT) -> None:
        self._root = root

    def create_views(self, conn: duckdb.DuckDBPyConnection) -> None:
        """Create all base market views."""
        self._create_candles_1m(conn)
        self._create_daily_summary(conn)
        self._create_latest_candle(conn)

    def _resolve_layout(self) -> tuple[str, str] | None:
        """Return (glob_pattern, layout_name) for the first layout that has files."""
        curated = curated_equity_glob(self._root)
        if _glob.glob(curated):
            return curated, "curated"

        legacy_eq = symbol_partition_glob(self._root)
        if _glob.glob(legacy_eq):
            return legacy_eq, "legacy"

        return None

    def _create_candles_1m(self, conn: duckdb.DuckDBPyConnection) -> None:
        """v_candles_1m — standardized 1-minute candle view.

        Tries curated layout first, falls back to legacy symbol-partitioned
        layout (equities + indices).  Creates an empty stub if no data exists.
        """
        resolved = self._resolve_layout()

        if resolved is None:
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
            logger.warning("v_candles_1m: no parquet files found (curated or legacy)")
            return

        pattern, layout = resolved

        if layout == "curated":
            conn.execute(f"""
                CREATE OR REPLACE VIEW v_candles_1m AS
                SELECT {_CANONICAL_COLUMNS}
                FROM read_parquet('{pattern}', hive_partitioning=true)
            """)
        else:
            legacy_idx = symbol_partition_glob(self._root).replace(
                "/equities/", "/indices/"
            )
            conn.execute(f"""
                CREATE OR REPLACE VIEW v_candles_1m AS
                SELECT {_CANONICAL_COLUMNS} FROM read_parquet('{pattern}', hive_partitioning=true)
                UNION ALL
                SELECT {_CANONICAL_COLUMNS} FROM read_parquet('{legacy_idx}', hive_partitioning=true)
            """)

        logger.info("Created v_candles_1m (%s layout: %s)", layout, pattern)

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
