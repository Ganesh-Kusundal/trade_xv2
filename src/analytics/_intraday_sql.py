"""SQL builder for intraday technical features."""

from datetime import datetime


def build_intraday_features_sql(published_at: datetime, intraday_days: int = 30) -> str:
    """Build SQL for intraday features with deduplicated window functions."""
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
        WHERE timestamp >= (SELECT MAX(timestamp) FROM v_candles_1m) - INTERVAL '{intraday_days} days'
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
    ),
    intraday_filled AS (
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
            gain,
            loss,
            AVG(true_range) OVER w14 as atr_14,
            AVG(CASE WHEN change < 0 THEN ABS(change) ELSE 0 END) OVER w14 as avg_loss_14_intra,
            AVG(CASE WHEN change > 0 THEN change ELSE 0 END) OVER w14 as avg_gain_14_intra,
            AVG(CASE WHEN change < 0 THEN ABS(change) ELSE 0 END) OVER w21 as avg_loss_21_intra,
            AVG(CASE WHEN change > 0 THEN change ELSE 0 END) OVER w21 as avg_gain_21_intra,
            AVG(close) OVER w20 as sma_20,
            AVG(close) OVER w50 as sma_50,
            AVG(close) OVER w12 as ema_12,
            AVG(close) OVER w26 as ema_26,
            STDDEV(close) OVER w20 as stddev_20,
            AVG(volume) OVER w20 as volume_sma_20,
            AVG(volume) OVER w50 as volume_sma_50
        FROM gains_losses
        WINDOW
            w14 AS (PARTITION BY symbol ORDER BY event_time ROWS BETWEEN 13 PRECEDING AND CURRENT ROW),
            w21 AS (PARTITION BY symbol ORDER BY event_time ROWS BETWEEN 20 PRECEDING AND CURRENT ROW),
            w20 AS (PARTITION BY symbol ORDER BY event_time ROWS BETWEEN 19 PRECEDING AND CURRENT ROW),
            w50 AS (PARTITION BY symbol ORDER BY event_time ROWS BETWEEN 49 PRECEDING AND CURRENT ROW),
            w12 AS (PARTITION BY symbol ORDER BY event_time ROWS BETWEEN 11 PRECEDING AND CURRENT ROW),
            w26 AS (PARTITION BY symbol ORDER BY event_time ROWS BETWEEN 25 PRECEDING AND CURRENT ROW)
    ),
    macd_base AS (
        SELECT
            *,
            ema_12 - ema_26 as macd_line,
            AVG(ema_12 - ema_26) OVER w9 as macd_signal_line
        FROM intraday_filled
        WINDOW w9 AS (PARTITION BY symbol ORDER BY event_time ROWS BETWEEN 8 PRECEDING AND CURRENT ROW)
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
            WHEN avg_loss_14_intra = 0 THEN 100.0
            ELSE 100.0 - (100.0 / (1.0 + avg_gain_14_intra / NULLIF(avg_loss_14_intra, 0)))
        END as rsi_14,
        CASE
            WHEN avg_loss_21_intra = 0 THEN 100.0
            ELSE 100.0 - (100.0 / (1.0 + avg_gain_21_intra / NULLIF(avg_loss_21_intra, 0)))
        END as rsi_21,
        sma_20,
        sma_50,
        ema_12,
        ema_26,
        macd_line as macd,
        macd_signal_line as macd_signal,
        macd_line - macd_signal_line as macd_histogram,
        sma_20 + 2.0 * stddev_20 as bb_upper,
        sma_20 - 2.0 * stddev_20 as bb_lower,
        sma_20 as bb_mid,
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
        volume_sma_20,
        volume_sma_50,
        CASE
            WHEN volume_sma_20 > 0
            THEN volume / volume_sma_20
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
        atr_14 as avg_true_range_14,
        YEAR(event_time) as year,
        MONTH(event_time) as month
    FROM macd_base
    QUALIFY ROW_NUMBER() OVER (PARTITION BY symbol, event_time) = 1
    """
