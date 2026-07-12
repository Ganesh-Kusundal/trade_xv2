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

# Named constants for materialization thresholds
MIN_SYMBOLS_FOR_FULL_DAY = 100  # minimum distinct symbols to consider a day "full"
DAILY_LOOKBACK_DAYS = 50  # days of daily candles for indicator warmup


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

    @staticmethod
    def materialization_sql() -> list[tuple[str, str]]:
        """SQL for intermediate tables required by scanner views.

        Returns ordered (table_name, sql) pairs — later tables depend on earlier ones.
        """
        return [
            # ─── Intraday: Current day's 1m candles ────────────────────────────
            (
                "m_intraday",
                f"""
                WITH latest_full_day AS (
                    SELECT CAST(timestamp AS DATE) as trade_date
                    FROM v_candles_1m
                    GROUP BY CAST(timestamp AS DATE)
                    HAVING COUNT(DISTINCT symbol) >= {MIN_SYMBOLS_FOR_FULL_DAY}
                    ORDER BY trade_date DESC
                    LIMIT 1
                )
                SELECT
                    i.timestamp,
                    i.symbol,
                    i.open,
                    i.high,
                    i.low,
                    i.close,
                    i.volume,
                    i.oi
                FROM v_candles_1m i
                INNER JOIN latest_full_day d ON CAST(i.timestamp AS DATE) = d.trade_date
            """,
            ),
            # ─── Recent daily: Last N days for indicator warmup ────────────────
            (
                "m_recent_daily",
                f"""
                WITH daily AS (
                    SELECT
                        CAST(timestamp AS DATE) as trade_date,
                        symbol,
                        FIRST(open ORDER BY timestamp) as open,
                        MAX(high) as high,
                        MIN(low) as low,
                        LAST(close ORDER BY timestamp) as close,
                        SUM(volume) as volume
                    FROM v_candles_1m
                    WHERE CAST(timestamp AS DATE) >= (
                        SELECT MAX(CAST(timestamp AS DATE)) - INTERVAL '{DAILY_LOOKBACK_DAYS} days'
                        FROM v_candles_1m
                    )
                    GROUP BY CAST(timestamp AS DATE), symbol
                )
                SELECT
                    trade_date,
                    symbol,
                    open,
                    high,
                    low,
                    close,
                    volume,
                    -- SMA indicators
                    AVG(close) OVER (PARTITION BY symbol ORDER BY trade_date
                        ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) as sma_20,
                    AVG(close) OVER (PARTITION BY symbol ORDER BY trade_date
                        ROWS BETWEEN 49 PRECEDING AND CURRENT ROW) as sma_50,
                    -- RSI
                    close - LAG(close) OVER (PARTITION BY symbol ORDER BY trade_date) as daily_change,
                    -- Volume
                    SUM(volume) OVER (PARTITION BY symbol ORDER BY trade_date
                        ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) / 20.0 as avg_volume_20,
                    -- Momentum
                    LAG(close, 5) OVER (PARTITION BY symbol ORDER BY trade_date) as close_5d,
                    LAG(close, 10) OVER (PARTITION BY symbol ORDER BY trade_date) as close_10d,
                    LAG(close, 20) OVER (PARTITION BY symbol ORDER BY trade_date) as close_20d
                FROM daily
            """,
            ),
            # ─── Symbol snapshot: Latest candle + all indicators (~500 rows) ────
            (
                "m_symbol_snapshot",
                """
                WITH latest AS (
                    SELECT
                        symbol,
                        LAST(timestamp ORDER BY timestamp) as last_ts,
                        LAST(close ORDER BY timestamp) as close,
                        LAST(high ORDER BY timestamp) as high,
                        LAST(low ORDER BY timestamp) as low,
                        LAST(open ORDER BY timestamp) as open,
                        LAST(volume ORDER BY timestamp) as volume,
                        SUM(volume) as total_volume_today
                    FROM m_intraday
                    GROUP BY symbol
                ),
                today_intraday AS (
                    SELECT
                        symbol,
                        COUNT(*) as bars_today,
                        MAX(high) as day_high,
                        MIN(low) as day_low,
                        FIRST(close ORDER BY timestamp) as day_open,
                        LAST(close ORDER BY timestamp) as day_close,
                        SUM(volume) as day_volume
                    FROM m_intraday
                    GROUP BY symbol
                )
                SELECT
                    l.symbol,
                    l.last_ts,
                    l.close,
                    l.high,
                    l.low,
                    l.open,
                    l.volume as last_volume,
                    t.bars_today,
                    t.day_high,
                    t.day_low,
                    t.day_open,
                    t.day_close,
                    t.day_volume,
                    r.sma_20,
                    r.sma_50,
                    r.close_5d,
                    r.close_10d,
                    r.close_20d,
                    CASE
                        WHEN r.close_5d > 0 THEN (l.close - r.close_5d) / r.close_5d * 100
                        ELSE 0
                    END as roc_5,
                    CASE
                        WHEN r.close_10d > 0 THEN (l.close - r.close_10d) / r.close_10d * 100
                        ELSE 0
                    END as roc_10,
                    CASE
                        WHEN r.close_20d > 0 THEN (l.close - r.close_20d) / r.close_20d * 100
                        ELSE 0
                    END as roc_20,
                    CASE
                        WHEN l.close > r.sma_20 AND r.sma_20 > r.sma_50 THEN 'Bullish'
                        WHEN l.close < r.sma_20 AND r.sma_20 < r.sma_50 THEN 'Bearish'
                        ELSE 'Neutral'
                    END as trend,
                    CASE
                        WHEN t.day_volume > 0 AND r.avg_volume_20 > 0
                        THEN t.day_volume / r.avg_volume_20
                        ELSE 1.0
                    END as relative_volume
                FROM latest l
                LEFT JOIN today_intraday t ON l.symbol = t.symbol
                LEFT JOIN m_recent_daily r ON l.symbol = r.symbol
                    AND r.trade_date = (SELECT MAX(trade_date) FROM m_recent_daily WHERE symbol = l.symbol)
            """,
            ),
            # ─── Intraday snapshot: Final scanner view (~500 rows) ─────────────
            (
                "m_intraday_snapshot",
                """
                SELECT
                    s.symbol,
                    s.close as ltp,
                    s.day_open,
                    s.day_high,
                    s.day_low,
                    s.day_close,
                    s.day_volume,
                    s.bars_today,
                    s.sma_20,
                    s.sma_50,
                    s.roc_5,
                    s.roc_10,
                    s.roc_20,
                    s.trend,
                    s.relative_volume,
                    s.close_5d,
                    s.close_10d,
                    s.close_20d,
                    -- 5-day price change % (not RSI — do not alias as rsi_14)
                    CASE
                        WHEN s.close_5d > 0 THEN (s.close - s.close_5d) / s.close_5d * 100
                        ELSE 0
                    END as momentum_5d_pct,
                    -- ATR approximation from daily range
                    (s.day_high - s.day_low) as atr_approx,
                    -- Composite intraday score
                    (
                        CASE
                            WHEN s.trend = 'Bullish' THEN 80
                            WHEN s.trend = 'Bearish' THEN 20
                            ELSE 50
                        END * 0.25 +
                        CASE
                            WHEN s.relative_volume > 2.0 THEN 90
                            WHEN s.relative_volume > 1.5 THEN 70
                            WHEN s.relative_volume > 1.0 THEN 50
                            ELSE 30
                        END * 0.25 +
                        CASE
                            WHEN s.roc_5 > 3 THEN 90
                            WHEN s.roc_5 > 1 THEN 70
                            WHEN s.roc_5 > 0 THEN 50
                            WHEN s.roc_5 > -1 THEN 30
                            ELSE 10
                        END * 0.25 +
                        CASE
                            WHEN s.close > s.sma_20 THEN 70
                            ELSE 30
                        END * 0.25
                    ) as intraday_score,
                    -- Signal
                    CASE
                        WHEN s.roc_5 > 0 AND s.trend = 'Bullish' AND s.relative_volume > 1.5
                        THEN 'BUY'
                        WHEN s.roc_5 < 0 AND s.trend = 'Bearish'
                        THEN 'SELL'
                        WHEN s.relative_volume > 2.0 AND s.trend = 'Bullish'
                        THEN 'BREAKOUT'
                        ELSE 'NEUTRAL'
                    END as signal
                FROM m_symbol_snapshot s
                WHERE s.bars_today > 0
            """,
            ),
        ]

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
                momentum_5d_pct,
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
                momentum_5d_pct,
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
