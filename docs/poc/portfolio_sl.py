"""Portfolio Simulation: Momentum Rule with Intraday Stop-Loss.

Uses 1-minute candle data to find the actual intraday low for each pick.
If the stock hits -3% intraday (from 09:45 Open), it's stopped out at -3%.
Otherwise, the full 09:45→15:15 return is realized.

Usage: python3 poc/portfolio_sl.py [--stop-loss 3] [--slippage 0.05]
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import FEATURES_PATH, LABELS_PATH, POC_DATA, PROJECT_ROOT
import numpy as np
import pandas as pd
import duckdb

# ── Defaults ──
SLIPPAGE_PCT = 0.05
TOP_K = 3
STOP_LOSS_PCT = 3.0  # -3% stop-loss
START_CAPITAL = 10_00_000
TEST_YEARS = [2023, 2024, 2025]

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

CANDLES_DIR = PROJECT_ROOT / "market_data" / "equities" / "candles" / "timeframe=1m"


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

    # Max consecutive wins/losses
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
        "name": name,
        "n_trading_days": n_days,
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


def query_intraday_lows(conn: duckdb.DuckDBPyConnection, picks_df: pd.DataFrame) -> pd.DataFrame:
    """For each pick, find the intraday low between 09:45 and 15:15, and the 09:45 open price.
    
    Returns DataFrame with columns: symbol, date, low_0945_1515, open_0945
    """
    # Build a VALUES list for DuckDB
    symbols = picks_df["symbol"].tolist()
    dates = picks_df["date"].tolist()
    
    # Create a temp table with the picks
    conn.execute("CREATE OR REPLACE TEMP TABLE picks (symbol VARCHAR, trade_date DATE)")
    for sym, dt in zip(symbols, dates):
        conn.execute("INSERT INTO picks VALUES (?, ?)", [sym, str(dt.date())])
    
    # Query: for each pick, find the minimum low between 09:45 and 15:15, and the open at 09:45
    result = conn.execute(f"""
        WITH candle_data AS (
            SELECT 
                p.trade_date,
                p.symbol,
                read_parquet('{CANDLES_DIR}/symbol=' || p.symbol || '/data.parquet',
                    hive_partitioning=true) as c
            FROM picks p
        )
        SELECT 
            p.symbol,
            p.trade_date::DATE as date,
            MIN(c.low) FILTER (WHERE c.timestamp BETWEEN (p.trade_date + INTERVAL '9 hours 45 minutes') 
                                                       AND (p.trade_date + INTERVAL '15 hours 15 minutes')) as intraday_low,
            MIN(c.open) FILTER (WHERE c.timestamp = (p.trade_date + INTERVAL '9 hours 45 minutes')) as open_0945,
            MIN(c.close) FILTER (WHERE c.timestamp = (p.trade_date + INTERVAL '15 hours 15 minutes')) as close_1515
        FROM picks p
        LEFT JOIN candles c ON c.symbol = p.symbol
        GROUP BY p.symbol, p.trade_date
    """).fetchdf()
    
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stop-loss", type=float, default=STOP_LOSS_PCT, help="Stop-loss threshold %%")
    parser.add_argument("--slippage", type=float, default=SLIPPAGE_PCT, help="Slippage %% each way")
    parser.add_argument("--name", type=str, default="Momentum + Stop", help="Strategy name for output")
    args = parser.parse_args()
    
    STOP = args.stop_loss
    SLIP = args.slippage
    NAME = args.name

    print("=" * 70)
    print(f"  PORTFOLIO SIMULATION — Momentum + {STOP}% Stop-Loss")
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

    print(f"\nTest period: {TEST_YEARS}")
    print(f"Candidates: {len(candidates):,}")
    print(f"Stop-loss: -{STOP}% intraday")
    print(f"Slippage: {SLIP}% each way ({SLIP*2:.2f}% round trip)")
    print()

    # ── Identify all picks ──
    print("Identifying picks...")
    all_picks = []
    for date, day_df in candidates.groupby("date"):
        if len(day_df) < TOP_K:
            continue
        picks = day_df.nlargest(TOP_K, "ret_30m")
        all_picks.append(picks)
    
    picks_df = pd.concat(all_picks) if all_picks else pd.DataFrame()
    print(f"Total picks: {len(picks_df)} ({picks_df['date'].nunique()} trading days × {TOP_K})")

    # ── Query intraday lows ──
    print("Querying 1-minute candle data for intraday lows...")
    conn = duckdb.connect(":memory:")
    
    # Process in batches to avoid DuckDB issues
    all_symbols = picks_df["symbol"].unique().tolist()
    print(f"Unique symbols: {len(all_symbols)}")

    # Query each pick individually to get intraday low between 09:45 and 15:15
    sl_data = []  # list of dicts: {symbol, date, open_0945, intraday_low, low_return}
    batch_size = 100
    total = len(picks_df)
    
    for i in range(0, total, batch_size):
        batch = picks_df.iloc[i:i+batch_size]
        for _, pick in batch.iterrows():
            sym = pick["symbol"]
            dt = pick["date"]
            dt_str = str(dt.date()) if hasattr(dt, 'date') else str(dt)[:10]
            
            try:
                row = conn.execute(f"""
                    SELECT 
                        MIN(low) as intraday_low,
                        MIN(open) FILTER (WHERE timestamp = timestamp '{dt_str} 09:45:00') as open_0945
                    FROM read_parquet('{CANDLES_DIR}/symbol={sym}/data.parquet', hive_partitioning=true)
                    WHERE timestamp >= timestamp '{dt_str} 09:45:00'
                      AND timestamp <= timestamp '{dt_str} 15:15:00'
                """).fetchone()
                
                intraday_low = row[0]
                open_0945 = row[1]
                
                if intraday_low is not None and open_0945 is not None and open_0945 > 0:
                    low_return = (intraday_low - open_0945) / open_0945 * 100
                else:
                    low_return = None
            except Exception as e:
                low_return = None
            
            sl_data.append({
                "symbol": sym,
                "date": dt,
                "open_0945": open_0945,
                "intraday_low": intraday_low,
                "low_return": low_return,
            })
        
        if (i + batch_size) % 500 == 0 or i + batch_size >= total:
            print(f"  Queried {min(i + batch_size, total)}/{total} picks...")
    
    sl_df = pd.DataFrame(sl_data)
    
    # ── Apply stop-loss logic ──
    picks_df = picks_df.reset_index(drop=True)
    sl_df = sl_df.reset_index(drop=True)
    
    # Merge stop-loss data with picks
    merged = picks_df.merge(sl_df[["symbol", "date", "low_return", "open_0945", "intraday_low"]], 
                            on=["symbol", "date"], how="left")
    
    # Apply stop-loss
    # For rows where we have intraday data and the low hit -STOP% or worse
    hit_stop = merged["low_return"].notna() & (merged["low_return"] <= -STOP)
    
    merged["stopped_out"] = hit_stop
    # If stopped out: return = -STOP% - slippage
    # If not stopped out: return = actual return_pct - slippage
    portfolio_cost = SLIP * 2  # entry + exit
    
    merged["realized_return"] = np.where(
        hit_stop,
        -STOP - portfolio_cost,
        merged["return_pct"] - portfolio_cost
    )
    
    # Also compute what return would have been WITHOUT stop-loss (for comparison)
    merged["no_stop_return"] = merged["return_pct"] - portfolio_cost
    
    n_stopped = hit_stop.sum()
    print(f"\nStop-loss triggered: {n_stopped}/{len(merged)} ({n_stopped/len(merged)*100:.1f}%)")

    # ── Build daily portfolio returns ──
    daily_with_sl = merged.groupby("date")["realized_return"].mean()
    daily_no_sl = merged.groupby("date")["no_stop_return"].mean()
    
    # ── Compute metrics ──
    metrics_sl = compute_metrics(daily_with_sl, f"Momentum + {STOP}% Stop")
    metrics_no_sl = compute_metrics(daily_no_sl, "Momentum (no stop)")
    
    # Also compute market avg benchmark
    full_test = df[df["year"].isin(TEST_YEARS)]
    market_returns = full_test.groupby("date")["return_pct"].mean()
    market_returns.index = pd.to_datetime(market_returns.index)
    
    # Align to same trading days
    common_days = daily_with_sl.index.intersection(market_returns.index)
    metrics_mkt = compute_metrics(market_returns[common_days], "Market Avg")
    
    # ── Print ──
    for metrics in [metrics_no_sl, metrics_sl, metrics_mkt]:
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
    print(f"  COMPARISON: No Stop vs {STOP}% Stop-Loss")
    print(f"{'='*65}")
    print(f"{'Metric':<25} {'No Stop':<15} {'+{0}% Stop'.format(STOP):<15} {'Market Avg':<15}")
    print("-" * 70)
    
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
            return f"{v:>14}" if isinstance(v, (int, float)) else f"{'N/A':>14}"
        
        line = f"{label:<25}"
        line += fmt(metrics_no_sl.get(key, "N/A"))
        line += f"  "
        line += fmt(metrics_sl.get(key, "N/A"))
        line += f"  "
        line += fmt(metrics_mkt.get(key, "N/A"))
        print(line)
    
    # ── Save ──
    # Save pick-level data with stop-loss info
    picks_out = merged[["date", "symbol", "ret_30m", "return_pct", "low_return", 
                        "stopped_out", "realized_return", "no_stop_return"]]
    picks_out = picks_out.sort_values(["date", "symbol"])
    picks_out_path = POC_DATA / f"picks_with_stop_{STOP}.csv"
    picks_out.to_csv(picks_out_path, index=False)
    print(f"\nPick-level data saved: {picks_out_path}")
    
    # Save report
    report = {
        "strategy": f"Momentum Rule + {STOP}% Stop-Loss",
        "test_years": TEST_YEARS,
        "config": {
            "stop_loss_pct": STOP,
            "slippage_pct": SLIP,
            "top_k": TOP_K,
        },
        "stop_trigger_rate": round(n_stopped / len(merged) * 100, 1),
        "with_stop": metrics_sl,
        "without_stop": metrics_no_sl,
        "market_avg": metrics_mkt,
    }
    report_path = POC_DATA / f"portfolio_sl_{STOP}.json"
    report_path.write_text(json.dumps(report, indent=2))
    print(f"Report saved: {report_path}")
    
    conn.close()


if __name__ == "__main__":
    main()
