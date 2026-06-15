"""Layer 10: Data Quality Views — missing candles, duplicates, quality scores."""

from __future__ import annotations

import logging

import duckdb

logger = logging.getLogger(__name__)


class QualityViews:
    """Creates data quality views in DuckDB."""

    def create_views(self, conn: duckdb.DuckDBPyConnection) -> None:
        """Create all quality views."""
        self._create_missing_candles(conn)
        self._create_duplicate_candles(conn)
        self._create_quality_score(conn)

    def _create_missing_candles(self, conn: duckdb.DuckDBPyConnection) -> None:
        """v_missing_candles — detect missing 1m candles during market hours."""
        conn.execute("""
            CREATE OR REPLACE VIEW v_missing_candles AS
            WITH trading_hours AS (
                SELECT
                    symbol,
                    CAST(timestamp AS DATE) as trade_date,
                    COUNT(DISTINCT EXTRACT(HOUR FROM timestamp) * 60 + EXTRACT(MINUTE FROM timestamp)) as minute_count
                FROM v_candles_1m
                WHERE EXTRACT(HOUR FROM timestamp) BETWEEN 9 AND 15
                GROUP BY symbol, CAST(timestamp AS DATE)
            )
            SELECT
                symbol,
                trade_date,
                minute_count,
                CASE
                    WHEN minute_count < 375 THEN 'INCOMPLETE'
                    WHEN minute_count < 345 THEN 'PARTIAL'
                    ELSE 'COMPLETE'
                END as status
            FROM trading_hours
            WHERE minute_count < 375
            ORDER BY trade_date DESC, symbol
        """)
        logger.debug("Created v_missing_candles")

    def _create_duplicate_candles(self, conn: duckdb.DuckDBPyConnection) -> None:
        """v_duplicate_candles — detect duplicate records."""
        conn.execute("""
            CREATE OR REPLACE VIEW v_duplicate_candles AS
            SELECT
                symbol,
                timestamp,
                COUNT(*) as duplicate_count
            FROM v_candles_1m
            GROUP BY symbol, timestamp
            HAVING COUNT(*) > 1
            ORDER BY duplicate_count DESC
        """)
        logger.debug("Created v_duplicate_candles")

    def _create_quality_score(self, conn: duckdb.DuckDBPyConnection) -> None:
        """v_quality_score — trust score per symbol."""
        conn.execute("""
            CREATE OR REPLACE VIEW v_quality_score AS
            WITH completeness AS (
                SELECT
                    symbol,
                    COUNT(DISTINCT CAST(timestamp AS DATE)) as trading_days,
                    MIN(timestamp) as first_candle,
                    MAX(timestamp) as last_candle
                FROM v_candles_1m
                GROUP BY symbol
            ),
            duplicates AS (
                SELECT
                    symbol,
                    COUNT(*) as dup_count
                FROM v_duplicate_candles
                GROUP BY symbol
            ),
            missing AS (
                SELECT
                    symbol,
                    COUNT(*) as missing_count
                FROM v_missing_candles
                GROUP BY symbol
            )
            SELECT
                c.symbol,
                c.trading_days,
                c.first_candle,
                c.last_candle,
                COALESCE(d.dup_count, 0) as duplicate_count,
                COALESCE(m.missing_count, 0) as missing_count,
                CASE
                    WHEN c.trading_days = 0 THEN 0
                    ELSE ROUND(
                        (1.0 - COALESCE(d.dup_count, 0) / NULLIF(c.trading_days * 375.0, 0)) *
                        (1.0 - COALESCE(m.missing_count, 0) / NULLIF(c.trading_days * 375.0, 0)) *
                        100, 2
                    )
                END as quality_score
            FROM completeness c
            LEFT JOIN duplicates d ON c.symbol = d.symbol
            LEFT JOIN missing m ON c.symbol = m.symbol
            ORDER BY quality_score DESC
        """)
        logger.debug("Created v_quality_score")
