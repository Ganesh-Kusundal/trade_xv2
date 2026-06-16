"""Layer 3-5: Scanner Views — intraday trading focused.

Uses materialized tables:
- m_intraday: Current day's 1m candles (~187K rows)
- m_recent_daily: Last 50 days daily candles for indicators (~25K rows)
- m_symbol_snapshot: Latest candle per symbol with indicators (~500 rows)
"""

from __future__ import annotations

import logging

import duckdb

logger = logging.getLogger(__name__)


class ScannerViews:
    """Creates scanner analytics views in DuckDB."""

    def create_views(self, conn: duckdb.DuckDBPyConnection) -> None:
        """Create all scanner views."""
        self._create_intraday_vwap(conn)
        self._create_intraday_rsi(conn)
        self._create_intraday_atr(conn)
        self._create_intraday_snapshot(conn)
        self._create_top3_candidates(conn)
        self._create_top10_candidates(conn)

    def _create_intraday_vwap(self, conn: duckdb.DuckDBPyConnection) -> None:
        """v_intraday_vwap — VWAP for current trading day."""
        conn.execute("""
            CREATE OR REPLACE VIEW v_intraday_vwap AS
            SELECT
                symbol,
                timestamp,
                close,
                volume,
                SUM(close * volume) OVER (
                    PARTITION BY symbol ORDER BY timestamp
                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                ) / NULLIF(SUM(volume) OVER (
                    PARTITION BY symbol ORDER BY timestamp
                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                ), 0) as vwap,
                close - (
                    SUM(close * volume) OVER (
                        PARTITION BY symbol ORDER BY timestamp
                        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                    ) / NULLIF(SUM(volume) OVER (
                        PARTITION BY symbol ORDER BY timestamp
                        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                    ), 0)
                ) as distance_from_vwap
            FROM m_intraday
        """)
        logger.debug("Created v_intraday_vwap")

    def _create_intraday_rsi(self, conn: duckdb.DuckDBPyConnection) -> None:
        """v_intraday_rsi — RSI for current trading day."""
        conn.execute("""
            CREATE OR REPLACE VIEW v_intraday_rsi AS
            WITH changes AS (
                SELECT
                    symbol,
                    timestamp,
                    close,
                    close - LAG(close) OVER (PARTITION BY symbol ORDER BY timestamp) as change
                FROM m_intraday
            )
            SELECT
                symbol,
                timestamp,
                close,
                AVG(CASE WHEN change > 0 THEN change ELSE 0 END) OVER (
                    PARTITION BY symbol ORDER BY timestamp
                    ROWS BETWEEN 13 PRECEDING AND CURRENT ROW
                ) as avg_gain_14,
                AVG(CASE WHEN change < 0 THEN ABS(change) ELSE 0 END) OVER (
                    PARTITION BY symbol ORDER BY timestamp
                    ROWS BETWEEN 13 PRECEDING AND CURRENT ROW
                ) as avg_loss_14,
                CASE
                    WHEN AVG(CASE WHEN change < 0 THEN ABS(change) ELSE 0 END) OVER (
                        PARTITION BY symbol ORDER BY timestamp
                        ROWS BETWEEN 13 PRECEDING AND CURRENT ROW
                    ) = 0 THEN 100.0
                    ELSE 100.0 - (100.0 / (1.0 +
                        AVG(CASE WHEN change > 0 THEN change ELSE 0 END) OVER (
                            PARTITION BY symbol ORDER BY timestamp
                            ROWS BETWEEN 13 PRECEDING AND CURRENT ROW
                        ) /
                        AVG(CASE WHEN change < 0 THEN ABS(change) ELSE 0 END) OVER (
                            PARTITION BY symbol ORDER BY timestamp
                            ROWS BETWEEN 13 PRECEDING AND CURRENT ROW
                        )
                    ))
                END as rsi_14
            FROM changes
        """)
        logger.debug("Created v_intraday_rsi")

    def _create_intraday_atr(self, conn: duckdb.DuckDBPyConnection) -> None:
        """v_intraday_atr — ATR for current trading day."""
        conn.execute("""
            CREATE OR REPLACE VIEW v_intraday_atr AS
            WITH tr AS (
                SELECT
                    symbol,
                    timestamp,
                    high,
                    low,
                    close,
                    GREATEST(
                        high - low,
                        ABS(high - LAG(close) OVER (PARTITION BY symbol ORDER BY timestamp)),
                        ABS(low - LAG(close) OVER (PARTITION BY symbol ORDER BY timestamp))
                    ) as true_range
                FROM m_intraday
            )
            SELECT
                symbol,
                timestamp,
                high,
                low,
                close,
                true_range,
                AVG(true_range) OVER (
                    PARTITION BY symbol ORDER BY timestamp
                    ROWS BETWEEN 13 PRECEDING AND CURRENT ROW
                ) as atr_14
            FROM tr
        """)
        logger.debug("Created v_intraday_atr")

    def _create_intraday_snapshot(self, conn: duckdb.DuckDBPyConnection) -> None:
        """v_intraday_snapshot — real-time scanner for current trading day."""
        conn.execute("""
            CREATE OR REPLACE VIEW v_intraday_snapshot AS
            SELECT * FROM m_intraday_snapshot
        """)
        logger.debug("Created v_intraday_snapshot")

    def _create_top3_candidates(self, conn: duckdb.DuckDBPyConnection) -> None:
        """v_top3_candidates — top 3 stocks by intraday score."""
        conn.execute("""
            CREATE OR REPLACE VIEW v_top3_candidates AS
            SELECT
                symbol,
                ltp,
                intraday_score,
                signal,
                trend,
                rsi_approx as rsi_14,
                roc_5,
                relative_volume,
                day_high,
                day_low,
                day_volume
            FROM m_intraday_snapshot
            ORDER BY intraday_score DESC, symbol
            LIMIT 3
        """)
        logger.debug("Created v_top3_candidates")

    def _create_top10_candidates(self, conn: duckdb.DuckDBPyConnection) -> None:
        """v_top10_candidates — top 10 stocks by intraday score."""
        conn.execute("""
            CREATE OR REPLACE VIEW v_top10_candidates AS
            SELECT
                symbol,
                ltp,
                intraday_score,
                signal,
                trend,
                rsi_approx as rsi_14,
                roc_5,
                relative_volume,
                day_high,
                day_low,
                day_volume
            FROM m_intraday_snapshot
            ORDER BY intraday_score DESC, symbol
            LIMIT 10
        """)
        logger.debug("Created v_top10_candidates")
