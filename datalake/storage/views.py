"""DuckDB Views — reusable SQL views over the data lake."""

from __future__ import annotations

import logging
from pathlib import Path

import duckdb

from datalake.core.paths import timeframe_partition_dir
from datalake.duckdb_utils import DEFAULT_CATALOG_PATH

logger = logging.getLogger(__name__)


def create_views(db_path: str | Path | None = None) -> None:
    """Create all reusable DuckDB views."""
    path = Path(db_path) if db_path else DEFAULT_CATALOG_PATH
    conn = duckdb.connect(str(path))

    # Register all Parquet files as a view
    parquet_dir = timeframe_partition_dir(str(Path(db_path).parent), "1m")
    if parquet_dir.exists():
        parquet_pattern = str(parquet_dir / "symbol=*" / "data.parquet")

        conn.execute(
            """
            CREATE OR REPLACE VIEW all_candles AS
            SELECT * FROM read_parquet(?)
        """,
            [parquet_pattern],
        )

        # Latest candle per symbol
        conn.execute("""
            CREATE OR REPLACE VIEW latest_candles AS
            SELECT *
            FROM all_candles
            WHERE (symbol, timestamp) IN (
                SELECT symbol, MAX(timestamp)
                FROM all_candles
                GROUP BY symbol
            )
        """)

        # Daily summary (aggregate 1m to daily)
        conn.execute("""
            CREATE OR REPLACE VIEW daily_summary AS
            SELECT
                symbol,
                DATE_TRUNC('day', timestamp) AS date,
                FIRST(open) AS open,
                MAX(high) AS high,
                MIN(low) AS low,
                LAST(close) AS close,
                SUM(volume) AS volume,
                LAST(oi) AS oi
            FROM all_candles
            GROUP BY symbol, DATE_TRUNC('day', timestamp)
            ORDER BY symbol, date
        """)

        # NIFTY500 universe (symbols with data)
        conn.execute("""
            CREATE OR REPLACE VIEW nifty500_universe AS
            SELECT DISTINCT symbol
            FROM all_candles
            ORDER BY symbol
        """)

        # Data quality summary
        conn.execute("""
            CREATE OR REPLACE VIEW data_quality_summary AS
            SELECT
                symbol,
                COUNT(*) AS total_rows,
                MIN(timestamp) AS first_candle,
                MAX(timestamp) AS last_candle,
                COUNT(DISTINCT DATE_TRUNC('day', timestamp)) AS trading_days,
                SUM(CASE WHEN volume = 0 THEN 1 ELSE 0 END) AS zero_volume_bars,
                SUM(CASE WHEN high < low THEN 1 ELSE 0 END) AS ohlc_errors
            FROM all_candles
            GROUP BY symbol
            ORDER BY symbol
        """)

        logger.info("Views created successfully")
    else:
        logger.warning("Parquet directory not found: %s", parquet_dir)

    conn.close()
