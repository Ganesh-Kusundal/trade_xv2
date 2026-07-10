"""Portfolio Simulation: Scanner → Enter on Pullback → Trailing Stop-Loss.

Strategy:
  1. Scanner selects top 3 by ret_30m from Stage 1 candidates at 09:45
  2. Don't buy at 09:45 — wait for a pullback of X% from the day's high
  3. After entry, trail a stop at Y% below the highest price since entry
  4. Exit at 15:15 if not stopped out

Uses 1-minute candle data to simulate the actual intraday price path.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import FEATURES_PATH, LABELS_PATH, POC_DATA, PROJECT_ROOT
import numpy as np
import pandas as pd
import duckdb

# ── Defaults ──
SLIPPAGE_PCT = 0.05  # per leg each way
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


def compute_metrics(daily_returns: pd.Series, name: str) -> dict:
    daily = daily_returns.dropna().values
    if len(daily) < 5:
        return {"error": "Insufficient data", "name": name}
    n_days = len(daily)
    mean_daily = np.mean(daily)
    std_daily = np.std(daily)
    sharpe = (mean_daily / std_daily) * np.sqrt(252) if std_daily > 0 else 0.0
    downside = daily[daily < 0]
    downside_std = np.std(downside) if len(downside) > 1 else std_daily
    sortino = (mean_daily / downside_std) * np.sqrt(252) if downside_std > 0 else 0.0
    cumulative = np.cumprod(1 + daily / 100)
    total_return_pct = (cumulative[-1] - 1) * 100
    years = n_days / 252
    cagr = ((cumulative[-1]) ** (1 / years) - 1) * 100 if years > 0 else 0.0
    peak = np.maximum.accumulate(cumulative)
    dd = (peak - cumulative) / peak * 100
    max_dd = np.max(dd)
    calmar = cagr / max_dd if max_dd > 0 else 0.0
    wins = daily[daily > 0]
    losses = daily[daily < 0]
    win_rate = len(wins) / n_days * 100
    avg_win = np.mean(wins) if len(wins) > 0 else 0.0
    avg_loss = abs(np.mean(losses)) if len(losses) > 0 else 0.0
    avg_win_loss = avg_win / avg_loss if avg_loss > 0 else 0.0
    gross_profit = np.sum(wins) if len(wins) > 0 else 0
    gross_loss = abs(np.sum(losses)) if len(losses) > 0 else 0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0.0
    seq = (daily > 0).astype(int)
    runs = np.diff(np.concatenate(([0], seq, [0])))
    run_starts = np.where(runs == 1)[0]
    run_ends = np.where(runs == -1)[0]
    run_lengths = run_ends - run_starts
    max_consec_wins = int(np.max(run_lengths)) if len(run_lengths) > 0 else 0
    seq_loss = (daily < 0).astype(int)
    runs_loss = np.diff(np.concatenate(([0], seq_loss, [0])))
    loss_starts = np.where(runs_loss == 1)[0]
    loss_ends = np.where(runs_loss == -1)[0]
    loss_lengths = loss_ends - loss_starts
    max_consec_losses = int(np.max(loss_lengths)) if len(loss_lengths) > 0 else 0
    ann_vol = std_daily * np.sqrt(252)
    return {
        "name": name, "n_trading_days": n_days,
        "total_return_pct": round(total_return_pct, 2),
        "cagr_pct": round(cagr, 2),
        "ann_volatility_pct": round(ann_vol, 2),
        "sharpe_ratio": round(sharpe, 2),
        "sortino_ratio": round(sortino, 2),
        "calmar_ratio": round(calmar, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "win_rate_pct": round(win_rate, 1),
        "avg_win_pct": round(avg_win, 2),
        "avg_loss_pct": round(avg_loss, 2),
        "avg_win_loss_ratio": round(avg_win_loss, 2),
        "profit_factor": round(profit_factor, 2),
        "max_consecutive_wins": max_consec_wins,
        "max_consecutive_losses": max_consec_losses,
        "mean_daily_return_pct": round(mean_daily, 4),
        "std_daily_return_pct": round(std_daily, 4),
    }


def apply_stage1(df: pd.DataFrame) -> pd.DataFrame:
    candidates = df.copy()
    for _, (col, threshold) in STAGE1_RULES.items():
        if threshold is not None:
            candidates = candidates[candidates[col] > threshold]
        else:
            candidates = candidates[candidates[col] == 1]
    return candidates


def simulate_pullback_trail(
    candles_df: pd.DataFrame,  # minute candles for one symbol on one day
    open_0945: float,
    close_1515: float,
    pullback_pct: float,
    trail_pct: float,
) -> dict:
    """Simulate pullback entry + trailing stop on intraday candle data.
    
    Returns: {entered, entry_time, entry_price, exit_time, exit_price, exit_reason, return_pct}
    """
    if candles_df.empty:
        return {"entered": False, "return_pct": 0.0, "exit_reason": "no_data"}
    
    candles = candles_df.sort_values("timestamp")
    
    high_so_far = open_0945
    entry_price = None
    entry_time = None
    trail_stop = None
    highest_since_entry = None
    
    for _, candle in candles.iterrows():
        ts = candle["timestamp"]
        c_high = float(candle["high"])
        c_low = float(candle["low"])
        c_close = float(candle["close"])
        
        # Update high since 09:45
        high_so_far = max(high_so_far, c_high)
        
        if entry_price is None:
            # Not yet entered — check for pullback
            pullback = (c_close - high_so_far) / high_so_far * 100
            if pullback <= -pullback_pct:
                # Enter at this candle's close (or midpoint of low/high?)
                entry_price = c_close
                entry_time = ts
                highest_since_entry = c_high if c_high > entry_price else entry_price
                trail_stop = highest_since_entry * (1 - trail_pct / 100)
        else:
            # In position — update trail
            if c_high > highest_since_entry:
                highest_since_entry = c_high
                trail_stop = highest_since_entry * (1 - trail_pct / 100)
            
            # Check if stop is hit (candle low crossed the stop)
            if c_low <= trail_stop:
                exit_price = trail_stop
                exit_reason = "trailing_stop"
                break
    else:
        # Held to 15:15
        exit_price = close_1515
        exit_reason = "close_1515"
    
    if entry_price is None:
        # Never entered — no pullback occurred
        return {"entered": False, "return_pct": 0.0, "exit_reason": "no_pullback"}
    
    # Slippage on entry and exit
    entry_cost = SLIPPAGE_PCT / 100 * entry_price
    exit_cost = SLIPPAGE_PCT / 100 * exit_price
    net_entry = entry_price + entry_cost
    net_exit = exit_price - exit_cost
    return_pct = (net_exit - net_entry) / net_entry * 100
    
    return {
        "entered": True,
        "entry_time": str(entry_time),
        "entry_price": round(entry_price, 2),
        "exit_price": round(exit_price, 2),
        "exit_reason": exit_reason,
        "return_pct": round(return_pct, 2),
    }


def load_candles_for_pick(conn, symbol, dt_str) -> pd.DataFrame:
    """Load 1-minute candles for a symbol on a specific day between 09:45 and 15:15."""
    try:
        df = conn.execute(f"""
            SELECT timestamp, open, high, low, close
            FROM read_parquet('{CANDLES_DIR}/symbol={symbol}/data.parquet', hive_partitioning=true)
            WHERE timestamp >= timestamp '{dt_str} 09:45:00'
              AND timestamp <= timestamp '{dt_str} 15:15:00'
            ORDER BY timestamp
        """).fetchdf()
        return df
    except Exception:
        return pd.DataFrame()


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--pullback", type=float, default=1.5, help="Pullback % to enter")
    parser.add_argument("--trail", type=float, default=2.0, help="Trailing stop % below high")
    args = parser.parse_args()
    
    PULL = args.pullback
    TRAIL = args.trail
    NAME = f"Pullback {PULL}% + Trail {TRAIL}%"

    print("=" * 70)
    print(f"  STRATEGY: Scanner → Pullback Entry ({PULL}%) → Trailing Stop ({TRAIL}%)")
    print("=" * 70)

    # ── Load features & labels ──
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

    print(f"Test: {TEST_YEARS}, Candidates: {len(candidates):,}")
    print(f"Params: pullback={PULL}%, trail={TRAIL}%, slippage={SLIPPAGE_PCT}%\n")

    # ── Identify picks ──
    all_picks = []
    for date, day_df in candidates.groupby("date"):
        if len(day_df) < TOP_K:
            continue
        picks = day_df.nlargest(TOP_K, "ret_30m")
        all_picks.append(picks)
    picks_df = pd.concat(all_picks) if all_picks else pd.DataFrame()
    print(f"Total picks: {len(picks_df)} ({picks_df['date'].nunique()} days)")

    # ── Simulate each pick through 1-minute candles ──
    conn = duckdb.connect(":memory:")
    results = []
    total = len(picks_df)
    
    for i, (_, pick) in enumerate(picks_df.iterrows()):
        sym = pick["symbol"]
        dt_str = str(pick["date"].date()) if hasattr(pick["date"], "date") else str(pick["date"])[:10]
        
        # Get open at 09:45 and close at 15:15
        try:
            meta = conn.execute(f"""
                SELECT 
                    MIN(open) FILTER (WHERE timestamp = timestamp '{dt_str} 09:45:00') as open_0945,
                    MIN(close) FILTER (WHERE timestamp = timestamp '{dt_str} 15:15:00') as close_1515
                FROM read_parquet('{CANDLES_DIR}/symbol={sym}/data.parquet', hive_partitioning=true)
                WHERE timestamp >= timestamp '{dt_str} 09:45:00'
                  AND timestamp <= timestamp '{dt_str} 15:15:00'
            """).fetchone()
            open_0945 = float(meta[0]) if meta[0] else None
            close_1515 = float(meta[1]) if meta[1] else None
        except:
            open_0945 = close_1515 = None
        
        if open_0945 is None or close_1515 is None:
            results.append({
                "symbol": sym, "date": str(pick["date"]),
                "entered": False, "return_pct": 0.0, "ret_30m": float(pick["ret_30m"]),
                "full_return": float(pick["return_pct"]),
                "entry_price": None, "exit_price": None,
                "exit_reason": "no_data",
            })
            continue
        
        # Load candles
        candles = load_candles_for_pick(conn, sym, dt_str)
        
        # Simulate
        sim = simulate_pullback_trail(candles, open_0945, close_1515, PULL, TRAIL)
        
        results.append({
            "symbol": sym, "date": str(pick["date"]),
            "entered": sim["entered"],
            "return_pct": sim["return_pct"],
            "ret_30m": float(pick["ret_30m"]),
            "full_return": float(pick["return_pct"]),
            "entry_price": sim.get("entry_price"),
            "exit_price": sim.get("exit_price"),
            "exit_reason": sim.get("exit_reason"),
        })
        
        if (i + 1) % 300 == 0 or i + 1 == total:
            print(f"  Simulated {i + 1}/{total} picks...")
    
    conn.close()
    
    # ── Analyze results ──
    res_df = pd.DataFrame(results)
    
    entered = res_df[res_df["entered"]]
    skipped = res_df[~res_df["entered"]]
    
    entry_rate = len(entered) / len(res_df) * 100
    stop_rate = (entered["exit_reason"] == "trailing_stop").sum() / len(entered) * 100
    hold_rate = (entered["exit_reason"] == "close_1515").sum() / len(entered) * 100
    
    print(f"\n{'─'*65}")
    print(f"  EXECUTION STATS")
    print(f"{'─'*65}")
    print(f"  Entries triggered:     {len(entered)}/{len(res_df)} ({entry_rate:.1f}%)")
    print(f"  Skipped (no pullback): {len(skipped)} ({len(skipped)/len(res_df)*100:.1f}%)")
    print(f"  Stopped out by trail:  {(entered['exit_reason']=='trailing_stop').sum()} ({stop_rate:.1f}% of entries)")
    print(f"  Held to 15:15:         {(entered['exit_reason']=='close_1515').sum()} ({hold_rate:.1f}% of entries)")
    
    avg_ret_entered = entered["return_pct"].mean()
    avg_ret_skipped = skipped["full_return"].mean()
    print(f"  Avg return (entered):  {avg_ret_entered:+.2f}%")
    print(f"  Avg return (skipped):  {avg_ret_skipped:+.2f}% (would have been if bought at 09:45)")
    
    # ── Build daily portfolio returns ──
    # Days where we entered at least one position
    pick_return = entered.groupby("date")["return_pct"].mean()
    no_skip_return = res_df.groupby("date")["full_return"].mean()  # buy at 09:45, no stop
    
    print(f"\n{'-'*65}")
    print(f"  PORTFOLIO METRICS")
    print(f"{'-'*65}")
    
    metrics_pb = compute_metrics(pick_return, NAME)
    metrics_no = compute_metrics(no_skip_return, "Buy at 09:45")
    
    # Market avg benchmark
    full_test = df[df["year"].isin(TEST_YEARS)]
    market_returns = full_test.groupby("date")["return_pct"].mean()
    market_returns.index = pd.to_datetime(market_returns.index)
    common_days = pick_return.index.intersection(market_returns.index)
    metrics_mkt = compute_metrics(market_returns[common_days], "Market Avg")
    
    for metrics in [metrics_pb, metrics_no, metrics_mkt]:
        if "error" in metrics:
            print(f"\n{metrics['name']}: {metrics['error']}")
            continue
        print(f"\n{'─'*65}")
        print(f"  {metrics['name']}")
        print(f"{'─'*65}")
        print(f"  Total return:           {metrics['total_return_pct']:>+8.2f}%")
        print(f"  CAGR:                   {metrics['cagr_pct']:>+8.2f}%")
        print(f"  Ann volatility:         {metrics['ann_volatility_pct']:>8.2f}%")
        print(f"  Sharpe:                 {metrics['sharpe_ratio']:>8.2f}")
        print(f"  Sortino:                {metrics['sortino_ratio']:>8.2f}")
        print(f"  Calmar:                 {metrics['calmar_ratio']:>8.2f}")
        print(f"  Max DD:                 {metrics['max_drawdown_pct']:>8.2f}%")
        print(f"  Win rate:               {metrics['win_rate_pct']:>7.1f}%")
        print(f"  Avg win/loss:           {metrics['avg_win_pct']:.2f}% / {metrics['avg_loss_pct']:.2f}%")
        print(f"  Win/Loss ratio:         {metrics['avg_win_loss_ratio']:>8.2f}")
        print(f"  Profit factor:          {metrics['profit_factor']:>8.2f}")
        print(f"  Max cons wins:          {metrics['max_consecutive_wins']:>4d}")
        print(f"  Max cons losses:        {metrics['max_consecutive_losses']:>4d}")

    # ── Comparison table ──
    print(f"\n{'='*65}")
    print(f"  COMPARISON: 3 Strategies")
    print(f"{'='*65}")
    print(f"{'Metric':<28} {'Pullback+Trail':<17} {'Buy at 09:45':<17} {'Market Avg':<17}")
    print("-" * 79)
    
    for label, key in [
        ("Total Return %", "total_return_pct"),
        ("CAGR %", "cagr_pct"),
        ("Sharpe", "sharpe_ratio"),
        ("Sortino", "sortino_ratio"),
        ("Max DD %", "max_drawdown_pct"),
        ("Win Rate %", "win_rate_pct"),
        ("Profit Factor", "profit_factor"),
    ]:
        def fmt(v):
            return f"{v:>16}" if isinstance(v, (int, float)) else f"{'N/A':>16}"
        line = f"{label:<28}"
        line += fmt(metrics_pb.get(key, "N/A"))
        line += fmt(metrics_no.get(key, "N/A"))
        line += fmt(metrics_mkt.get(key, "N/A"))
        print(line)
    
    # ── Save ──
    res_df.to_csv(POC_DATA / f"picks_pullback_{PULL}_trail_{TRAIL}.csv", index=False)
    report = {
        "strategy": NAME,
        "config": {"pullback_pct": PULL, "trail_pct": TRAIL, "slippage_pct": SLIPPAGE_PCT},
        "execution": {
            "total_picks": len(res_df),
            "entries_triggered": int(entry_rate),
            "entry_rate_pct": round(entry_rate, 1),
            "stopped_out_pct": round(stop_rate, 1),
            "held_to_close_pct": round(hold_rate, 1),
        },
        "pullback_trail": metrics_pb,
        "buy_0945": metrics_no,
        "market_avg": metrics_mkt,
    }
    (POC_DATA / f"portfolio_pullback_{PULL}_{TRAIL}.json").write_text(json.dumps(report, indent=2))
    print(f"\nReport saved: {POC_DATA / f'portfolio_pullback_{PULL}_{TRAIL}.json'}")


if __name__ == "__main__":
    main()
