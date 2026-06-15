"""Layer 1: Base Market Views — standardized candle data, daily summaries, latest quotes."""

from __future__ import annotations

import logging

import duckdb

logger = logging.getLogger(__name__)


class BaseViews:
    """Creates base market data views in DuckDB."""

    def create_views(self, conn: duckdb.DuckDBPyConnection) -> None:
        """Create all base market views."""
        self._create_candles_1m(conn)
        self._create_daily_summary(conn)
        self._create_latest_candle(conn)

    def _create_candles_1m(self, conn: duckdb.DuckDBPyConnection) -> None:
        """v_candles_1m — standardized 1-minute candle view."""
        conn.execute("""
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
            FROM read_parquet('market_data/equities/candles/timeframe=1m/symbol=*/data.parquet')
        """)
        logger.debug("Created v_candles_1m")

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
        """v_latest_candle — most recent candle per symbol."""
        conn.execute("""
            CREATE OR REPLACE VIEW v_latest_candle AS
            SELECT
                c.timestamp,
                c.symbol,
                c.open,
                c.high,
                c.low,
                c.close,
                c.volume,
                c.oi
            FROM v_candles_1m c
            INNER JOIN (
                SELECT symbol, MAX(timestamp) as max_ts
                FROM v_candles_1m
                GROUP BY symbol
            ) latest ON c.symbol = latest.symbol AND c.timestamp = latest.max_ts
        """)
        logger.debug("Created v_latest_candle")
