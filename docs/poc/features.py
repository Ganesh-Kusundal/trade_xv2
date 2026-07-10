"""Momentum PoC — Feature Engineering v3 (50+ Features, Multi-Timeframe, Cross-Sectional).

Features computed at 09:45 each day:
1. Morning window features (09:15-09:45) — 20 features
2. Multi-timeframe lagged daily features — 20 features  
3. Cross-sectional ranks — 10 features
4. Technical indicators from daily data — 10 features
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import CANDLES_DIR, POC_DATA, FEATURES_PATH
import duckdb
import pandas as pd
import numpy as np

def main() -> None:
    POC_DATA.mkdir(parents=True, exist_ok=True)
    glob_pattern = str(CANDLES_DIR / "symbol=*" / "data.parquet")
    nifty_path = str(Path("market_data/indices/candles/timeframe=1m/symbol=NIFTY/data.parquet"))
    print("Computing features via DuckDB SQL...")
    conn = duckdb.connect(":memory:")

    # ══════════════════════════════════════════════════════════════
    # PHASE 1: Base data + OBV delta + bar-level gain/loss
    # ══════════════════════════════════════════════════════════════
    conn.execute(f"""
        CREATE TABLE base_raw AS
        SELECT symbol, CAST(timestamp AS TIMESTAMP) AS ts,
            CAST(timestamp AS DATE) AS trade_date, CAST(timestamp AS TIME) AS tod,
            open, high, low, close, volume,
            close - LAG(close) OVER (PARTITION BY symbol ORDER BY timestamp) AS delta_close
        FROM read_parquet('{glob_pattern}', hive_partitioning=true)
    """)
    conn.execute("""
        CREATE TABLE base AS
        SELECT symbol, ts, trade_date, tod, open, high, low, close, volume,
            SIGN(delta_close) * volume AS obv_delta,
            GREATEST(delta_close, 0) AS bar_gain, LEAST(delta_close, 0) AS bar_loss
        FROM base_raw
    """)
    print(f"  Loaded {conn.execute('SELECT COUNT(*) FROM base').fetchone()[0]:,} rows")

    # ══════════════════════════════════════════════════════════════
    # PHASE 2: Daily open/close/high/low/volume
    # ══════════════════════════════════════════════════════════════
    conn.execute("""
        CREATE TABLE daily_raw AS
        SELECT symbol, trade_date, 
            MIN(ts) AS min_ts, MAX(ts) AS max_ts,
            MAX(high) AS d_high, MIN(low) AS d_low,
            SUM(volume) AS d_volume
        FROM base GROUP BY symbol, trade_date
    """)
    conn.execute("""
        CREATE TABLE daily AS
        SELECT d.symbol, d.trade_date, 
            b1.open AS d_open, b2.close AS d_close,
            d.d_high, d.d_low, d.d_volume
        FROM daily_raw d
        JOIN base b1 ON d.symbol = b1.symbol AND d.min_ts = b1.ts
        JOIN base b2 ON d.symbol = b2.symbol AND d.max_ts = b2.ts
    """)

    # ══════════════════════════════════════════════════════════════
    # PHASE 3: Morning window features (09:15-09:45)
    # ══════════════════════════════════════════════════════════════
    conn.execute("""
        CREATE TABLE morning AS
        SELECT symbol, trade_date,
            LAST_VALUE(close) OVER w AS close_0945,
            FIRST_VALUE(open) OVER w AS open_0915,
            MAX(high) OVER w AS high_0945, MIN(low) OVER w AS low_0945,
            AVG(volume) OVER w AS vol_0945,
            SUM(CASE WHEN tod <= TIME '09:30' THEN volume ELSE 0 END) OVER w AS vol_first15,
            SUM(CASE WHEN tod > TIME '09:30' THEN volume ELSE 0 END) OVER w AS vol_last15,
            SUM((high+low+close)/3.0 * volume) OVER w / NULLIF(SUM(volume) OVER w, 0) AS vwap,
            SUM(obv_delta) OVER w AS obv_delta,
            COUNT(*) OVER w AS morning_bars,
            AVG(bar_gain) OVER w AS avg_gain, AVG(ABS(bar_loss)) OVER w AS avg_loss
        FROM base WHERE tod >= TIME '09:15' AND tod <= TIME '09:45'
        WINDOW w AS (PARTITION BY symbol, trade_date ORDER BY ts
                     ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)
    """)
    conn.execute("""
        CREATE TABLE morning_dedup AS
        SELECT DISTINCT symbol, trade_date, close_0945, open_0915, high_0945, low_0945,
            vol_0945, vol_first15, vol_last15, vwap, obv_delta, morning_bars, avg_gain, avg_loss
        FROM morning
    """)

    # ══════════════════════════════════════════════════════════════
    # PHASE 4: RVOL (10-day trailing average morning volume)
    # ══════════════════════════════════════════════════════════════
    conn.execute("""
        CREATE TABLE morning_vol_avg AS
        SELECT m.symbol, m.trade_date, m.vol_0945,
            AVG(m.vol_0945) OVER (PARTITION BY m.symbol ORDER BY m.trade_date
                ROWS BETWEEN 10 PRECEDING AND 1 PRECEDING) AS avg_vol_10d,
            AVG(m.vol_0945) OVER (PARTITION BY m.symbol ORDER BY m.trade_date
                ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING) AS avg_vol_20d
        FROM morning_dedup m
    """)

    # ══════════════════════════════════════════════════════════════
    # PHASE 5: NIFTY index features
    # ══════════════════════════════════════════════════════════════
    conn.execute(f"""
        CREATE TABLE nifty_base AS
        SELECT CAST(timestamp AS TIMESTAMP) AS ts,
            CAST(timestamp AS DATE) AS trade_date, CAST(timestamp AS TIME) AS tod,
            close, volume
        FROM read_parquet('{nifty_path}')
    """)
    conn.execute("""
        CREATE TABLE nifty_morning AS
        SELECT trade_date,
            LAST_VALUE(close) OVER w AS nifty_close_0945,
            FIRST_VALUE(close) OVER w AS nifty_open_0915
        FROM nifty_base WHERE tod >= TIME '09:15' AND tod <= TIME '09:45'
        WINDOW w AS (PARTITION BY trade_date ORDER BY ts
                     ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)
    """)
    conn.execute("""
        CREATE TABLE nifty_morning_dedup AS
        SELECT DISTINCT trade_date, nifty_close_0945, nifty_open_0915 FROM nifty_morning
    """)
    conn.execute("""
        CREATE TABLE nifty_daily AS
        SELECT trade_date,
            FIRST_VALUE(close) OVER w AS nifty_d_open,
            LAST_VALUE(close) OVER w AS nifty_d_close
        FROM (SELECT trade_date, ts, close FROM nifty_base) sub
        WINDOW w AS (PARTITION BY trade_date ORDER BY ts
                     ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)
    """)
    print(f"  NIFTY features computed")

    # ══════════════════════════════════════════════════════════════
    # PHASE 6: Multi-timeframe features from daily data
    # ══════════════════════════════════════════════════════════════
    # Step 6a: Pre-compute 10d avg volume for ratio
    conn.execute("""
        CREATE TABLE daily_vol_avg AS
        SELECT symbol, trade_date, d_volume,
            AVG(d_volume) OVER (PARTITION BY symbol ORDER BY trade_date
                ROWS BETWEEN 10 PRECEDING AND 1 PRECEDING) AS avg_dvol_10d
        FROM daily
    """)
    conn.execute("""
        CREATE TABLE daily_features AS
        SELECT d.symbol, d.trade_date, d.d_open, d.d_close, d.d_high, d.d_low, d.d_volume,
            (d.d_close - d.d_open) / NULLIF(d.d_open, 0) * 100 AS daily_ret,
            (d.d_high - d.d_low) / NULLIF(d.d_open, 0) * 100 AS daily_range,
            LAG(d.d_volume / NULLIF(va.avg_dvol_10d, 0), 1) OVER (PARTITION BY d.symbol ORDER BY d.trade_date) AS daily_vol_ratio,
            LAG(d.d_close, 1) OVER (PARTITION BY d.symbol ORDER BY d.trade_date) AS close_1d_ago,
            LAG(d.d_close, 2) OVER (PARTITION BY d.symbol ORDER BY d.trade_date) AS close_2d_ago,
            LAG(d.d_close, 5) OVER (PARTITION BY d.symbol ORDER BY d.trade_date) AS close_5d_ago,
            LAG(d.d_close, 10) OVER (PARTITION BY d.symbol ORDER BY d.trade_date) AS close_10d_ago,
            LAG(d.d_close, 20) OVER (PARTITION BY d.symbol ORDER BY d.trade_date) AS close_20d_ago,
            LAG(d.d_high, 1) OVER (PARTITION BY d.symbol ORDER BY d.trade_date) AS high_1d_ago,
            LAG(d.d_low, 1) OVER (PARTITION BY d.symbol ORDER BY d.trade_date) AS low_1d_ago,
            LAG(d.d_volume, 1) OVER (PARTITION BY d.symbol ORDER BY d.trade_date) AS volume_1d_ago,
            LAG((d.d_close - d.d_open) / NULLIF(d.d_open, 0) * 100, 1) OVER (PARTITION BY d.symbol ORDER BY d.trade_date) AS ret_1d_ago,
            LAG((d.d_high - d.d_low) / NULLIF(d.d_open, 0) * 100, 1) OVER (PARTITION BY d.symbol ORDER BY d.trade_date) AS range_1d_ago,
            LAG((d.d_close - d.d_open) / NULLIF(d.d_open, 0) * 100, 2) OVER (PARTITION BY d.symbol ORDER BY d.trade_date) AS ret_2d_ago,
            AVG((d.d_close - d.d_open) / NULLIF(d.d_open, 0) * 100) OVER (PARTITION BY d.symbol ORDER BY d.trade_date
                ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING) AS avg_ret_5d,
            AVG((d.d_close - d.d_open) / NULLIF(d.d_open, 0) * 100) OVER (PARTITION BY d.symbol ORDER BY d.trade_date
                ROWS BETWEEN 10 PRECEDING AND 1 PRECEDING) AS avg_ret_10d,
            AVG((d.d_high - d.d_low) / NULLIF(d.d_open, 0) * 100) OVER (PARTITION BY d.symbol ORDER BY d.trade_date
                ROWS BETWEEN 10 PRECEDING AND 1 PRECEDING) AS avg_range_10d,
            STDDEV_SAMP((d.d_close - d.d_open) / NULLIF(d.d_open, 0) * 100) OVER (PARTITION BY d.symbol ORDER BY d.trade_date
                ROWS BETWEEN 10 PRECEDING AND 1 PRECEDING) AS vol_10d,
            STDDEV_SAMP((d.d_close - d.d_open) / NULLIF(d.d_open, 0) * 100) OVER (PARTITION BY d.symbol ORDER BY d.trade_date
                ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING) AS vol_20d,
            AVG(d.d_volume) OVER (PARTITION BY d.symbol ORDER BY d.trade_date
                ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING) AS avg_vol_5d,
            AVG(d.d_volume) OVER (PARTITION BY d.symbol ORDER BY d.trade_date
                ROWS BETWEEN 10 PRECEDING AND 1 PRECEDING) AS avg_vol_10d,
            CASE WHEN (d.d_close - d.d_open) > 0 THEN 1 WHEN (d.d_close - d.d_open) < 0 THEN -1 ELSE 0 END AS direction
        FROM daily d
        LEFT JOIN daily_vol_avg va ON d.symbol = va.symbol AND d.trade_date = va.trade_date
    """)

    print(f"  Daily features computed")

    # ══════════════════════════════════════════════════════════════
    # PHASE 7: Join all features (including cross-sectional in pandas)
    # ══════════════════════════════════════════════════════════════
    df = conn.execute("""
        WITH prev AS (
            SELECT symbol, trade_date, d_close,
                LAG(d_close) OVER (PARTITION BY symbol ORDER BY trade_date) AS prev_close
            FROM daily
        ),
        prev_dir AS (
            SELECT symbol, trade_date,
                LAG(CASE WHEN d_close > d_open THEN 1 WHEN d_close < d_open THEN -1 ELSE 0 END)
                    OVER (PARTITION BY symbol ORDER BY trade_date) AS prev_direction
            FROM daily
        ),
        nifty_mom AS (
            SELECT trade_date, nifty_d_close,
                LAG(nifty_d_close, 5) OVER (ORDER BY trade_date) AS nifty_close_5d,
                LAG(nifty_d_close, 10) OVER (ORDER BY trade_date) AS nifty_close_10d,
                LAG(nifty_d_close, 20) OVER (ORDER BY trade_date) AS nifty_close_20d
            FROM (SELECT DISTINCT trade_date, nifty_d_close FROM nifty_daily)
        ),
        nifty_perf AS (
            SELECT trade_date, nifty_d_open, nifty_d_close,
                LAG((nifty_d_close - nifty_d_open) / NULLIF(nifty_d_open, 0) * 100, 1) OVER (ORDER BY trade_date) AS nifty_daily_ret_prev,
                LAG((nifty_d_close - nifty_d_open) / NULLIF(nifty_d_open, 0) * 100, 1) OVER (ORDER BY trade_date) AS nifty_ret_1d_ago,
                LAG((nifty_d_close - nifty_d_open) / NULLIF(nifty_d_open, 0) * 100, 5) OVER (ORDER BY trade_date) AS nifty_ret_5d_ago
            FROM (SELECT DISTINCT trade_date, nifty_d_open, nifty_d_close FROM nifty_daily)
        )
        SELECT
            -- Basic identifiers
            m.symbol, m.trade_date AS date, m.close_0945,
            
            -- === MORNING WINDOW FEATURES (20) ===
            (m.open_0915 - p.prev_close) / NULLIF(p.prev_close, 0) * 100 AS gap_up_pct,
            (m.close_0945 - m.open_0915) / NULLIF(m.open_0915, 0) * 100 AS ret_30m,
            (m.high_0945 - m.low_0945) / NULLIF(m.open_0915, 0) * 100 AS range_30m,
            (m.close_0945 - m.vwap) / NULLIF(m.vwap, 0) * 100 AS vwap_dev,
            CASE WHEN m.avg_loss > 0 THEN 100.0 - 100.0 / (1.0 + m.avg_gain / m.avg_loss) ELSE 50.0 END AS rsi_14,
            (m.close_0945 - m.open_0915) * 0.3 AS macd_hist,
            CASE WHEN m.high_0945 > m.low_0945 THEN (m.close_0945 - m.low_0945) / (m.high_0945 - m.low_0945) ELSE 0.5 END AS bb_pctb,
            COALESCE(m.vol_0945 / NULLIF(mva.avg_vol_10d, 0), 1.0) AS rvol,
            CASE WHEN m.vol_first15 > 0 THEN m.vol_last15 * 1.0 / m.vol_first15 ELSE 1.0 END AS vol_surge,
            COALESCE(m.obv_delta, 0) AS obv_delta,
            EXTRACT(DOW FROM m.trade_date) AS dow,
            (m.close_0945 - mo.close_5d_ago) / NULLIF(mo.close_5d_ago, 0) * 100 AS mom_5d,
            (p.prev_close - mo.close_1d_ago) / NULLIF(mo.close_1d_ago, 0) * 100 AS prev_day_ret,
            COALESCE(pd.prev_direction, 0) AS consec_days,
            COALESCE(m.vol_0945, 0) AS avg_vol_30m,
            
            -- === NIFTY FEATURES (6) ===
            (nm.nifty_close_0945 - nm.nifty_open_0915) / NULLIF(nm.nifty_open_0915, 0) * 100 AS nifty_ret_30m,
            (nm.nifty_close_0945 - nmo.nifty_close_5d) / NULLIF(nmo.nifty_close_5d, 0) * 100 AS nifty_mom_5d,
            ((m.close_0945 - m.open_0915) / NULLIF(m.open_0915, 0) - (nm.nifty_close_0945 - nm.nifty_open_0915) / NULLIF(nm.nifty_open_0915, 0)) * 100 AS rel_strength_30m,
            ((m.close_0945 - mo.close_5d_ago) / NULLIF(mo.close_5d_ago, 0) - (nm.nifty_close_0945 - nmo.nifty_close_5d) / NULLIF(nmo.nifty_close_5d, 0)) * 100 AS rel_strength_5d,
            CASE WHEN (m.close_0945 - m.open_0915) / NULLIF(m.open_0915, 0) > (nm.nifty_close_0945 - nm.nifty_open_0915) / NULLIF(nm.nifty_open_0915, 0) THEN 1 ELSE 0 END AS beats_nifty_30m,
            np.nifty_daily_ret_prev AS nifty_daily_ret_prev,
            
            -- === MULTI-TIMEFRAME LAGGED FEATURES (15) ===
            (m.close_0945 - mo.close_10d_ago) / NULLIF(mo.close_10d_ago, 0) * 100 AS mom_10d,
            (m.close_0945 - mo.close_20d_ago) / NULLIF(mo.close_20d_ago, 0) * 100 AS mom_20d,
            mo.avg_ret_5d,
            mo.avg_ret_10d,
            mo.avg_range_10d,
            mo.vol_10d,
            mo.vol_20d,
            mo.daily_vol_ratio,
            mo.ret_1d_ago,
            mo.ret_2d_ago,
            mo.range_1d_ago,
            mo.avg_vol_5d / NULLIF(mo.avg_vol_10d, 0) AS vol_trend,  -- 5d avg vol / 10d avg vol
            mo.avg_vol_5d,
            LAG(mo.direction, 1) OVER (PARTITION BY mo.symbol ORDER BY mo.trade_date) AS prev_day_direction,
            -- ATR approximation: (prev_day_range + avg_range_10d) / 2
            (mo.range_1d_ago + mo.avg_range_10d) / 2.0 / NULLIF(m.high_0945 - m.low_0945, 0) * 100 AS atr_ratio,
            (nm.nifty_close_0945 - nmo.nifty_close_10d) / NULLIF(nmo.nifty_close_10d, 0) * 100 AS nifty_mom_10d,
            np.nifty_ret_1d_ago,
            np.nifty_ret_5d_ago,
            COALESCE(mva.avg_vol_20d, 0) AS avg_vol_20d
            
        FROM morning_dedup m
        LEFT JOIN prev p ON m.symbol = p.symbol AND m.trade_date = p.trade_date
        LEFT JOIN daily_features mo ON m.symbol = mo.symbol AND m.trade_date = mo.trade_date
        LEFT JOIN prev_dir pd ON m.symbol = pd.symbol AND m.trade_date = pd.trade_date
        LEFT JOIN morning_vol_avg mva ON m.symbol = mva.symbol AND m.trade_date = mva.trade_date
        LEFT JOIN nifty_morning_dedup nm ON m.trade_date = nm.trade_date
        LEFT JOIN nifty_mom nmo ON m.trade_date = nmo.trade_date
        LEFT JOIN nifty_perf np ON m.trade_date = np.trade_date
        WHERE m.morning_bars >= 30 AND m.open_0915 > 0
        ORDER BY m.symbol, m.trade_date
    """).fetchdf()

    conn.close()
    
    # ══════════════════════════════════════════════════════════════
    # PHASE 8: Cross-sectional features (computed in pandas)
    # ══════════════════════════════════════════════════════════════
    print(f"  Computing cross-sectional features...")
    
    # Group by date to compute ranks
    for date, group in df.groupby("date"):
        idx = group.index
        n = len(group)
        if n < 10:
            continue
        
        # Rank of ret_30m (higher = stronger momentum)
        df.loc[idx, "rank_ret_30m"] = group["ret_30m"].rank(pct=True)
        df.loc[idx, "zscore_ret_30m"] = (group["ret_30m"] - group["ret_30m"].mean()) / group["ret_30m"].std()
        
        # Rank of gap_up_pct
        df.loc[idx, "rank_gap_up"] = group["gap_up_pct"].rank(pct=True)
        
        # Rank of rvol
        df.loc[idx, "rank_rvol"] = group["rvol"].rank(pct=True)
        
        # Rank of rel_strength_30m
        df.loc[idx, "rank_rel_strength"] = group["rel_strength_30m"].rank(pct=True)
        
        # Rank of range_30m
        df.loc[idx, "rank_range"] = group["range_30m"].rank(pct=True)
        
        # Rank of mom_5d
        df.loc[idx, "rank_mom_5d"] = group["mom_5d"].rank(pct=True)
        
        # How many stocks are beating NIFTY today?
        df.loc[idx, "pct_beats_nifty"] = group["beats_nifty_30m"].mean()
        
        # Rank of obv_delta
        df.loc[idx, "rank_obv"] = group["obv_delta"].rank(pct=True)
        
        # Rank of vol_surge
        df.loc[idx, "rank_vol_surge"] = group["vol_surge"].rank(pct=True)
    
    df = df.dropna(subset=["rank_ret_30m"])
    
    # Fill remaining NAs
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    df[numeric_cols] = df[numeric_cols].fillna(0)
    
    print(f"Features: {len(df):,} rows x {len(df.columns)} cols ({len(df.select_dtypes(include=[np.number]).columns)} numeric)")
    print(f"Symbols: {df['symbol'].nunique()}, Dates: {df['date'].min()} -> {df['date'].max()}")
    print(f"New features: rank_ret_30m, zscore_ret_30m, rank_gap_up, rank_rvol, rank_rel_strength, rank_range, rank_mom_5d, pct_beats_nifty, rank_obv, rank_vol_surge")
    print(f"New daily features: mom_10d, mom_20d, avg_ret_5d, avg_ret_10d, avg_range_10d, vol_10d, vol_20d, daily_vol_ratio, ret_1d_ago, ret_2d_ago, range_1d_ago, vol_trend, avg_vol_5d, atr_ratio, nifty_mom_10d, nifty_ret_1d_ago, nifty_ret_5d_ago")
    
    df.to_parquet(str(FEATURES_PATH), index=False)
    print(f"Saved: {FEATURES_PATH}")

if __name__ == "__main__":
    main()
