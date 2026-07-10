"""Option analytics materialization SQL.

Computes m_pcr, m_max_pain, m_iv_surface from the option Parquet data.
These are expensive GROUP BY / cross-join operations that should be
materialized once and refreshed on data sync.
"""

# PCR — Put-Call Ratio per (timestamp, underlying, expiry)
# Note: source data uses 'CALL'/'PUT' (not 'CE'/'PE')
SQL_M_PCR = """
SELECT
    timestamp,
    underlying,
    expiry_kind,
    expiry_code,
    expiry_date,
    spot,
    interval_min,
    SUM(CASE WHEN option_type = 'CALL' THEN volume ELSE 0 END) as total_ce_volume,
    SUM(CASE WHEN option_type = 'PUT' THEN volume ELSE 0 END) as total_pe_volume,
    SUM(CASE WHEN option_type = 'CALL' THEN oi ELSE 0 END) as total_ce_oi,
    SUM(CASE WHEN option_type = 'PUT' THEN oi ELSE 0 END) as total_pe_oi
FROM read_parquet('market_data/options/candles/underlying=*/*/*/data.parquet')
GROUP BY timestamp, underlying, expiry_kind, expiry_code, expiry_date, spot, interval_min
ORDER BY timestamp, underlying, expiry_kind, expiry_code
"""

# Max Pain — strike that minimizes total option holder loss
SQL_M_MAX_PAIN = """
WITH options AS (
    SELECT * FROM read_parquet('market_data/options/candles/underlying=*/*/*/data.parquet')
),
candidates AS (
    SELECT DISTINCT
        timestamp, underlying, expiry_kind, expiry_code, expiry_date, spot, interval_min,
        strike as K
    FROM options
),
pain AS (
    SELECT
        c.timestamp, c.underlying, c.expiry_kind, c.expiry_code, c.expiry_date,
        c.spot, c.interval_min, c.K,
        SUM(CASE WHEN o.option_type = 'CALL' THEN o.oi * GREATEST(0, c.K - o.strike) ELSE 0 END) +
        SUM(CASE WHEN o.option_type = 'PUT' THEN o.oi * GREATEST(0, o.strike - c.K) ELSE 0 END) as total_pain
    FROM candidates c
    JOIN options o
        ON c.timestamp = o.timestamp
        AND c.underlying = o.underlying
        AND c.expiry_kind = o.expiry_kind
        AND c.expiry_code = o.expiry_code
    GROUP BY c.timestamp, c.underlying, c.expiry_kind, c.expiry_code, c.expiry_date,
             c.spot, c.interval_min, c.K
),
ranked AS (
    SELECT *,
        ROW_NUMBER() OVER (
            PARTITION BY timestamp, underlying, expiry_kind, expiry_code
            ORDER BY total_pain ASC
        ) as rn
    FROM pain
)
SELECT
    timestamp, underlying, expiry_kind, expiry_code, expiry_date,
    spot, interval_min,
    K as max_pain_strike,
    total_pain as total_pain_at_max_pain
FROM ranked
WHERE rn = 1
ORDER BY timestamp, underlying, expiry_kind, expiry_code
"""

# IV Surface — ATM IV, OTM put IV, OTM call IV, IV skew
# Source data uses 'CALL'/'PUT' (not 'CE'/'PE')
SQL_M_IV_SURFACE = """
WITH options AS (
    SELECT * FROM read_parquet('market_data/options/candles/underlying=*/*/*/data.parquet')
),
dist_to_spot AS (
    SELECT *,
        ABS(strike - spot) as dist,
        CASE WHEN strike = spot THEN 'at_spot'
             WHEN strike < spot AND option_type = 'PUT' THEN 'otm_put'
             WHEN strike > spot AND option_type = 'CALL' THEN 'otm_call'
             ELSE 'other' END as moneyness
    FROM options
),
atm AS (
    SELECT DISTINCT ON (timestamp, underlying, expiry_kind, expiry_code)
        timestamp, underlying, expiry_kind, expiry_code, expiry_date,
        spot, interval_min, strike as atm_strike, iv as atm_iv
    FROM dist_to_spot
    WHERE moneyness IN ('at_spot', 'otm_put', 'otm_call')
    ORDER BY timestamp, underlying, expiry_kind, expiry_code, dist ASC
),
otm_put AS (
    SELECT timestamp, underlying, expiry_kind, expiry_code,
        AVG(iv) as otm_put_iv
    FROM dist_to_spot
    WHERE moneyness = 'otm_put'
    GROUP BY timestamp, underlying, expiry_kind, expiry_code
),
otm_call AS (
    SELECT timestamp, underlying, expiry_kind, expiry_code,
        AVG(iv) as otm_call_iv
    FROM dist_to_spot
    WHERE moneyness = 'otm_call'
    GROUP BY timestamp, underlying, expiry_kind, expiry_code
),
days_to_expiry_calc AS (
    SELECT
        a.timestamp, a.underlying, a.expiry_kind, a.expiry_code,
        a.expiry_date, a.spot, a.interval_min,
        a.atm_strike, a.atm_iv,
        COALESCE(p.otm_put_iv, 0) as otm_put_iv,
        COALESCE(c.otm_call_iv, 0) as otm_call_iv,
        CASE
            WHEN a.expiry_date IS NOT NULL
            THEN CAST(a.expiry_date AS DATE) - CAST(a.timestamp AS DATE)
            ELSE NULL
        END as days_to_expiry
    FROM atm a
    LEFT JOIN otm_put p
        ON a.timestamp = p.timestamp AND a.underlying = p.underlying
        AND a.expiry_kind = p.expiry_kind AND a.expiry_code = p.expiry_code
    LEFT JOIN otm_call c
        ON a.timestamp = c.timestamp AND a.underlying = c.underlying
        AND a.expiry_kind = c.expiry_kind AND a.expiry_code = c.expiry_code
)
SELECT * FROM days_to_expiry_calc
ORDER BY timestamp, underlying, expiry_kind, expiry_code
"""
