"""Parameter Grid Search: Pullback × Trail — 16 combinations.

Optimized: queries all candle data ONCE, then runs 16 sims in-memory.
"""
from __future__ import annotations
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import FEATURES_PATH, LABELS_PATH, POC_DATA, PROJECT_ROOT
import numpy as np
import pandas as pd
import duckdb

SLIPPAGE_PCT = 0.05
TOP_K = 3
START_CAPITAL = 10_00_000
TEST_YEARS = [2023, 2024, 2025]
CANDLES_DIR = PROJECT_ROOT / "market_data" / "equities" / "candles" / "timeframe=1m"

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

# Parameter grids
PULLBACKS = [0.5, 1.0, 1.5, 2.0]
TRAILS = [1.5, 2.0, 3.0, 4.0]


def compute_metrics(daily_returns: pd.Series, name: str) -> dict:
    daily = daily_returns.dropna().values
    if len(daily) < 5:
        return {"error": "Insufficient data"}
    n_days = len(daily)
    mean_daily = np.mean(daily)
    std_daily = np.std(daily)
    sharpe = (mean_daily / std_daily) * np.sqrt(252) if std_daily > 0 else 0.0
    downside = daily[daily < 0]
    downside_std = np.std(downside) if len(downside) > 1 else std_daily
    sortino = (mean_daily / downside_std) * np.sqrt(252) if downside_std > 0 else 0.0
    cumulative = np.cumprod(1 + daily / 100)
    total_return = (cumulative[-1] - 1) * 100
    years = n_days / 252
    cagr = ((cumulative[-1]) ** (1 / years) - 1) * 100 if years > 0 else 0.0
    peak = np.maximum.accumulate(cumulative)
    dd = (peak - cumulative) / peak * 100
    max_dd = np.max(dd)
    wins = daily[daily > 0]
    losses = daily[daily < 0]
    win_rate = len(wins) / n_days * 100
    avg_win = np.mean(wins) if len(wins) > 0 else 0.0
    avg_loss = abs(np.mean(losses)) if len(losses) > 0 else 0.0
    gross_profit = np.sum(wins) if len(wins) > 0 else 0
    gross_loss = abs(np.sum(losses)) if len(losses) > 0 else 0
    pf = gross_profit / gross_loss if gross_loss > 0 else 0.0
    return {
        "n_days": n_days,
        "total_return": round(total_return, 2),
        "cagr": round(cagr, 2),
        "sharpe": round(sharpe, 2),
        "sortino": round(sortino, 2),
        "max_dd": round(max_dd, 2),
        "win_rate": round(win_rate, 1),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "profit_factor": round(pf, 2),
    }


def apply_stage1(df: pd.DataFrame) -> pd.DataFrame:
    candidates = df.copy()
    for _, (col, threshold) in STAGE1_RULES.items():
        if threshold is not None:
            candidates = candidates[candidates[col] > threshold]
        else:
            candidates = candidates[candidates[col] == 1]
    return candidates


def simulate_pick(candles_df: pd.DataFrame, open_0945: float, close_1515: float,
                  pullback_pct: float, trail_pct: float) -> tuple:
    """Simulate one pick. Returns (entered, return_pct, exit_reason)."""
    if candles_df.empty:
        return (False, 0.0, "no_data")
    
    high_so_far = open_0945
    entry_price = None
    trail_stop = None
    highest_since_entry = None
    exit_reason = "no_entry"
    exit_price = 0.0
    
    for _, c in candles_df.iterrows():
        c_high = float(c["high"])
        c_low = float(c["low"])
        c_close = float(c["close"])
        
        high_so_far = max(high_so_far, c_high)
        
        if entry_price is None:
            pullback = (c_close - high_so_far) / high_so_far * 100
            if pullback <= -pullback_pct:
                entry_price = c_close
                highest_since_entry = max(c_high, c_close)
                trail_stop = highest_since_entry * (1 - trail_pct / 100)
        else:
            if c_high > highest_since_entry:
                highest_since_entry = c_high
                trail_stop = highest_since_entry * (1 - trail_pct / 100)
            if c_low <= trail_stop:
                exit_price = trail_stop
                exit_reason = "stop"
                break
    else:
        if entry_price is not None:
            exit_price = close_1515
            exit_reason = "close"
    
    if entry_price is None:
        return (False, 0.0, "no_pullback")
    
    # Slippage
    entry_cost = SLIPPAGE_PCT / 100 * entry_price
    exit_cost = SLIPPAGE_PCT / 100 * exit_price if exit_price > 0 else 0
    net_entry = entry_price + entry_cost
    net_exit = exit_price - exit_cost
    ret = (net_exit - net_entry) / net_entry * 100
    return (True, ret, exit_reason)


def load_all_candle_data(conn, picks_df: pd.DataFrame) -> dict:
    """Load ALL candle data for all picks. Returns dict keyed by (symbol, date_str)."""
    print("  Querying candle data for all picks...")
    candle_cache = {}
    total = len(picks_df)
    start = time.time()
    
    for i, (_, pick) in enumerate(picks_df.iterrows()):
        sym = pick["symbol"]
        dt_str = str(pick["date"].date()) if hasattr(pick["date"], "date") else str(pick["date"])[:10]
        key = (sym, dt_str)
        
        if key in candle_cache:
            continue
        
        try:
            df = conn.execute(f"""
                SELECT timestamp, open, high, low, close
                FROM read_parquet('{CANDLES_DIR}/symbol={sym}/data.parquet', hive_partitioning=true)
                WHERE timestamp >= timestamp '{dt_str} 09:45:00'
                  AND timestamp <= timestamp '{dt_str} 15:15:00'
                ORDER BY timestamp
            """).fetchdf()
            meta = (float(df.iloc[0]["open"]) if len(df) > 0 else None,
                    float(df.iloc[-1]["close"]) if len(df) > 0 else None)
            candle_cache[key] = (df, meta[0], meta[1])
        except Exception:
            candle_cache[key] = (pd.DataFrame(), None, None)
        
        if (i + 1) % 500 == 0 or i + 1 == total:
            elapsed = time.time() - start
            print(f"    {i+1}/{total} picks ({elapsed:.0f}s)")
    
    return candle_cache


def main():
    print("=" * 75)
    print("  PARAMETER GRID SEARCH: Pullback (0.5–2.0) × Trail (1.5–4.0)")
    print("=" * 75)

    # ── Load data ──
    print("\nLoading features & labels...")
    features = pd.read_parquet(FEATURES_PATH)
    labels = pd.read_parquet(LABELS_PATH)
    features["date"] = pd.to_datetime(features["date"])
    labels["date"] = pd.to_datetime(labels["date"])
    df = features.merge(labels[["symbol", "date", "return_pct"]], on=["symbol", "date"], how="inner")
    feats = [f for f in ALL_FEATURES if f in df.columns]
    df = df.dropna(subset=feats)
    df["year"] = df["date"].dt.year
    candidates = apply_stage1(df)
    candidates = candidates[candidates["year"].isin(TEST_YEARS)]
    
    # ── Identify picks ──
    all_picks = []
    for date, day_df in candidates.groupby("date"):
        if len(day_df) >= TOP_K:
            all_picks.append(day_df.nlargest(TOP_K, "ret_30m"))
    picks_df = pd.concat(all_picks) if all_picks else pd.DataFrame()
    print(f"Total picks: {len(picks_df)} ({picks_df['date'].nunique()} days)")
    
    # ── Load all candle data ──
    conn = duckdb.connect(":memory:")
    candle_cache = load_all_candle_data(conn, picks_df)
    conn.close()
    print(f"  Unique (symbol, date) pairs cached: {len(candle_cache)}")
    
    # ── Compute buy-at-0945 baseline (no stop) ──
    baseline_ret = picks_df.groupby("date")["return_pct"].mean()
    baseline_cost = SLIPPAGE_PCT * 2
    baseline_daily = baseline_ret - baseline_cost
    baseline_metrics = compute_metrics(baseline_daily, "Buy@09:45")
    
    # ── Market avg benchmark ──
    full_test = df[df["year"].isin(TEST_YEARS)]
    market_returns = full_test.groupby("date")["return_pct"].mean()
    common_days = baseline_daily.index.intersection(market_returns.index)
    mkt_metrics = compute_metrics(market_returns[common_days], "Market Avg")
    
    # ── Grid search ──
    print(f"\nRunning {len(PULLBACKS) * len(TRAILS)} parameter combinations...")
    grid_results = []
    
    for pb in PULLBACKS:
        for tr in TRAILS:
            # Simulate all picks with these params
            returns = []
            for _, pick in picks_df.iterrows():
                sym = pick["symbol"]
                dt_str = str(pick["date"].date()) if hasattr(pick["date"], "date") else str(pick["date"])[:10]
                key = (sym, dt_str)
                
                if key in candle_cache:
                    candles, o95, c15 = candle_cache[key]
                    if o95 is not None and c15 is not None:
                        _, ret, _ = simulate_pick(candles, o95, c15, pb, tr)
                        returns.append(ret)
                    else:
                        returns.append(0.0)
                else:
                    returns.append(0.0)
            
            # Daily portfolio returns
            pick_df = picks_df.copy()
            pick_df["sim_ret"] = returns
            daily = pick_df.groupby("date")["sim_ret"].mean()
            
            metrics = compute_metrics(daily, f"PB{pb}_TR{tr}")
            grid_results.append({
                "pullback": pb, "trail": tr,
                **metrics,
                "buy_0945_total": baseline_metrics["total_return"],
                "improvement_vs_buy0945": round(metrics["total_return"] - baseline_metrics["total_return"], 2),
            })
            
            print(f"  PB={pb:3.1f}% TR={tr:3.1f}% → Ret={metrics['total_return']:>+7.2f}%  Sharpe={metrics['sharpe']:>5.2f}  DD={metrics['max_dd']:>5.1f}%  PF={metrics['profit_factor']:>5.2f}  WR={metrics['win_rate']:>5.1f}%")
    
    # ── Rank by total return ──
    grid_df = pd.DataFrame(grid_results)
    grid_df = grid_df.sort_values("total_return", ascending=False).reset_index(drop=True)
    grid_df["rank"] = range(1, len(grid_df) + 1)
    
    # ── Best combination ──
    best = grid_df.iloc[0]
    best_pb = best["pullback"]
    best_tr = best["trail"]
    
    print(f"\n{'='*75}")
    print(f"  BEST COMBINATION: Pullback {best_pb}% + Trail {best_tr}%")
    print(f"{'='*75}")
    print(f"  Total return:       {best['total_return']:>+8.2f}%")
    print(f"  CAGR:               {best['cagr']:>+8.2f}%")
    print(f"  Sharpe:             {best['sharpe']:>8.2f}")
    print(f"  Sortino:            {best['sortino']:>8.2f}")
    print(f"  Max DD:             {best['max_dd']:>8.2f}%")
    print(f"  Win rate:           {best['win_rate']:>7.1f}%")
    print(f"  Profit factor:      {best['profit_factor']:>8.2f}")
    print(f"  vs Buy@09:45:       {best['improvement_vs_buy0945']:>+8.2f}pp")
    
    # ── Full ranked table ──
    print(f"\n{'='*75}")
    print("  FULL RANKINGS")
    print(f"{'='*75}")
    print(f" {'Rank':<5} {'PB%':<7} {'Trail%':<8} {'Ret%':<9} {'Sharpe':<8} {'DD%':<8} {'WR%':<7} {'PF':<6} {'vs 09:45':<10}")
    print("-" * 75)
    
    for _, row in grid_df.iterrows():
        rank = row["rank"]
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, "")
        marker = "  👈" if row["profit_factor"] >= 1.0 else ""
        print(f" {medal:<5} {row['pullback']:<6.1f}% {row['trail']:<7.1f}% {row['total_return']:<+8.2f}% {row['sharpe']:<7.2f} {row['max_dd']:<7.1f}% {row['win_rate']:<6.1f}% {row['profit_factor']:<5.2f} {row['improvement_vs_buy0945']:<+9.2f}pp{marker}")
    
    # ── Which combos are profitable (if any) ──
    profitable = grid_df[grid_df["profit_factor"] >= 1.0]
    if len(profitable) > 0:
        print(f"\n  ✅ PROFITABLE COMBOS (PF >= 1.0): {len(profitable)}")
        for _, row in profitable.iterrows():
            print(f"     PB={row['pullback']}% TR={row['trail']}% → Ret={row['total_return']:+.2f}% PF={row['profit_factor']:.2f}")
    else:
        print(f"\n  ❌ No profitable combination found")
    
    # ── Summary heatmap (returns) ──
    print(f"\n{'='*75}")
    print("  RETURN HEATMAP (Total Return %)")
    print(f"{'='*75}")
    header = "  PB ↓ \\ Trail → "
    for tr in TRAILS:
        header += f" {tr:>7.1f}%"
    print(header)
    for pb in PULLBACKS:
        line = f"  {pb:<6.1f}%    "
        for tr in TRAILS:
            row = grid_df[(grid_df["pullback"] == pb) & (grid_df["trail"] == tr)]
            if len(row) > 0:
                val = row.iloc[0]["total_return"]
                line += f" {val:>+7.2f}%"
            else:
                line += "      N/A"
        print(line)
    
    # ── Save full report ──
    report = {
        "config": {"pullbacks": PULLBACKS, "trails": TRAILS, "slippage": SLIPPAGE_PCT, "top_k": TOP_K},
        "baseline": {
            "buy_at_0945": {"total_return": baseline_metrics["total_return"],
                           "sharpe": baseline_metrics["sharpe"],
                           "max_dd": baseline_metrics["max_dd"],
                           "win_rate": baseline_metrics["win_rate"],
                           "profit_factor": baseline_metrics["profit_factor"]},
            "market_avg": {"total_return": mkt_metrics["total_return"]},
        },
        "best": {
            "pullback": float(best_pb), "trail": float(best_tr),
            "total_return": float(grid_df.iloc[0]["total_return"]),
            "sharpe": float(grid_df.iloc[0]["sharpe"]),
            "sortino": float(grid_df.iloc[0]["sortino"]),
            "max_dd": float(grid_df.iloc[0]["max_dd"]),
            "win_rate": float(grid_df.iloc[0]["win_rate"]),
            "profit_factor": float(grid_df.iloc[0]["profit_factor"]),
        },
        "ranked_results": grid_df[["rank", "pullback", "trail", "total_return", "sharpe",
                                    "max_dd", "win_rate", "profit_factor",
                                    "improvement_vs_buy0945"]].to_dict(orient="records"),
        "n_profitable": int(len(profitable)),
        "profitable_combos": profitable[["pullback", "trail", "total_return", "profit_factor"]].to_dict(orient="records") if len(profitable) > 0 else [],
    }
    
    report_path = POC_DATA / "grid_search_report.json"
    report_path.write_text(json.dumps(report, indent=2))
    print(f"\nReport saved: {report_path}")
    
    # Also save CSV for easy viewing
    csv_path = POC_DATA / "grid_search_results.csv"
    grid_df.to_csv(csv_path, index=False)
    print(f"CSV saved: {csv_path}")


if __name__ == "__main__":
    main()
