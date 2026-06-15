"""Layer 2: Feature Views — reusable analytical features computed once, consumed everywhere."""

from __future__ import annotations

import logging

import duckdb

logger = logging.getLogger(__name__)


class FeatureViews:
    """Creates feature views in DuckDB."""

    def create_views(self, conn: duckdb.DuckDBPyConnection) -> None:
        """Create all feature views."""
        self._create_atr(conn)
        self._create_vwap(conn)
        self._create_volume(conn)
        self._create_momentum(conn)
        self._create_rsi(conn)

    def _create_atr(self, conn: duckdb.DuckDBPyConnection) -> None:
        """v_feature_atr — Average True Range."""
        conn.execute("""
            CREATE OR REPLACE VIEW v_feature_atr AS
            WITH tr AS (
                SELECT
                    symbol,
                    timestamp,
                    GREATEST(
                        high - low,
                        ABS(high - LAG(close) OVER (PARTITION BY symbol ORDER BY timestamp)),
                        ABS(low - LAG(close) OVER (PARTITION BY symbol ORDER BY timestamp))
                    ) as true_range
                FROM v_candles_1m
            )
            SELECT
                symbol,
                timestamp,
                AVG(true_range) OVER (
                    PARTITION BY symbol ORDER BY timestamp
                    ROWS BETWEEN 13 PRECEDING AND CURRENT ROW
                ) as atr_14,
                AVG(true_range) OVER (
                    PARTITION BY symbol ORDER BY timestamp
                    ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
                ) as atr_20,
                AVG(true_range) OVER (
                    PARTITION BY symbol ORDER BY timestamp
                    ROWS BETWEEN 49 PRECEDING AND CURRENT ROW
                ) as atr_50
            FROM tr
        """)
        logger.debug("Created v_feature_atr")

    def _create_vwap(self, conn: duckdb.DuckDBPyConnection) -> None:
        """v_feature_vwap — Volume Weighted Average Price."""
        conn.execute("""
            CREATE OR REPLACE VIEW v_feature_vwap AS
            WITH daily AS (
                SELECT
                    symbol,
                    CAST(timestamp AS DATE) as trade_date,
                    timestamp,
                    close,
                    volume,
                    (high + low + close) / 3.0 as typical_price,
                    SUM(volume) OVER (
                        PARTITION BY symbol, CAST(timestamp AS DATE)
                        ORDER BY timestamp
                        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                    ) as cum_volume
                FROM v_candles_1m
            )
            SELECT
                symbol,
                timestamp,
                SUM(typical_price * volume) OVER (
                    PARTITION BY symbol, trade_date
                    ORDER BY timestamp
                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                ) / NULLIF(cum_volume, 0) as vwap,
                close as current_close
            FROM daily
        """)
        logger.debug("Created v_feature_vwap")

    def _create_volume(self, conn: duckdb.DuckDBPyConnection) -> None:
        """v_feature_volume — volume analytics."""
        conn.execute("""
            CREATE OR REPLACE VIEW v_feature_volume AS
            SELECT
                symbol,
                timestamp,
                volume,
                AVG(volume) OVER (
                    PARTITION BY symbol ORDER BY timestamp
                    ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
                ) as avg_volume_20,
                AVG(volume) OVER (
                    PARTITION BY symbol ORDER BY timestamp
                    ROWS BETWEEN 49 PRECEDING AND CURRENT ROW
                ) as avg_volume_50,
                CASE
                    WHEN AVG(volume) OVER (
                        PARTITION BY symbol ORDER BY timestamp
                        ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
                    ) > 0
                    THEN volume / AVG(volume) OVER (
                        PARTITION BY symbol ORDER BY timestamp
                        ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
                    )
                    ELSE 1.0
                END as relative_volume,
                CASE
                    WHEN volume > 2.0 * AVG(volume) OVER (
                        PARTITION BY symbol ORDER BY timestamp
                        ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
                    ) THEN TRUE
                    ELSE FALSE
                END as volume_spike
            FROM v_candles_1m
        """)
        logger.debug("Created v_feature_volume")

    def _create_momentum(self, conn: duckdb.DuckDBPyConnection) -> None:
        """v_feature_momentum — rate of change and momentum score."""
        conn.execute("""
            CREATE OR REPLACE VIEW v_feature_momentum AS
            SELECT
                symbol,
                timestamp,
                close,
                LAG(close, 5) OVER (PARTITION BY symbol ORDER BY timestamp) as close_5d_ago,
                LAG(close, 10) OVER (PARTITION BY symbol ORDER BY timestamp) as close_10d_ago,
                LAG(close, 20) OVER (PARTITION BY symbol ORDER BY timestamp) as close_20d_ago,
                CASE
                    WHEN LAG(close, 5) OVER (PARTITION BY symbol ORDER BY timestamp) > 0
                    THEN (close - LAG(close, 5) OVER (PARTITION BY symbol ORDER BY timestamp))
                         / LAG(close, 5) OVER (PARTITION BY symbol ORDER BY timestamp) * 100
                    ELSE 0
                END as roc_5,
                CASE
                    WHEN LAG(close, 10) OVER (PARTITION BY symbol ORDER BY timestamp) > 0
                    THEN (close - LAG(close, 10) OVER (PARTITION BY symbol ORDER BY timestamp))
                         / LAG(close, 10) OVER (PARTITION BY symbol ORDER BY timestamp) * 100
                    ELSE 0
                END as roc_10,
                CASE
                    WHEN LAG(close, 20) OVER (PARTITION BY symbol ORDER BY timestamp) > 0
                    THEN (close - LAG(close, 20) OVER (PARTITION BY symbol ORDER BY timestamp))
                         / LAG(close, 20) OVER (PARTITION BY symbol ORDER BY timestamp) * 100
                    ELSE 0
                END as roc_20
            FROM v_candles_1m
        """)
        logger.debug("Created v_feature_momentum")

    def _create_rsi(self, conn: duckdb.DuckDBPyConnection) -> None:
        """v_feature_rsi — Relative Strength Index."""
        conn.execute("""
            CREATE OR REPLACE VIEW v_feature_rsi AS
            WITH changes AS (
                SELECT
                    symbol,
                    timestamp,
                    close - LAG(close) OVER (PARTITION BY symbol ORDER BY timestamp) as change
                FROM v_candles_1m
            ),
            gains_losses AS (
                SELECT
                    symbol,
                    timestamp,
                    change,
                    CASE WHEN change > 0 THEN change ELSE 0 END as gain,
                    CASE WHEN change < 0 THEN ABS(change) ELSE 0 END as loss
                FROM changes
            ),
            avg_gl AS (
                SELECT
                    symbol,
                    timestamp,
                    AVG(gain) OVER (
                        PARTITION BY symbol ORDER BY timestamp
                        ROWS BETWEEN 13 PRECEDING AND CURRENT ROW
                    ) as avg_gain_14,
                    AVG(loss) OVER (
                        PARTITION BY symbol ORDER BY timestamp
                        ROWS BETWEEN 13 PRECEDING AND CURRENT ROW
                    ) as avg_loss_14,
                    AVG(gain) OVER (
                        PARTITION BY symbol ORDER BY timestamp
                        ROWS BETWEEN 20 PRECEDING AND CURRENT ROW
                    ) as avg_gain_21,
                    AVG(loss) OVER (
                        PARTITION BY symbol ORDER BY timestamp
                        ROWS BETWEEN 20 PRECEDING AND CURRENT ROW
                    ) as avg_loss_21
                FROM gains_losses
            )
            SELECT
                symbol,
                timestamp,
                CASE
                    WHEN avg_loss_14 = 0 THEN 100
                    ELSE 100 - (100 / (1 + avg_gain_14 / avg_loss_14))
                END as rsi_14,
                CASE
                    WHEN avg_loss_21 = 0 THEN 100
                    ELSE 100 - (100 / (1 + avg_gain_21 / avg_loss_21))
                END as rsi_21
            FROM avg_gl
        """)
        logger.debug("Created v_feature_rsi")
