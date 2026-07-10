"""Layer 6: Strategy Views — intraday trading signals.

Uses materialized tables for fast queries.
"""

from __future__ import annotations

import logging

import duckdb

logger = logging.getLogger(__name__)


class StrategyViews:
    """Creates strategy-ready views in DuckDB."""

    def create_views(self, conn: duckdb.DuckDBPyConnection) -> None:
        """Create all strategy views."""
        self._create_strategy_halftrend(conn)
        self._create_strategy_candidates(conn)
        self._create_strategy_momentum(conn)
        self._create_strategy_breakout(conn)

    def _create_strategy_halftrend(self, conn: duckdb.DuckDBPyConnection) -> None:
        """v_strategy_halftrend — HalfTrend signals for intraday."""
        conn.execute("""
            CREATE OR REPLACE VIEW v_strategy_halftrend AS
            SELECT
                symbol,
                ltp,
                intraday_score,
                signal,
                trend,
                rsi_approx as rsi_14,
                roc_5,
                relative_volume,
                atr_approx as atr_14,
                day_high,
                day_low,
                -- HalfTrend levels
                CASE
                    WHEN signal = 'BUY' THEN ltp - atr_approx
                    WHEN signal = 'SELL' THEN ltp + atr_approx
                    ELSE NULL
                END as stop_loss,
                CASE
                    WHEN signal = 'BUY' THEN ltp + 2 * atr_approx
                    WHEN signal = 'SELL' THEN ltp - 2 * atr_approx
                    ELSE NULL
                END as target
            FROM m_intraday_snapshot
            WHERE signal IN ('BUY', 'SELL', 'BREAKOUT')
        """)
        logger.debug("Created v_strategy_halftrend")

    def _create_strategy_candidates(self, conn: duckdb.DuckDBPyConnection) -> None:
        """v_strategy_candidates — combined scanner + features for strategy."""
        conn.execute("""
            CREATE OR REPLACE VIEW v_strategy_candidates AS
            SELECT
                symbol,
                ltp,
                intraday_score,
                signal,
                trend,
                rsi_approx as rsi_14,
                roc_5,
                roc_10,
                roc_20,
                relative_volume,
                sma_20,
                sma_50,
                atr_approx as atr_14,
                day_open,
                day_high,
                day_low,
                day_close,
                day_volume,
                bars_today,
                -- Risk metrics
                CASE
                    WHEN atr_approx > 0 THEN atr_approx / ltp * 100
                    ELSE 0
                END as atr_pct,
                CASE
                    WHEN ltp > 0 THEN (day_high - day_low) / ltp * 100
                    ELSE 0
                END as range_pct,
                -- Position sizing
                CASE
                    WHEN atr_approx > 0 THEN ROUND(1000 / atr_approx) * 100
                    ELSE 0
                END as suggested_quantity
            FROM m_intraday_snapshot
            ORDER BY intraday_score DESC, symbol
        """)
        logger.debug("Created v_strategy_candidates")

    def _create_strategy_momentum(self, conn: duckdb.DuckDBPyConnection) -> None:
        """v_strategy_momentum — momentum signals for intraday."""
        conn.execute("""
            CREATE OR REPLACE VIEW v_strategy_momentum AS
            SELECT
                symbol,
                ltp,
                intraday_score,
                signal,
                trend,
                rsi_approx as rsi_14,
                roc_5,
                roc_10,
                relative_volume,
                atr_approx as atr_14,
                -- Momentum signal
                CASE
                    WHEN rsi_approx < 35 AND roc_5 > 0 AND trend = 'Bullish' AND relative_volume > 1.5
                    THEN 'STRONG_BUY'
                    WHEN rsi_approx < 45 AND roc_5 > 0 AND trend = 'Bullish'
                    THEN 'BUY'
                    WHEN rsi_approx > 70 AND roc_5 < 0
                    THEN 'SELL'
                    WHEN rsi_approx > 60 AND trend = 'Bearish'
                    THEN 'STRONG_SELL'
                    ELSE 'NEUTRAL'
                END as momentum_signal,
                -- Entry/Exit levels
                CASE
                    WHEN rsi_approx < 35 AND roc_5 > 0 THEN ltp - atr_approx
                    WHEN rsi_approx > 70 AND roc_5 < 0 THEN ltp + atr_approx
                    ELSE NULL
                END as entry_level,
                CASE
                    WHEN rsi_approx < 35 AND roc_5 > 0 THEN ltp + 2 * atr_approx
                    WHEN rsi_approx > 70 AND roc_5 < 0 THEN ltp - 2 * atr_approx
                    ELSE NULL
                END as target_level
            FROM m_intraday_snapshot
            WHERE momentum_signal != 'NEUTRAL'
        """)
        logger.debug("Created v_strategy_momentum")

    def _create_strategy_breakout(self, conn: duckdb.DuckDBPyConnection) -> None:
        """v_strategy_breakout — breakout signals for intraday."""
        conn.execute("""
            CREATE OR REPLACE VIEW v_strategy_breakout AS
            SELECT
                symbol,
                ltp,
                intraday_score,
                signal,
                trend,
                rsi_approx as rsi_14,
                relative_volume,
                roc_5,
                atr_approx as atr_14,
                day_high,
                day_low,
                -- Breakout levels
                CASE
                    WHEN relative_volume > 2.0 AND trend = 'Bullish'
                    THEN day_high
                    WHEN relative_volume > 1.5 AND trend = 'Bearish'
                    THEN day_low
                    ELSE NULL
                END as breakout_level,
                CASE
                    WHEN relative_volume > 2.0 AND trend = 'Bullish'
                    THEN ltp + 2 * atr_approx
                    WHEN relative_volume > 1.5 AND trend = 'Bearish'
                    THEN ltp - 2 * atr_approx
                    ELSE NULL
                END as breakout_target,
                CASE
                    WHEN relative_volume > 2.0 AND trend = 'Bullish'
                    THEN ltp - atr_approx
                    WHEN relative_volume > 1.5 AND trend = 'Bearish'
                    THEN ltp + atr_approx
                    ELSE NULL
                END as breakout_stop
            FROM m_intraday_snapshot
            WHERE signal = 'BREAKOUT'
               OR (relative_volume > 2.0 AND trend = 'Bullish')
               OR (relative_volume > 1.5 AND trend = 'Bearish')
        """)
        logger.debug("Created v_strategy_breakout")
