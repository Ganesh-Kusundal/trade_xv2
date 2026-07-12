"""SQL definitions for pre-built scanners."""

from __future__ import annotations

from analytics.scanner.scanner_queries import ScannerQuery


_MOMENTUM_SQL = """
WITH latest_features AS (
    SELECT DISTINCT ON (symbol)
        symbol,
        event_time,
        close,
        volume,
        rsi_14,
        roc_5,
        sma_20,
        sma_50,
        relative_volume_20,
        CASE
            WHEN close > sma_20 AND sma_20 > sma_50 THEN 'up'
            WHEN close < sma_20 AND sma_20 < sma_50 THEN 'down'
            ELSE 'neutral'
        END as trend,
        close - LAG(close, 5) OVER (PARTITION BY symbol ORDER BY event_time) as momentum
    FROM intraday_features
    WHERE published_at <= :as_of_time
      AND event_time <= :as_of_time
    ORDER BY symbol, event_time DESC
)
SELECT
    symbol,
    ROUND(
        0.20 * GREATEST(0, LEAST(100, 50.0 + (rsi_14 - 50.0) * 1.0))
        + 0.20 * GREATEST(0, LEAST(100, 50.0 + GREATEST(-10, LEAST(10, roc_5)) * 3.0))
        + 0.25 * CASE trend
            WHEN 'up' THEN 75.0
            WHEN 'down' THEN 25.0
            ELSE 50.0
        END
        + 0.15 * GREATEST(0, LEAST(100, 50.0 + GREATEST(-1, LEAST(3, relative_volume_20 - 1.0)) * 15.0))
        + 0.20 * GREATEST(0, LEAST(100, 50.0 + GREATEST(-5, LEAST(5, COALESCE(momentum, 0))) * 5.0))
    , 2) as score,
    CASE
        WHEN rsi_14 > 70 THEN 'overbought'
        WHEN rsi_14 < 30 THEN 'oversold'
        ELSE 'neutral_rsi'
    END || ', ' ||
    CASE
        WHEN relative_volume_20 > 2.0 THEN 'high_volume'
        WHEN relative_volume_20 > 1.5 THEN 'above_avg_volume'
        ELSE 'normal_volume'
    END as reason,
    rsi_14,
    roc_5,
    COALESCE(momentum, 0) as momentum_5,
    relative_volume_20,
    trend
FROM latest_features
WHERE rsi_14 IS NOT NULL
ORDER BY score DESC
"""

_VOLUME_SQL = """
WITH latest_features AS (
    SELECT DISTINCT ON (symbol)
        symbol,
        event_time,
        close,
        volume,
        rsi_14,
        atr_14,
        relative_volume_20,
        volume_sma_20,
        volume / NULLIF(volume_sma_20, 0) as vol_ratio
    FROM intraday_features
    WHERE published_at <= :as_of_time
      AND event_time <= :as_of_time
    ORDER BY symbol, event_time DESC
)
SELECT
    symbol,
    ROUND(
        0.40 * GREATEST(0, LEAST(100, 50.0 + GREATEST(-1, LEAST(5, relative_volume_20 - 1.0)) * 12.0))
        + 0.25 * GREATEST(0, LEAST(100, 50.0 + GREATEST(-2, LEAST(3, COALESCE(vol_ratio, 1.0) - 1.0)) * 10.0))
        + 0.20 * GREATEST(0, LEAST(100, 50.0 + GREATEST(0, LEAST(10, COALESCE(atr_14, 0))) * 3.0))
        + 0.15 * GREATEST(0, LEAST(100, 50.0 + (COALESCE(rsi_14, 50.0) - 50.0) * 0.5))
    , 2) as score,
    CASE
        WHEN relative_volume_20 > 3.0 THEN 'extreme_volume'
        WHEN relative_volume_20 > 2.0 THEN 'high_volume'
        WHEN relative_volume_20 > 1.5 THEN 'above_avg_volume'
        ELSE 'normal_volume'
    END || ', ' ||
    CASE
        WHEN vol_ratio > 2.0 THEN 'volume_spike'
        ELSE 'normal_volume_trend'
    END as reason,
    relative_volume_20,
    COALESCE(vol_ratio, 1.0) as vol_ratio,
    atr_14,
    rsi_14
FROM latest_features
WHERE relative_volume_20 IS NOT NULL
ORDER BY score DESC
"""

_RS_SQL = """
WITH latest_features AS (
    SELECT DISTINCT ON (symbol)
        symbol,
        event_time,
        close,
        rsi_14,
        roc_5,
        sma_20,
        sma_50,
        atr_14,
        CASE
            WHEN close > sma_20 AND sma_20 > sma_50 THEN 'up'
            WHEN close < sma_20 AND sma_20 < sma_50 THEN 'down'
            ELSE 'neutral'
        END as trend,
        close - LAG(close, 5) OVER (PARTITION BY symbol ORDER BY event_time) as momentum
    FROM intraday_features
    WHERE published_at <= :as_of_time
      AND event_time <= :as_of_time
    ORDER BY symbol, event_time DESC
)
SELECT
    symbol,
    ROUND(
        0.15 * GREATEST(0, LEAST(100, 50.0 + (rsi_14 - 50.0) * 1.0))
        + 0.30 * CASE trend
            WHEN 'up' THEN 75.0
            WHEN 'down' THEN 25.0
            ELSE 50.0
        END
        + 0.25 * GREATEST(0, LEAST(100, 50.0 + GREATEST(-10, LEAST(10, roc_5)) * 3.0))
        + 0.15 * GREATEST(0, LEAST(100, 50.0 + GREATEST(-5, LEAST(5, COALESCE(momentum, 0))) * 5.0))
        + 0.15 * GREATEST(0, LEAST(100, 50.0 + GREATEST(0, LEAST(10, COALESCE(atr_14, 0))) * 3.0))
    , 2) as score,
    CASE trend
        WHEN 'up' THEN 'uptrend'
        WHEN 'down' THEN 'downtrend'
        ELSE 'neutral_trend'
    END || ', ' ||
    CASE
        WHEN rsi_14 > 60 THEN 'strong_rsi'
        ELSE 'neutral_rsi'
    END as reason,
    rsi_14,
    roc_5,
    COALESCE(momentum, 0) as momentum_5,
    atr_14,
    trend
FROM latest_features
WHERE rsi_14 IS NOT NULL
ORDER BY score DESC
"""

_BREAKOUT_SQL = """
WITH latest_features AS (
    SELECT DISTINCT ON (symbol)
        symbol,
        event_time,
        close,
        volume,
        rsi_14,
        atr_14,
        relative_volume_20,
        sma_20 as bb_mid,
        sma_20 + 2.0 * STDDEV(close) OVER (
            PARTITION BY symbol ORDER BY event_time
            ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
        ) as bb_upper,
        sma_20 - 2.0 * STDDEV(close) OVER (
            PARTITION BY symbol ORDER BY event_time
            ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
        ) as bb_lower,
        SUM(volume * close) OVER (
            PARTITION BY symbol, CAST(event_time AS DATE)
            ORDER BY event_time
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) / NULLIF(SUM(volume) OVER (
            PARTITION BY symbol, CAST(event_time AS DATE)
            ORDER BY event_time
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ), 0) as vwap
    FROM intraday_features
    WHERE published_at <= :as_of_time
      AND event_time <= :as_of_time
    ORDER BY symbol, event_time DESC
)
SELECT
    symbol,
    ROUND(
        0.30 * GREATEST(0, LEAST(100, 50.0 + (
            (close - bb_lower) / NULLIF(bb_upper - bb_lower, 0) - 0.5
        ) * 60.0))
        + 0.30 * GREATEST(0, LEAST(100, 50.0 + GREATEST(-1, LEAST(4, relative_volume_20 - 1.0)) * 15.0))
        + 0.20 * GREATEST(0, LEAST(100, 50.0 + (COALESCE(rsi_14, 50.0) - 50.0) * 0.8))
        + 0.20 * GREATEST(0, LEAST(100, 50.0 + GREATEST(-5, LEAST(5,
            (close - COALESCE(vwap, close)) / NULLIF(COALESCE(vwap, close), 0) * 100
        )) * 5.0))
    , 2) as score,
    CASE
        WHEN close >= bb_upper THEN 'near_upper_band'
        WHEN close <= bb_lower THEN 'near_lower_band'
        ELSE 'within_bands'
    END || ', ' ||
    CASE
        WHEN relative_volume_20 > 2.0 THEN 'high_volume'
        ELSE 'normal_volume'
    END as reason,
    close,
    bb_upper,
    bb_mid,
    bb_lower,
    (close - bb_lower) / NULLIF(bb_upper - bb_lower, 0) as bb_pct_b,
    relative_volume_20,
    rsi_14,
    vwap
FROM latest_features
WHERE bb_upper IS NOT NULL AND bb_lower IS NOT NULL
ORDER BY score DESC
"""


momentum_scanner = ScannerQuery(
    name="momentum",
    description="Finds stocks with strong momentum (RSI, ROC, trend alignment). "
    "Matches MomentumScanner scoring logic.",
    sql=_MOMENTUM_SQL,
    top_n=20,
    min_score=0.0,
)

volume_scanner = ScannerQuery(
    name="volume_breakout",
    description="Finds stocks with unusual volume activity. "
    "Matches VolumeScanner scoring logic.",
    sql=_VOLUME_SQL,
    top_n=20,
    min_score=0.0,
)

rs_rotation_scanner = ScannerQuery(
    name="rs_rotation",
    description="Finds stocks with strong relative strength vs benchmark. "
    "Matches RSScanner scoring logic.",
    sql=_RS_SQL,
    top_n=20,
    min_score=0.0,
)

breakout_scanner = ScannerQuery(
    name="breakout",
    description="Finds stocks near breakout (Bollinger squeeze, volume, swing levels). "
    "Matches BreakoutScanner scoring logic.",
    sql=_BREAKOUT_SQL,
    top_n=20,
    min_score=0.0,
)

_BUILTIN_SCANNERS: list[ScannerQuery] = [
    momentum_scanner,
    volume_scanner,
    rs_rotation_scanner,
    breakout_scanner,
]

_SCANNER_MAP: dict[str, ScannerQuery] = {s.name: s for s in _BUILTIN_SCANNERS}

__all__ = [
    "_BUILTIN_SCANNERS",
    "_SCANNER_MAP",
    "breakout_scanner",
    "momentum_scanner",
    "rs_rotation_scanner",
    "volume_scanner",
]
