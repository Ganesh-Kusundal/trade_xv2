"""SQL builder for options-specific features (PCR, max pain, IV skew)."""

from datetime import datetime


def build_options_features_sql(published_at: datetime) -> str:
    """Build SQL for options-specific features (PCR, max pain, IV skew)."""
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
        FROM read_parquet('data/lake/options/chains/expiry=*/underlying=*/data.parquet')
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
