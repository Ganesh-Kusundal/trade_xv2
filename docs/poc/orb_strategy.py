"""Opening Range Breakout (ORB) Strategy — Indian NSE Market.

Simulates ORB on NSE 1-minute candle data.

Strategy:
  1. Define opening range (09:15-09:30)
  2. Watch for breakout above range_high (long) or below range_low (short)
  3. Entry: at breakout price + slippage
  4. Stop-loss: opposite side of the range
  5. Trailing stop: ATR-based (optional)
  6. Exit at 15:15 if not stopped out

Compares:
  - ORB on all stocks (no scanner)
  - ORB only on momentum-scanner picks
  - Buy-at-09:45 baseline
"""
from __future__ import annotations
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import FEATURES_PATH, LABELS_PATH, POC_DATA, PROJECT_ROOT
import numpy as np
import pandas as pd
import duckdb

# ── Config ──
SLIPPAGE_PCT = 0.05
TOP_K = 3
START_CAPITAL = 10_00_000
TEST_YEARS = [2023, 2024, 2025]
CANDLES_DIR = PROJECT_ROOT / "market_data" / "equities" / "candles" / "timeframe=1m"

# Opening range: 09:15 to 09:30 (15 min)
RANGE_START_HOUR, RANGE_START_MIN = 9, 15
RANGE_END_HOUR, RANGE_END_MIN = 9, 30

STAGE1_RULES = {
    "ret_30m > 1%": ("ret_30m", 1.0),
    "rvol > 1.5": ("rvol", 1.5),
    "beats_nifty_30m == 1": ("beats_nifty_30m", None),
}

ALL_FEATURES = [
    "ret_30m", "range_30m", "rvol", "vol_surge", "obv_delta",
    "gap_up_pct", "rsi_14", "macd_hist", "bb_pctb", "vwap_dev",
    "mom_5d", "mom_10d", "mom_20d",
    "beats_nifty_30m", "rel_strength_30m", "rel_strength_5d",
    "rank_ret_30m", "zscore_ret_30m", "rank_gap_up", "rank_rvol",
    "rank_rel_strength", "rank_range", "rank_mom_5d", "rank_obv", "rank_vol_surge",
    "avg_vol_30m", "avg_vol_5d", "avg_vol_20d",
    "vol_10d", "vol_20d", "atr_ratio",
    "nifty_ret_30m", "nifty_mom_5d", "nifty_mom_10d",
    "nifty_daily_ret_prev", "nifty_ret_1d_ago", "nifty_ret_5d_ago",
    "prev_day_direction", "daily_vol_ratio", "vol_trend",
    "avg_range_10d", "prev_day_ret", "avg_ret_5d", "avg_ret_10d",
    "ret_1d_ago", "ret_2d_ago", "range_1d_ago",
    "consec_days", "pct_beats_nifty", "dow",
]


def compute_metrics(daily_returns: pd.Series, name: str) -> dict:
    daily = daily_returns.dropna().values
    if len(daily) < 5:
        return {"error": f"Insufficient data ({len(daily)} days)", "name": name}
    n = len(daily)
    md = np.mean(daily)
    sd = np.std(daily)
    sharpe = (md / sd) * np.sqrt(252) if sd > 0 else 0.0
    dn = daily[daily < 0]
    dsd = np.std(dn) if len(dn) > 1 else sd
    sortino = (md / dsd) * np.sqrt(252) if dsd > 0 else 0.0
    cum = np.cumprod(1 + daily / 100)
    tr = (cum[-1] - 1) * 100
    cagr = ((cum[-1]) ** (1 / (n / 252)) - 1) * 100 if n >= 20 else 0.0
    peak = np.maximum.accumulate(cum)
    mdd = np.max((peak - cum) / peak * 100)
    calmar = cagr / mdd if mdd > 0 else 0.0
    wins = daily[daily > 0]
    losses = daily[daily < 0]
    wr = len(wins) / n * 100
    aw = np.mean(wins) if len(wins) > 0 else 0.0
    al = abs(np.mean(losses)) if len(losses) > 0 else 0.0
    pf = np.sum(wins) / abs(np.sum(losses)) if abs(np.sum(losses)) > 0 else 0.0
    return {
        "name": name, "n_days": n,
        "total_return": round(tr, 2), "cagr": round(cagr, 2),
        "sharpe": round(sharpe, 2), "sortino": round(sortino, 2),
        "calmar": round(calmar, 2), "max_dd": round(mdd, 2),
        "win_rate": round(wr, 1), "avg_win": round(aw, 2),
        "avg_loss": round(al, 2), "profit_factor": round(pf, 2),
    }


def apply_stage1(df: pd.DataFrame) -> pd.DataFrame:
    candidates = df.copy()
    for _, (col, threshold) in STAGE1_RULES.items():
        if threshold is not None:
            candidates = candidates[candidates[col] > threshold]
        else:
            candidates = candidates[candidates[col] == 1]
    return candidates


def simulate_orb_for_pick(candles_df: pd.DataFrame, range_high: float, range_low: float,
                          close_1515: float, use_trail: bool, atr_mult: float = 2.0) -> dict:
    """Simulate ORB for one stock-day.
    
    1. After range closes (09:30), watch for breakout above range_high or below range_low
    2. Enter at breakout + slippage
    3. Stop at opposite side of range (or trail if use_trail=True)
    4. Exit at 15:15 if not stopped
    
    Returns: {direction, entry_price, exit_price, return_pct, exit_reason}
    """
    if range_high is None or range_low is None or candles_df.empty:
        return {"entered": False, "return_pct": 0.0, "direction": "none"}
    
    candles = candles_df.sort_values("timestamp").copy()
    if len(candles) < 2:
        return {"entered": False, "return_pct": 0.0, "direction": "none"}
    
    entry_price = None
    direction = None
    trail_stop = None
    highest_since_entry = None
    lowest_since_entry = None
    entry_cost = SLIPPAGE_PCT / 100
    
    for i, (_, c) in enumerate(candles.iterrows()):
        ts = c["timestamp"]
        c_high = float(c["high"])
        c_low = float(c["low"])
        c_close = float(c["close"])
        
        if entry_price is None:
            # Check for breakout
            if c_high > range_high:
                # Long: price breaks above range
                entry_price = range_high  # Assume fill at range high
                direction = "long"
                trail_stop = range_low  # Initial stop at opposite side
                highest_since_entry = c_high
            elif c_low < range_low:
                # Short: price breaks below range
                entry_price = range_low  # Assume fill at range low
                direction = "short"
                trail_stop = range_high  # Initial stop at opposite side
                lowest_since_entry = c_low
        else:
            if direction == "long":
                # Update highest since entry
                if c_high > highest_since_entry:
                    highest_since_entry = c_high
                    if use_trail:
                        # Trail: ATR-based — move stop up to trail below highest
                        # For simplicity, use a fixed % trail based on range size
                        trail_range = range_high - range_low
                        trail_dist = trail_range * atr_mult if trail_range > 0 else range_high * 0.01
                        trail_stop = max(trail_stop, highest_since_entry - trail_dist)
                    else:
                        trail_stop = range_low  # Fixed stop at opposite side
                
                # Check if stopped
                if c_low <= trail_stop:
                    exit_price = trail_stop
                    exit_reason = "stop"
                    break
            else:  # short
                if c_low < lowest_since_entry:
                    lowest_since_entry = c_low
                    if use_trail:
                        trail_range = range_high - range_low
                        trail_dist = trail_range * atr_mult if trail_range > 0 else range_high * 0.01
                        trail_stop = min(trail_stop, lowest_since_entry + trail_dist)
                    else:
                        trail_stop = range_high
                
                if c_high >= trail_stop:
                    exit_price = trail_stop
                    exit_reason = "stop"
                    break
    else:
        if entry_price is not None:
            exit_price = close_1515
            exit_reason = "close"
    
    if entry_price is None:
        return {"entered": False, "return_pct": 0.0, "direction": "none"}
    
    # Compute return with slippage
    if direction == "long":
        net_entry = entry_price * (1 + entry_cost)
        net_exit = exit_price * (1 - entry_cost)
        ret = (net_exit - net_entry) / net_entry * 100
    else:  # short
        net_entry = entry_price * (1 - entry_cost)  # Selling, so we get less
        net_exit = exit_price * (1 + entry_cost)     # Buying back, paying more
        ret = (net_entry - net_exit) / net_entry * 100  # Short: sold high, bought low
    
    return {
        "entered": True,
        "direction": direction,
        "entry_price": round(entry_price, 2),
        "exit_price": round(exit_price, 2),
        "return_pct": round(ret, 2),
        "exit_reason": exit_reason,
    }


def main():
    print("=" * 75)
    print("  OPENING RANGE BREAKOUT (ORB) — Indian NSE Market")
    print(f"  Range: {RANGE_START_HOUR:02d}:{RANGE_START_MIN:02d}–{RANGE_END_HOUR:02d}:{RANGE_END_MIN:02d}")
    print("=" * 75)
    
    # Test two modes: with and without trailing stop
    for use_trail, trail_label in [(False, "fixed_stop"), (True, "atr_trail_2x")]:
        print(f"\n{'─'*75}")
        print(f"  MODE: {'Fixed Stop (range opposite side)' if not use_trail else 'ATR Trailing Stop (2x range)'}")
        print(f"{'─'*75}")
        
        # ── Test period subset for speed → use Q1 2023 for quick test, then full data
        # For full run, use all test years
        use_full = True  # Set False for quick test
        
        # ── Load labels & features for scanner ──
        features = pd.read_parquet(FEATURES_PATH)
        labels = pd.read_parquet(LABELS_PATH)
        features["date"] = pd.to_datetime(features["date"])
        labels["date"] = pd.to_datetime(labels["date"])
        
        df = features.merge(labels[["symbol", "date", "return_pct"]], on=["symbol", "date"], how="inner")
        feats = [f for f in ALL_FEATURES if f in df.columns]
        df = df.dropna(subset=feats)
        df["year"] = df["date"].dt.year
        candidates = apply_stage1(df)
        
        if not use_full:
            df = df[df["date"] < "2023-04-01"]
            candidates = candidates[candidates["date"] < "2023-04-01"]
        else:
            df = df[df["year"].isin(TEST_YEARS)]
            candidates = candidates[candidates["year"].isin(TEST_YEARS)]
        
        conn = duckdb.connect(":memory:")
        
        # ── Get all unique (symbol, date) pairs ──
        all_pairs = df[["symbol", "date"]].drop_duplicates()
        scanner_pairs = candidates[["symbol", "date"]].drop_duplicates()
        
        print(f"\nLoading candle data...")
        print(f"  All stocks: {len(all_pairs):,} (symbol, date) pairs")
        print(f"  Scanner picks: {len(scanner_pairs):,} pairs")
        
        # ── Process ALL stocks with ORB ──
        print(f"\n  Simulating ORB on ALL stocks...")
        all_results = []
        start = time.time()
        total = len(all_pairs)
        
        for i, (_, row) in enumerate(all_pairs.iterrows()):
            sym = row["symbol"]
            dt = row["date"]
            dt_str = str(dt.date()) if hasattr(dt, "date") else str(dt)[:10]
            
            try:
                candles = conn.execute(f"""
                    SELECT timestamp, open, high, low, close
                    FROM read_parquet('{CANDLES_DIR}/symbol={sym}/data.parquet', hive_partitioning=true)
                    WHERE timestamp >= timestamp '{dt_str} 09:15:00'
                      AND timestamp <= timestamp '{dt_str} 15:15:00'
                    ORDER BY timestamp
                """).fetchdf()
                
                if candles.empty:
                    continue
                
                # Compute range
                range_candles = candles[
                    (candles["timestamp"] >= f"{dt_str} 09:15:00") & 
                    (candles["timestamp"] < f"{dt_str} 09:30:00")
                ]
                if range_candles.empty:
                    continue
                
                range_high = float(range_candles["high"].max())
                range_low = float(range_candles["low"].min())
                
                # Post-range candles
                post_range = candles[
                    (candles["timestamp"] >= f"{dt_str} 09:30:00") & 
                    (candles["timestamp"] <= f"{dt_str} 15:15:00")
                ].copy()
                
                close_1515 = float(candles[candles["timestamp"] == f"{dt_str} 15:15:00"]["close"].iloc[0]) if len(candles[candles["timestamp"] == f"{dt_str} 15:15:00"]) > 0 else None
                if close_1515 is None:
                    close_1515 = float(post_range.iloc[-1]["close"])
                
                sim = simulate_orb_for_pick(post_range, range_high, range_low, close_1515, use_trail, atr_mult=2.0)
                
                if sim["entered"]:
                    all_results.append({
                        "symbol": sym, "date": dt,
                        "direction": sim["direction"],
                        "return_pct": sim["return_pct"],
                        "exit_reason": sim["exit_reason"],
                        "range_high": round(range_high, 2),
                        "range_low": round(range_low, 2),
                        "range_size": round(range_high - range_low, 2),
                    })
            except Exception:
                continue
            
            if (i + 1) % 10000 == 0 or i + 1 == total:
                elapsed = time.time() - start
                print(f"    {i+1}/{total} ({elapsed:.0f}s, {len(all_results)} trades so far)")
        
        # ── Process scanner picks with ORB ──
        print(f"\n  Simulating ORB on SCANNER picks only...")
        scanner_results = []
        start = time.time()
        total = len(scanner_pairs)
        
        for i, (_, row) in enumerate(scanner_pairs.iterrows()):
            sym = row["symbol"]
            dt = row["date"]
            dt_str = str(dt.date()) if hasattr(dt, "date") else str(dt)[:10]
            
            try:
                candles = conn.execute(f"""
                    SELECT timestamp, open, high, low, close
                    FROM read_parquet('{CANDLES_DIR}/symbol={sym}/data.parquet', hive_partitioning=true)
                    WHERE timestamp >= timestamp '{dt_str} 09:15:00'
                      AND timestamp <= timestamp '{dt_str} 15:15:00'
                    ORDER BY timestamp
                """).fetchdf()
                
                if candles.empty:
                    continue
                
                range_candles = candles[
                    (candles["timestamp"] >= f"{dt_str} 09:15:00") & 
                    (candles["timestamp"] < f"{dt_str} 09:30:00")
                ]
                if range_candles.empty:
                    continue
                
                range_high = float(range_candles["high"].max())
                range_low = float(range_candles["low"].min())
                
                post_range = candles[
                    (candles["timestamp"] >= f"{dt_str} 09:30:00") & 
                    (candles["timestamp"] <= f"{dt_str} 15:15:00")
                ].copy()
                
                close_1515 = float(candles[candles["timestamp"] == f"{dt_str} 15:15:00"]["close"].iloc[0]) if len(candles[candles["timestamp"] == f"{dt_str} 15:15:00"]) > 0 else float(post_range.iloc[-1]["close"])
                
                sim = simulate_orb_for_pick(post_range, range_high, range_low, close_1515, use_trail, atr_mult=2.0)
                
                if sim["entered"]:
                    scanner_results.append({
                        "symbol": sym, "date": dt,
                        "direction": sim["direction"],
                        "return_pct": sim["return_pct"],
                        "exit_reason": sim["exit_reason"],
                        "range_high": round(range_high, 2),
                        "range_low": round(range_low, 2),
                        "range_size": round(range_high - range_low, 2),
                    })
            except Exception:
                continue
            
            if (i + 1) % 500 == 0 or i + 1 == total:
                elapsed = time.time() - start
                print(f"    {i+1}/{total} ({elapsed:.0f}s, {len(scanner_results)} trades so far)")
        
        conn.close()
        
        # ── Analyze ──
        orb_all = pd.DataFrame(all_results) if all_results else pd.DataFrame()
        orb_scanner = pd.DataFrame(scanner_results) if scanner_results else pd.DataFrame()
        
        if orb_all.empty and orb_scanner.empty:
            print("\n  No trades generated.")
            continue
        
        # Daily portfolio returns
        if not orb_all.empty:
            # Portfolio: take ALL ORB trades, equal weight per day
            orb_all["trade_count"] = orb_all.groupby("date")["symbol"].transform("count")
            orb_all["weight"] = 1.0 / orb_all["trade_count"]
            orb_all["weighted_ret"] = orb_all["return_pct"] * orb_all["weight"]
            orb_daily = orb_all.groupby("date")["weighted_ret"].sum()
        else:
            orb_daily = pd.Series(dtype=float)
        
        if not orb_scanner.empty:
            # Scanner: pick top 3 by ret_30m, apply ORB to those
            # First get the ret_30m for each scanner pick
            scanner_merged = orb_scanner.merge(
                scanner_pairs, on=["symbol", "date"], how="left"
            )
            # For each day, we pick at most 3 stocks from the scanner picks that triggered ORB
            # But we already have scanner_pairs filtered by Stage 1, so these ARE the scanner picks
            # We'll pick top 3 by range_size (larger breakout = stronger signal)
            orb_scanner["top3_rank"] = orb_scanner.groupby("date")["range_size"].rank(ascending=False)
            top3 = orb_scanner[orb_scanner["top3_rank"] <= 3]
            sc_daily = top3.groupby("date")["return_pct"].mean()
        else:
            sc_daily = pd.Series(dtype=float)
        
        print(f"\n  {'─'*65}")
        print(f"  ORB RESULTS — {trail_label}")
        print(f"{'─'*65}")
        print(f"  ORB (all stocks):  {len(orb_all):,} trades on {orb_all['date'].nunique() if not orb_all.empty else 0} days")
        if not orb_all.empty:
            print(f"    Long:  {(orb_all['direction']=='long').sum()} ({((orb_all['direction']=='long').sum()/len(orb_all)*100):.0f}%)")
            print(f"    Short: {(orb_all['direction']=='short').sum()} ({((orb_all['direction']=='short').sum()/len(orb_all)*100):.0f}%)")
            print(f"    Stopped: {(orb_all['exit_reason']=='stop').sum()} ({((orb_all['exit_reason']=='stop').sum()/len(orb_all)*100):.0f}%)")
            print(f"    Held to close: {(orb_all['exit_reason']=='close').sum()} ({((orb_all['exit_reason']=='close').sum()/len(orb_all)*100):.0f}%)")
        
        print(f"  ORB (scanner):    {len(orb_scanner):,} trades on {orb_scanner['date'].nunique() if not orb_scanner.empty else 0} days")
        
        # Metrics
        print(f"\n  {'─'*65}")
        print(f"  PORTFOLIO METRICS")
        print(f"{'─'*65}")
        
        if not orb_daily.empty:
            m_all = compute_metrics(orb_daily, "ORB (all stocks)")
            print(f"\n  ORB All Stocks:")
            print(f"    Total return: {m_all['total_return']:>+8.2f}%  Sharpe: {m_all['sharpe']:>6.2f}  DD: {m_all['max_dd']:>6.1f}%  WR: {m_all['win_rate']:>5.1f}%  PF: {m_all['profit_factor']:>5.2f}")
        
        if not sc_daily.empty:
            m_sc = compute_metrics(sc_daily, "ORB (scanner)")
            print(f"  ORB Scanner:")
            print(f"    Total return: {m_sc['total_return']:>+8.2f}%  Sharpe: {m_sc['sharpe']:>6.2f}  DD: {m_sc['max_dd']:>6.1f}%  WR: {m_sc['win_rate']:>5.1f}%  PF: {m_sc['profit_factor']:>5.2f}")


if __name__ == "__main__":
    main()
