"""SQL builder for daily technical features."""

from datetime import datetime


def build_daily_features_sql(published_at: datetime) -> str:
    """Build SQL for all daily features in one pass over daily aggregated bars.

    Window functions are computed ONCE in CTEs and referenced by name
    in the final SELECT, eliminating duplicate computations.
    """
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
            AVG(true_range) OVER w14 as atr_14,
            AVG(gain) OVER w14 as avg_gain_14,
            AVG(loss) OVER w14 as avg_loss_14,
            AVG(gain) OVER w21 as avg_gain_21,
            AVG(loss) OVER w21 as avg_loss_21,
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
        FROM daily_filled
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
            WHEN avg_loss_14 = 0 THEN 100.0
            ELSE 100.0 - (100.0 / (1.0 + avg_gain_14 / NULLIF(avg_loss_14, 0)))
        END as rsi_14,
        CASE
            WHEN avg_loss_21 = 0 THEN 100.0
            ELSE 100.0 - (100.0 / (1.0 + avg_gain_21 / NULLIF(avg_loss_21, 0)))
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
        volume_sma_20,
        volume_sma_50,
        CASE
            WHEN volume_sma_20 > 0
            THEN volume / volume_sma_20
            ELSE 1.0
        END as relative_volume_20,
        SUM(volume * (high + low + close) / 3.0) OVER (
            PARTITION BY symbol, event_time
        ) / NULLIF(SUM(volume) OVER (
            PARTITION BY symbol, event_time
        ), 0) as vwap_daily,
        true_range,
        atr_14 as avg_true_range_14,
        YEAR(event_time) as year,
        MONTH(event_time) as month
    FROM macd_base
    QUALIFY ROW_NUMBER() OVER (PARTITION BY symbol, event_time) = 1
    """
