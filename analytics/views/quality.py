"""Layer 10: Data Quality Views — missing candles, duplicates, quality scores.

These views read from materialized tables (m_duplicate_candles, m_missing_candles)
instead of v_candles_1m to avoid full 231M-row Parquet scans at query time.

All timestamps are in IST (Asia/Kolkata) per the canonical schema.
"""

from __future__ import annotations

import logging

import duckdb

from datalake.schema import TRADING_MINUTES_PER_DAY

logger = logging.getLogger(__name__)

MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 15
MARKET_CLOSE_HOUR = 15
MARKET_CLOSE_MINUTE = 30
TRADING_MINUTES_PARTIAL = 345  # >= 92% of full day


class QualityViews:
    """Creates data quality views in DuckDB."""

    def create_views(self, conn: duckdb.DuckDBPyConnection) -> None:
        """Create all quality views.

        Expects m_duplicate_candles and m_missing_candles to already be
        materialized (see ViewManager._materialize_quality).
        """
        self._create_missing_candles(conn)
        self._create_duplicate_candles(conn)
        self._create_quality_score(conn)

    def _create_missing_candles(self, conn: duckdb.DuckDBPyConnection) -> None:
        """v_missing_candles — detect missing 1m candles during NSE market hours.

        Reads from materialized m_missing_candles table.
        """
        conn.execute(
            """
            CREATE OR REPLACE VIEW v_missing_candles AS
            SELECT
                symbol,
                trade_date,
                minute_count,
                CASE
                    WHEN minute_count < ? THEN 'INCOMPLETE'
                    WHEN minute_count < ? THEN 'PARTIAL'
                    ELSE 'COMPLETE'
                END as status
            FROM m_missing_candles
            WHERE minute_count < ?
            ORDER BY trade_date DESC, symbol
        """,
            [TRADING_MINUTES_PARTIAL, TRADING_MINUTES_PER_DAY, TRADING_MINUTES_PER_DAY],
        )
        logger.debug("Created v_missing_candles")

    def _create_duplicate_candles(self, conn: duckdb.DuckDBPyConnection) -> None:
        """v_duplicate_candles — detect duplicate timestamps.

        Reads from materialized m_duplicate_candles table.
        """
        conn.execute("""
            CREATE OR REPLACE VIEW v_duplicate_candles AS
            SELECT symbol, timestamp, duplicate_count
            FROM m_duplicate_candles
            ORDER BY duplicate_count DESC
        """)
        logger.debug("Created v_duplicate_candles")

    def _create_quality_score(self, conn: duckdb.DuckDBPyConnection) -> None:
        """v_quality_score — trust score per symbol.

        Formula: (1 - missing_minutes / total_possible_minutes) * (1 - duplicate_count / total_candles) * 100

        Uses m_trading_days (full history) for accurate completeness calculation.
        Previously used m_recent_daily (50-day window) which artificially
        capped trading_days at ~50 and inflated the missing_days count.
        Also previously used COUNT(days with < 375 candles) which gave
        near-100% scores even for symbols missing 1 candle per day.
        """
        conn.execute(
            "CREATE OR REPLACE VIEW v_quality_score AS "  # noqa: S608
            "WITH completeness AS ("
            "SELECT symbol, COUNT(DISTINCT trade_date) as trading_days, "
            "MIN(trade_date) as first_candle, MAX(trade_date) as last_candle "
            "FROM m_trading_days GROUP BY symbol"
            "), "
            "duplicates AS ("
            "SELECT symbol, COUNT(*) as dup_count "
            "FROM m_duplicate_candles GROUP BY symbol"
            "), "
            "missing AS ("
            "SELECT symbol, "
            f"COALESCE(SUM({TRADING_MINUTES_PER_DAY} - minute_count), 0) as missing_minutes "
            "FROM m_missing_candles GROUP BY symbol"
            ") "
            "SELECT c.symbol, c.trading_days, c.first_candle, c.last_candle, "
            "COALESCE(d.dup_count, 0) as duplicate_count, "
            "CAST(COALESCE(m.missing_minutes, 0) AS BIGINT) as missing_count, "
            "CASE WHEN c.trading_days = 0 THEN 0 "
            "ELSE ROUND("
            f"(1.0 - COALESCE(m.missing_minutes, 0) / NULLIF(c.trading_days * {TRADING_MINUTES_PER_DAY}.0, 0)) * "
            f"(1.0 - COALESCE(d.dup_count, 0) / NULLIF(c.trading_days * {TRADING_MINUTES_PER_DAY}.0, 0)) * "
            "100, 2) END as quality_score "
            "FROM completeness c "
            "LEFT JOIN duplicates d ON c.symbol = d.symbol "
            "LEFT JOIN missing m ON c.symbol = m.symbol "
            "ORDER BY quality_score DESC"
        )
        logger.debug("Created v_quality_score")
