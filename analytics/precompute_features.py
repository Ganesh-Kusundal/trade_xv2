"""Pre-compute and materialize technical features as partitioned Parquet.

Features are computed once, stored with point-in-time columns (published_at),
and sorted by (symbol, event_time) for efficient as-of joins.

Usage:
    python -m analytics.precompute_features [--date-to 2024-03-15] [--force]

    # Or programmatically:
    from analytics.precompute_features import FeaturePrecomputer
    pc = FeaturePrecomputer()
    pc.compute_daily_features()
    pc.compute_intraday_features()
"""

from __future__ import annotations

import argparse
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import duckdb

from datalake.duckdb_utils import DEFAULT_CATALOG_PATH, get_pool

logger = logging.getLogger(__name__)

FEATURES_ROOT = Path("market_data/features")
TARGET_FILE_MB = 150

FEATURE_DAILY_COLUMNS = [
    "symbol", "event_time", "published_at",
    "open", "high", "low", "close", "volume",
]

FEATURE_INTRADAY_COLUMNS = [
    "symbol", "event_time", "published_at",
    "open", "high", "low", "close", "volume",
]


@dataclass
class FeaturePrecomputer:
    """Pre-computes and materializes technical features into partitioned Parquet.

    Attributes:
        catalog_path: Path to DuckDB catalog file.
        intraday_days: Number of recent days for intraday features.
        force: If True, re-compute even if output already exists.
        features_root: Root directory for feature output.
        target_file_mb: Target size for each Parquet file.
    """

    catalog_path: str | Path = DEFAULT_CATALOG_PATH
    intraday_days: int = 30
    force: bool = False
    features_root: Path = FEATURES_ROOT
    target_file_mb: int = TARGET_FILE_MB

    def _get_conn(self) -> duckdb.DuckDBPyConnection:
        """Acquire a DuckDB connection from the pool."""
        return get_pool().acquire(self.catalog_path, read_only=False)

    def _release_conn(self, conn: duckdb.DuckDBPyConnection) -> None:
        get_pool().release(self.catalog_path)

    def _ensure_views(self, conn: duckdb.DuckDBPyConnection) -> None:
        """Ensure base views exist."""
        from analytics.views.base import BaseViews

        BaseViews().create_views(conn)

    def _compute_published_at(self, conn: duckdb.DuckDBPyConnection) -> datetime:
        """Get the current max timestamp as the batch published_at."""
        result = conn.execute("SELECT MAX(timestamp) FROM v_candles_1m").fetchone()
        return result[0] if result[0] else datetime.now()

    @staticmethod
    def _feature_path(feature_name: str) -> Path:
        return FEATURES_ROOT / feature_name

    def _feature_exists(self, feature_name: str) -> bool:
        feature_dir = self._feature_path(feature_name)
        if not feature_dir.exists():
            return False
        parquet_files = list(feature_dir.rglob("data_*.parquet"))
        return len(parquet_files) > 0

    # ── Daily features ─────────────────────────────────────────────────────

    def compute_daily_features(
        self, conn: duckdb.DuckDBPyConnection | None = None, published_at: datetime | None = None
    ) -> list[str]:
        """Compute all daily features and write as partitioned Parquet.

        Returns list of feature table paths written.
        """
        if conn is None:
            conn = self._get_conn()
            should_release = True
        else:
            should_release = False

        try:
            self._ensure_views(conn)
            if published_at is None:
                published_at = self._compute_published_at(conn)

            written: list[str] = []

            # Daily feature: ATR, RSI, SMA, EMA, MACD, Bollinger, ROC, Volume, VWAP
            daily_sql = self._build_daily_features_sql(published_at)

            if not self.force and self._feature_exists("daily_features"):
                logger.info("daily_features already exists, skipping (use --force to re-compute)")
            else:
                self._write_feature_table(conn, "daily_features", daily_sql)
                written.append("daily_features")
                logger.info("Wrote daily_features")

            return written
        finally:
            if should_release:
                self._release_conn(conn)

    def _build_daily_features_sql(self, published_at: datetime) -> str:
        """Build SQL for all daily features in one pass over daily aggregated bars."""

        published_at_str = published_at.strftime("%Y-%m-%d %H:%M:%S")

        return f"""
        WITH daily AS (
            SELECT
                CAST(timestamp AS DATE) as event_time,
                symbol,
                FIRST(open ORDER BY timestamp) as open,
                MAX(high) as high,
                MIN(low) as low,
                LAST(close ORDER BY timestamp) as close,
                SUM(volume) as volume
            FROM v_candles_1m
            GROUP BY CAST(timestamp AS DATE), symbol
        ),
        tr AS (
            SELECT
                symbol,
                event_time,
                open,
                high,
                low,
                close,
                volume,
                GREATEST(
                    high - low,
                    ABS(high - LAG(close) OVER (PARTITION BY symbol ORDER BY event_time)),
                    ABS(low - LAG(close) OVER (PARTITION BY symbol ORDER BY event_time))
                ) as true_range
            FROM daily
        ),
        changes AS (
            SELECT
                symbol,
                event_time,
                open,
                high,
                low,
                close,
                volume,
                true_range,
                close - LAG(close) OVER (PARTITION BY symbol ORDER BY event_time) as change
            FROM tr
        ),
        gains_losses AS (
            SELECT
                symbol,
                event_time,
                open,
                high,
                low,
                close,
                volume,
                true_range,
                change,
                CASE WHEN change > 0 THEN change ELSE 0 END as gain,
                CASE WHEN change < 0 THEN ABS(change) ELSE 0 END as loss
            FROM changes
        ),
        daily_filled AS (
            SELECT
                symbol,
                event_time,
                open,
                high,
                low,
                close,
                volume,
                true_range,
                AVG(true_range) OVER (
                    PARTITION BY symbol ORDER BY event_time
                    ROWS BETWEEN 13 PRECEDING AND CURRENT ROW
                ) as atr_14,
                AVG(gain) OVER (
                    PARTITION BY symbol ORDER BY event_time
                    ROWS BETWEEN 13 PRECEDING AND CURRENT ROW
                ) as avg_gain_14,
                AVG(loss) OVER (
                    PARTITION BY symbol ORDER BY event_time
                    ROWS BETWEEN 13 PRECEDING AND CURRENT ROW
                ) as avg_loss_14,
                AVG(gain) OVER (
                    PARTITION BY symbol ORDER BY event_time
                    ROWS BETWEEN 20 PRECEDING AND CURRENT ROW
                ) as avg_gain_21,
                AVG(loss) OVER (
                    PARTITION BY symbol ORDER BY event_time
                    ROWS BETWEEN 20 PRECEDING AND CURRENT ROW
                ) as avg_loss_21,
                AVG(close) OVER (
                    PARTITION BY symbol ORDER BY event_time
                    ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
                ) as sma_20,
                AVG(close) OVER (
                    PARTITION BY symbol ORDER BY event_time
                    ROWS BETWEEN 49 PRECEDING AND CURRENT ROW
                ) as sma_50
            FROM gains_losses
        )
        SELECT
            symbol,
            event_time,
            CAST('{published_at_str}' AS TIMESTAMP) as published_at,
            open,
            high,
            low,
            close,
            volume,
            atr_14,
            CASE
                WHEN avg_loss_14 = 0 THEN 100.0
                ELSE 100.0 - (100.0 / (1.0 + avg_gain_14 / NULLIF(avg_loss_14, 0)))
            END as rsi_14,
            CASE
                WHEN avg_loss_21 = 0 THEN 100.0
                ELSE 100.0 - (100.0 / (1.0 + avg_gain_21 / NULLIF(avg_loss_21, 0)))
            END as rsi_21,
            sma_20,
            sma_50,
            AVG(close) OVER (
                PARTITION BY symbol ORDER BY event_time
                ROWS BETWEEN 11 PRECEDING AND CURRENT ROW
            ) as ema_12,
            AVG(close) OVER (
                PARTITION BY symbol ORDER BY event_time
                ROWS BETWEEN 25 PRECEDING AND CURRENT ROW
            ) as ema_26,
            AVG(close) OVER (
                PARTITION BY symbol ORDER BY event_time
                ROWS BETWEEN 11 PRECEDING AND CURRENT ROW
            ) - AVG(close) OVER (
                PARTITION BY symbol ORDER BY event_time
                ROWS BETWEEN 25 PRECEDING AND CURRENT ROW
            ) as macd,
            AVG(AVG(close) OVER (
                PARTITION BY symbol ORDER BY event_time
                ROWS BETWEEN 11 PRECEDING AND CURRENT ROW
            ) - AVG(close) OVER (
                PARTITION BY symbol ORDER BY event_time
                ROWS BETWEEN 25 PRECEDING AND CURRENT ROW
            )) OVER (
                PARTITION BY symbol ORDER BY event_time
                ROWS BETWEEN 8 PRECEDING AND CURRENT ROW
            ) as macd_signal,
            (
                AVG(close) OVER (
                    PARTITION BY symbol ORDER BY event_time
                    ROWS BETWEEN 11 PRECEDING AND CURRENT ROW
                ) - AVG(close) OVER (
                    PARTITION BY symbol ORDER BY event_time
                    ROWS BETWEEN 25 PRECEDING AND CURRENT ROW
                )
            ) - AVG(AVG(close) OVER (
                PARTITION BY symbol ORDER BY event_time
                ROWS BETWEEN 11 PRECEDING AND CURRENT ROW
            ) - AVG(close) OVER (
                PARTITION BY symbol ORDER BY event_time
                ROWS BETWEEN 25 PRECEDING AND CURRENT ROW
            )) OVER (
                PARTITION BY symbol ORDER BY event_time
                ROWS BETWEEN 8 PRECEDING AND CURRENT ROW
            ) as macd_histogram,
            AVG(close) OVER (
                PARTITION BY symbol ORDER BY event_time
                ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
            ) + 2.0 * STDDEV(close) OVER (
                PARTITION BY symbol ORDER BY event_time
                ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
            ) as bb_upper,
            AVG(close) OVER (
                PARTITION BY symbol ORDER BY event_time
                ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
            ) - 2.0 * STDDEV(close) OVER (
                PARTITION BY symbol ORDER BY event_time
                ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
            ) as bb_lower,
            AVG(close) OVER (
                PARTITION BY symbol ORDER BY event_time
                ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
            ) as bb_mid,
            CASE
                WHEN LAG(close, 5) OVER (PARTITION BY symbol ORDER BY event_time) > 0
                THEN (close - LAG(close, 5) OVER (PARTITION BY symbol ORDER BY event_TIME))
                     / LAG(close, 5) OVER (PARTITION BY symbol ORDER BY event_time) * 100
                ELSE 0
            END as roc_5,
            CASE
                WHEN LAG(close, 10) OVER (PARTITION BY symbol ORDER BY event_time) > 0
                THEN (close - LAG(close, 10) OVER (PARTITION BY symbol ORDER BY event_time))
                     / LAG(close, 10) OVER (PARTITION BY symbol ORDER BY event_time) * 100
                ELSE 0
            END as roc_10,
            CASE
                WHEN LAG(close, 20) OVER (PARTITION BY symbol ORDER BY event_time) > 0
                THEN (close - LAG(close, 20) OVER (PARTITION BY symbol ORDER BY event_time))
                     / LAG(close, 20) OVER (PARTITION BY symbol ORDER BY event_time) * 100
                ELSE 0
            END as roc_20,
            AVG(volume) OVER (
                PARTITION BY symbol ORDER BY event_time
                ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
            ) as volume_sma_20,
            AVG(volume) OVER (
                PARTITION BY symbol ORDER BY event_time
                ROWS BETWEEN 49 PRECEDING AND CURRENT ROW
            ) as volume_sma_50,
            CASE
                WHEN AVG(volume) OVER (
                    PARTITION BY symbol ORDER BY event_time
                    ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
                ) > 0
                THEN volume / AVG(volume) OVER (
                    PARTITION BY symbol ORDER BY event_time
                    ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
                )
                ELSE 1.0
            END as relative_volume_20,
            SUM(volume * (high + low + close) / 3.0) OVER (
                PARTITION BY symbol, event_time
            ) / NULLIF(SUM(volume) OVER (
                PARTITION BY symbol, event_time
            ), 0) as vwap_daily,
            true_range,
            AVG(true_range) OVER (
                PARTITION BY symbol ORDER BY event_time
                ROWS BETWEEN 13 PRECEDING AND CURRENT ROW
            ) as avg_true_range_14,
            YEAR(event_time) as year,
            MONTH(event_time) as month
        FROM daily_filled
        QUALIFY ROW_NUMBER() OVER (PARTITION BY symbol, event_time) = 1
        """

    # ── Intraday features ──────────────────────────────────────────────────

    def compute_intraday_features(
        self, conn: duckdb.DuckDBPyConnection | None = None, published_at: datetime | None = None
    ) -> list[str]:
        """Compute intraday features from 1m candles (last N days)."""
        if conn is None:
            conn = self._get_conn()
            should_release = True
        else:
            should_release = False

        try:
            self._ensure_views(conn)
            if published_at is None:
                published_at = self._compute_published_at(conn)

            written: list[str] = []
            intraday_sql = self._build_intraday_features_sql(published_at)

            if not self.force and self._feature_exists("intraday_features"):
                logger.info("intraday_features already exists, skipping")
            else:
                self._write_feature_table(conn, "intraday_features", intraday_sql)
                written.append("intraday_features")
                logger.info("Wrote intraday_features")

            return written
        finally:
            if should_release:
                self._release_conn(conn)

    def _build_intraday_features_sql(self, published_at: datetime) -> str:
        published_at_str = published_at.strftime("%Y-%m-%d %H:%M:%S")

        return f"""
        WITH base AS (
            SELECT
                timestamp as event_time,
                symbol,
                open,
                high,
                low,
                close,
                volume
            FROM v_candles_1m
            WHERE timestamp >= (SELECT MAX(timestamp) FROM v_candles_1m) - INTERVAL '{self.intraday_days} days'
        ),
        tr AS (
            SELECT
                symbol,
                event_time,
                open,
                high,
                low,
                close,
                volume,
                GREATEST(
                    high - low,
                    ABS(high - LAG(close) OVER (PARTITION BY symbol ORDER BY event_time)),
                    ABS(low - LAG(close) OVER (PARTITION BY symbol ORDER BY event_time))
                ) as true_range
            FROM base
        ),
        changes AS (
            SELECT
                symbol,
                event_time,
                open,
                high,
                low,
                close,
                volume,
                true_range,
                close - LAG(close) OVER (PARTITION BY symbol ORDER BY event_time) as change
            FROM tr
        ),
        gains_losses AS (
            SELECT
                symbol,
                event_time,
                open,
                high,
                low,
                close,
                volume,
                true_range,
                change,
                CASE WHEN change > 0 THEN change ELSE 0 END as gain,
                CASE WHEN change < 0 THEN ABS(change) ELSE 0 END as loss
            FROM changes
        )
        SELECT
            symbol,
            event_time,
            CAST('{published_at_str}' AS TIMESTAMP) as published_at,
            open,
            high,
            low,
            close,
            volume,
            AVG(true_range) OVER (
                PARTITION BY symbol ORDER BY event_time
                ROWS BETWEEN 13 PRECEDING AND CURRENT ROW
            ) as atr_14,
            CASE
                WHEN AVG(CASE WHEN change < 0 THEN ABS(change) ELSE 0 END) OVER (
                    PARTITION BY symbol ORDER BY event_time
                    ROWS BETWEEN 13 PRECEDING AND CURRENT ROW
                ) = 0 THEN 100.0
                ELSE 100.0 - (100.0 / (1.0 +
                    AVG(CASE WHEN change > 0 THEN change ELSE 0 END) OVER (
                        PARTITION BY symbol ORDER BY event_time
                        ROWS BETWEEN 13 PRECEDING AND CURRENT ROW
                    ) /
                    NULLIF(AVG(CASE WHEN change < 0 THEN ABS(change) ELSE 0 END) OVER (
                        PARTITION BY symbol ORDER BY event_time
                        ROWS BETWEEN 13 PRECEDING AND CURRENT ROW
                    ), 0)
                ))
            END as rsi_14,
            CASE
                WHEN AVG(CASE WHEN change < 0 THEN ABS(change) ELSE 0 END) OVER (
                    PARTITION BY symbol ORDER BY event_time
                    ROWS BETWEEN 20 PRECEDING AND CURRENT ROW
                ) = 0 THEN 100.0
                ELSE 100.0 - (100.0 / (1.0 +
                    AVG(CASE WHEN change > 0 THEN change ELSE 0 END) OVER (
                        PARTITION BY symbol ORDER BY event_time
                        ROWS BETWEEN 20 PRECEDING AND CURRENT ROW
                    ) /
                    NULLIF(AVG(CASE WHEN change < 0 THEN ABS(change) ELSE 0 END) OVER (
                        PARTITION BY symbol ORDER BY event_time
                        ROWS BETWEEN 20 PRECEDING AND CURRENT ROW
                    ), 0)
                ))
            END as rsi_21,
            AVG(close) OVER (
                PARTITION BY symbol ORDER BY event_time
                ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
            ) as sma_20,
            AVG(close) OVER (
                PARTITION BY symbol ORDER BY event_time
                ROWS BETWEEN 49 PRECEDING AND CURRENT ROW
            ) as sma_50,
            AVG(close) OVER (
                PARTITION BY symbol ORDER BY event_time
                ROWS BETWEEN 11 PRECEDING AND CURRENT ROW
            ) as ema_12,
            AVG(close) OVER (
                PARTITION BY symbol ORDER BY event_time
                ROWS BETWEEN 25 PRECEDING AND CURRENT ROW
            ) as ema_26,
            AVG(close) OVER (
                PARTITION BY symbol ORDER BY event_time
                ROWS BETWEEN 11 PRECEDING AND CURRENT ROW
            ) - AVG(close) OVER (
                PARTITION BY symbol ORDER BY event_time
                ROWS BETWEEN 25 PRECEDING AND CURRENT ROW
            ) as macd,
            AVG(close) OVER (
                PARTITION BY symbol ORDER BY event_time
                ROWS BETWEEN 11 PRECEDING AND CURRENT ROW
            ) - AVG(close) OVER (
                PARTITION BY symbol ORDER BY event_time
                ROWS BETWEEN 25 PRECEDING AND CURRENT ROW
            ) as macd_signal,
            (
                AVG(close) OVER (
                    PARTITION BY symbol ORDER BY event_time
                    ROWS BETWEEN 11 PRECEDING AND CURRENT ROW
                ) - AVG(close) OVER (
                    PARTITION BY symbol ORDER BY event_time
                    ROWS BETWEEN 25 PRECEDING AND CURRENT ROW
                )
            ) - AVG(AVG(close) OVER (
                PARTITION BY symbol ORDER BY event_time
                ROWS BETWEEN 11 PRECEDING AND CURRENT ROW
            ) - AVG(close) OVER (
                PARTITION BY symbol ORDER BY event_time
                ROWS BETWEEN 25 PRECEDING AND CURRENT ROW
            )) OVER (
                PARTITION BY symbol ORDER BY event_time
                ROWS BETWEEN 8 PRECEDING AND CURRENT ROW
            ) as macd_histogram,
            AVG(close) OVER (
                PARTITION BY symbol ORDER BY event_time
                ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
            ) + 2.0 * STDDEV(close) OVER (
                PARTITION BY symbol ORDER BY event_time
                ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
            ) as bb_upper,
            AVG(close) OVER (
                PARTITION BY symbol ORDER BY event_time
                ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
            ) - 2.0 * STDDEV(close) OVER (
                PARTITION BY symbol ORDER BY event_time
                ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
            ) as bb_lower,
            AVG(close) OVER (
                PARTITION BY symbol ORDER BY event_time
                ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
            ) as bb_mid,
            CASE
                WHEN LAG(close, 5) OVER (PARTITION BY symbol ORDER BY event_time) > 0
                THEN (close - LAG(close, 5) OVER (PARTITION BY symbol ORDER BY event_time))
                     / LAG(close, 5) OVER (PARTITION BY symbol ORDER BY event_time) * 100
                ELSE 0
            END as roc_5,
            CASE
                WHEN LAG(close, 10) OVER (PARTITION BY symbol ORDER BY event_time) > 0
                THEN (close - LAG(close, 10) OVER (PARTITION BY symbol ORDER BY event_time))
                     / LAG(close, 10) OVER (PARTITION BY symbol ORDER BY event_time) * 100
                ELSE 0
            END as roc_10,
            CASE
                WHEN LAG(close, 20) OVER (PARTITION BY symbol ORDER BY event_time) > 0
                THEN (close - LAG(close, 20) OVER (PARTITION BY symbol ORDER BY event_time))
                     / LAG(close, 20) OVER (PARTITION BY symbol ORDER BY event_time) * 100
                ELSE 0
            END as roc_20,
            AVG(volume) OVER (
                PARTITION BY symbol ORDER BY event_time
                ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
            ) as volume_sma_20,
            AVG(volume) OVER (
                PARTITION BY symbol ORDER BY event_time
                ROWS BETWEEN 49 PRECEDING AND CURRENT ROW
            ) as volume_sma_50,
            CASE
                WHEN AVG(volume) OVER (
                    PARTITION BY symbol ORDER BY event_time
                    ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
                ) > 0
                THEN volume / AVG(volume) OVER (
                    PARTITION BY symbol ORDER BY event_time
                    ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
                )
                ELSE 1.0
            END as relative_volume_20,
            SUM(volume * (high + low + close) / 3.0) OVER (
                PARTITION BY symbol, CAST(event_time AS DATE)
                ORDER BY event_time
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) / NULLIF(SUM(volume) OVER (
                PARTITION BY symbol, CAST(event_time AS DATE)
                ORDER BY event_time
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ), 0) as vwap_daily,
            true_range,
            AVG(true_range) OVER (
                PARTITION BY symbol ORDER BY event_time
                ROWS BETWEEN 13 PRECEDING AND CURRENT ROW
            ) as avg_true_range_14,
            YEAR(event_time) as year,
            MONTH(event_time) as month
        FROM gains_losses
        QUALIFY ROW_NUMBER() OVER (PARTITION BY symbol, event_time) = 1
        """

    # ── Options features ───────────────────────────────────────────────────

    def compute_options_features(
        self, conn: duckdb.DuckDBPyConnection | None = None, published_at: datetime | None = None
    ) -> list[str]:
        """Compute options-specific features (PCR, max pain, IV skew)."""
        if conn is None:
            conn = self._get_conn()
            should_release = True
        else:
            should_release = False

        try:
            if published_at is None:
                published_at = self._compute_published_at(conn)

            written: list[str] = []
            options_sql = self._build_options_features_sql(published_at)

            if not self.force and self._feature_exists("options_features"):
                logger.info("options_features already exists, skipping")
            else:
                self._write_feature_table(conn, "options_features", options_sql)
                written.append("options_features")
                logger.info("Wrote options_features")

            return written
        finally:
            if should_release:
                self._release_conn(conn)

    def _build_options_features_sql(self, published_at: datetime) -> str:
        published_at_str = published_at.strftime("%Y-%m-%d %H:%M:%S")

        return f"""
        WITH option_data AS (
            SELECT
                timestamp as event_time,
                underlying as symbol,
                strike,
                option_type,
                oi,
                change_in_oi,
                volume,
                iv,
                ltp,
                expiry_kind,
                expiry_code,
                expiry_date,
                spot
            FROM read_parquet('market_data/options/chains/expiry=*/underlying=*/data.parquet')
            WHERE timestamp >= (SELECT MAX(timestamp) FROM v_candles_1m) - INTERVAL '30 days'
        ),
        pcr AS (
            SELECT
                event_time,
                symbol,
                SUM(CASE WHEN option_type = 'CE' THEN volume ELSE 0 END) as total_ce_volume,
                SUM(CASE WHEN option_type = 'PE' THEN volume ELSE 0 END) as total_pe_volume,
                SUM(CASE WHEN option_type = 'CE' THEN oi ELSE 0 END) as total_ce_oi,
                SUM(CASE WHEN option_type = 'PE' THEN oi ELSE 0 END) as total_pe_oi,
                AVG(spot) as spot_price
            FROM option_data
            GROUP BY event_time, symbol
        ),
        iv_skew_data AS (
            SELECT
                event_time,
                symbol,
                strike,
                option_type,
                iv,
                spot,
                ROW_NUMBER() OVER (
                    PARTITION BY event_time, symbol, option_type
                    ORDER BY ABS(strike - spot)
                ) as dist_rank
            FROM option_data
            WHERE iv IS NOT NULL
        ),
        atm_iv AS (
            SELECT
                event_time,
                symbol,
                MAX(CASE WHEN option_type = 'CE' AND dist_rank = 1 THEN iv END) as atm_call_iv,
                MAX(CASE WHEN option_type = 'PE' AND dist_rank = 1 THEN iv END) as atm_put_iv
            FROM iv_skew_data
            WHERE dist_rank <= 3
            GROUP BY event_time, symbol
        ),
        otm_iv AS (
            SELECT
                a.event_time,
                a.symbol,
                AVG(CASE
                    WHEN a.option_type = 'PE' AND a.strike < a.spot
                    THEN a.iv
                END) as otm_put_iv,
                AVG(CASE
                    WHEN a.option_type = 'CE' AND a.strike > a.spot
                    THEN a.iv
                END) as otm_call_iv
            FROM option_data a
            WHERE a.iv IS NOT NULL
            GROUP BY a.event_time, a.symbol
        ),
        max_pain_data AS (
            SELECT
                a.event_time,
                a.symbol,
                a.strike,
                a.spot,
                SUM(b.oi * CASE
                    WHEN b.option_type = 'CE' THEN GREATEST(0, a.strike - b.strike)
                    ELSE GREATEST(0, b.strike - a.strike)
                END) as total_pain
            FROM option_data a
            JOIN option_data b
                ON a.event_time = b.event_time
                AND a.symbol = b.symbol
            GROUP BY a.event_time, a.symbol, a.strike, a.spot
        ),
        max_pain AS (
            SELECT
                event_time,
                symbol,
                FIRST(strike ORDER BY total_pain ASC) as max_pain_strike,
                FIRST(spot ORDER BY total_pain ASC) as spot_at_max_pain
            FROM max_pain_data
            GROUP BY event_time, symbol
        )
        SELECT
            p.event_time,
            p.symbol,
            CAST('{published_at_str}' AS TIMESTAMP) as published_at,
            CASE WHEN p.total_ce_volume > 0
                THEN ROUND(p.total_pe_volume * 1.0 / p.total_ce_volume, 4)
                ELSE NULL
            END as pcr_volume,
            CASE WHEN p.total_ce_oi > 0
                THEN ROUND(p.total_pe_oi * 1.0 / p.total_ce_oi, 4)
                ELSE NULL
            END as pcr_oi,
            mp.max_pain_strike,
            ROUND(oi.otm_put_iv - oi.otm_call_iv, 4) as iv_skew,
            YEAR(p.event_time) as year,
            MONTH(p.event_time) as month
        FROM pcr p
        LEFT JOIN max_pain mp
            ON p.event_time = mp.event_time AND p.symbol = mp.symbol
        LEFT JOIN otm_iv oi
            ON p.event_time = oi.event_time AND p.symbol = oi.symbol
        LEFT JOIN atm_iv ai
            ON p.event_time = ai.event_time AND p.symbol = ai.symbol
        QUALIFY ROW_NUMBER() OVER (PARTITION BY p.symbol, p.event_time) = 1
        """

    # ── Write utilities ────────────────────────────────────────────────────

    def _write_feature_table(self, conn: duckdb.DuckDBPyConnection, name: str, sql: str) -> Path:
        """Write a feature query result as partitioned Parquet."""
        feature_dir = self._feature_path(name)
        feature_dir.mkdir(parents=True, exist_ok=True)

        temp_table = f"_precompute_{name}_{int(time.time() * 1_000_000)}"
        try:
            conn.execute(f"DROP TABLE IF EXISTS {temp_table}")

            copy_sql = f"""
                COPY ({sql}) TO '{feature_dir}/'
                (FORMAT PARQUET, PER_THREAD_OUTPUT TRUE,
                 PARTITION_BY (year, month),
                 ORDER BY (symbol, event_time))
            """
            conn.execute(copy_sql)

            target_rows = int(self.target_file_mb * 1_000_000 / 1024)

            return feature_dir
        except Exception:
            raise
        finally:
            conn.execute(f"DROP TABLE IF EXISTS {temp_table}")

    # ── Batch compute ──────────────────────────────────────────────────────

    def compute_all(
        self, conn: duckdb.DuckDBPyConnection | None = None
    ) -> dict[str, list[str]]:
        """Compute all feature groups. Returns dict of group -> list of paths."""
        if conn is None:
            conn = self._get_conn()
            should_release = True
        else:
            should_release = False

        try:
            published_at = self._compute_published_at(conn)
            results: dict[str, list[str]] = {}
            results["daily"] = self.compute_daily_features(conn, published_at)
            results["intraday"] = self.compute_intraday_features(conn, published_at)
            results["options"] = self.compute_options_features(conn, published_at)
            return results
        finally:
            if should_release:
                self._release_conn(conn)


# ── CLI ──────────────────────────────────────────────────────────────────────


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="Pre-compute technical features")
    parser.add_argument(
        "--date-to",
        default=None,
        help="Compute features up to this date (YYYY-MM-DD). Default: latest data",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-compute even if output already exists",
    )
    args = parser.parse_args()

    pc = FeaturePrecomputer(force=args.force)
    results = pc.compute_all()
    total = sum(len(v) for v in results.values())
    logger.info("Pre-computed %d feature groups: %s", total, results)


if __name__ == "__main__":
    main()
