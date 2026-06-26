"""Relative volume queries — intraday and daily.

Provides queries for finding stocks with unusual volume:
- 14-day relative volume by 09:45 AM (first 30 minutes)
- 20-day relative volume for full day
- Custom time window relative volume

Usage:
    from datalake.relative_volume import (
        rel_volume_14d_by_time,
        rel_volume_20d_daily,
        high_rel_volume_stocks,
    )

    # Find stocks with 5x+ volume by 09:45 AM
    df = high_rel_volume_stocks(
        target_date="2026-06-10",
        min_rel_volume=5.0,
        lookback_days=14,
        cutoff_time="09:45",
    )
"""

from __future__ import annotations

import logging

import duckdb
import pandas as pd

logger = logging.getLogger(__name__)


def _get_conn(read_only: bool = True) -> duckdb.DuckDBPyConnection:
    from datalake.duckdb_utils import get_read_pool, DEFAULT_CATALOG_PATH
    return get_read_pool().acquire(str(DEFAULT_CATALOG_PATH))


def _time_condition(cutoff_time: str) -> str:
    """Build SQL WHERE clause for intraday time filter.

    Args:
        cutoff_time: Time string like "09:45", "10:00", "11:30".

    Returns:
        SQL condition string.
    """
    parts = cutoff_time.split(":")
    hr = int(parts[0])
    mn = int(parts[1]) if len(parts) > 1 else 0

    if hr == 9 and mn <= 15:
        return "FALSE"
    if hr == 9:
        return f"(EXTRACT(HOUR FROM timestamp) = 9 AND EXTRACT(MINUTE FROM timestamp) >= 15 AND EXTRACT(MINUTE FROM timestamp) <= {mn})"
    return f"(EXTRACT(HOUR FROM timestamp) = 9 AND EXTRACT(MINUTE FROM timestamp) >= 15) OR (EXTRACT(HOUR FROM timestamp) > 9 AND EXTRACT(HOUR FROM timestamp) < {hr}) OR (EXTRACT(HOUR FROM timestamp) = {hr} AND EXTRACT(MINUTE FROM timestamp) <= {mn})"


def rel_volume_14d_by_time(
    target_date: str,
    cutoff_time: str = "09:45",
    lookback_days: int = 14,
    lookback_start: str | None = None,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> pd.DataFrame:
    """Get 14-day relative volume for stocks by a specific cutoff time.

    Computes: volume_today(9:15-cutoff) / avg_14d_volume(9:15-cutoff)

    Args:
        target_date: Date to query (YYYY-MM-DD).
        cutoff_time: Intraday cutoff (default "09:45").
        lookback_days: Number of trading days for average (default 14).
        lookback_start: Optional start date for lookback window.
        conn: Optional DuckDB connection.

    Returns:
        DataFrame with columns: symbol, volume_today, avg_volume, rel_volume.
    """
    time_cond = _time_condition(cutoff_time)

    if lookback_start is None:
        from datetime import datetime, timedelta
        dt = datetime.strptime(target_date, "%Y-%m-%d")
        lookback_start = (dt - timedelta(days=lookback_days * 2)).strftime("%Y-%m-%d")

    own_conn = conn is None
    if own_conn:
        conn = _get_conn()

    try:
        sql = f"""
        WITH intraday AS (
            SELECT
                symbol,
                CAST(timestamp AS DATE) as trade_date,
                volume
            FROM all_candles
            WHERE timestamp >= '{lookback_start}'
              AND {time_cond}
        ),
        daily_agg AS (
            SELECT
                symbol,
                trade_date,
                SUM(volume) as day_volume
            FROM intraday
            GROUP BY symbol, trade_date
        ),
        with_avg AS (
            SELECT
                symbol,
                trade_date,
                day_volume,
                AVG(day_volume) OVER (
                    PARTITION BY symbol
                    ORDER BY trade_date
                    ROWS BETWEEN {lookback_days} PRECEDING AND 1 PRECEDING
                ) as avg_volume
            FROM daily_agg
        )
        SELECT
            symbol,
            trade_date,
            day_volume as volume_today,
            ROUND(avg_volume, 0) as avg_volume,
            ROUND(day_volume / NULLIF(avg_volume, 0), 2) as rel_volume
        FROM with_avg
        WHERE trade_date = '{target_date}'
          AND avg_volume > 0
        ORDER BY rel_volume DESC
        """
        return conn.execute(sql).fetchdf()
    finally:
        if own_conn:
            conn.close()


def rel_volume_20d_daily(
    target_date: str,
    lookback_days: int = 20,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> pd.DataFrame:
    """Get 20-day relative volume for full-day data.

    Computes: volume_today / avg_20d_volume

    Args:
        target_date: Date to query (YYYY-MM-DD).
        lookback_days: Number of trading days for average (default 20).
        conn: Optional DuckDB connection.

    Returns:
        DataFrame with columns: symbol, trade_date, volume_today, avg_volume, rel_volume.
    """
    own_conn = conn is None
    if own_conn:
        conn = _get_conn()

    try:
        sql = f"""
        WITH daily AS (
            SELECT
                symbol,
                CAST(timestamp AS DATE) as trade_date,
                SUM(volume) as day_volume
            FROM all_candles
            WHERE timestamp >= '{target_date}'
            GROUP BY symbol, CAST(timestamp AS DATE)
        ),
        with_avg AS (
            SELECT
                symbol,
                trade_date,
                day_volume,
                AVG(day_volume) OVER (
                    PARTITION BY symbol
                    ORDER BY trade_date
                    ROWS BETWEEN {lookback_days} PRECEDING AND 1 PRECEDING
                ) as avg_volume
            FROM daily
        )
        SELECT
            symbol,
            trade_date,
            day_volume as volume_today,
            ROUND(avg_volume, 0) as avg_volume,
            ROUND(day_volume / NULLIF(avg_volume, 0), 2) as rel_volume
        FROM with_avg
        WHERE trade_date = '{target_date}'
          AND avg_volume > 0
        ORDER BY rel_volume DESC
        """
        return conn.execute(sql).fetchdf()
    finally:
        if own_conn:
            conn.close()


def high_rel_volume_stocks(
    target_date: str,
    min_rel_volume: float = 5.0,
    lookback_days: int = 14,
    cutoff_time: str = "09:45",
    conn: duckdb.DuckDBPyConnection | None = None,
) -> pd.DataFrame:
    """Find stocks with unusually high relative volume.

    Args:
        target_date: Date to query (YYYY-MM-DD).
        min_rel_volume: Minimum relative volume threshold (default 5.0 = 5x).
        lookback_days: Trading days for average (default 14).
        cutoff_time: Intraday cutoff time (default "09:45").
        conn: Optional DuckDB connection.

    Returns:
        DataFrame of stocks exceeding the threshold, sorted by rel_volume DESC.
    """
    df = rel_volume_14d_by_time(
        target_date=target_date,
        cutoff_time=cutoff_time,
        lookback_days=lookback_days,
        conn=conn,
    )
    return df[df["rel_volume"] >= min_rel_volume].reset_index(drop=True)
