"""ORB + Scanner Combo — Compare: ORB (all stocks) vs ORB (scanner picks) vs Scanner only.

Tests whether the momentum scanner improves ORB breakout quality by filtering
to only stocks with morning momentum > 1%, volume surge, beating NIFTY.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import FEATURES_PATH, LABELS_PATH, POC_DATA, PROJECT_ROOT
import numpy as np
import pandas as pd
import duckdb

SLIPPAGE_PCT = 0.05
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


def apply_stage1(df: pd.DataFrame) -> pd.DataFrame:
    candidates = df.copy()
    for _, (col, threshold) in STAGE1_RULES.items():
        if threshold is not None:
            candidates = candidates[candidates[col] > threshold]
        else:
            candidates = candidates[candidates[col] == 1]
    return candidates


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
    years = n / 252
    cagr = ((cum[-1]) ** (1 / years) - 1) * 100 if years > 0 else 0.0
    peak = np.maximum.accumulate(cum)
    mdd = np.max((peak - cum) / peak * 100)
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
        "max_dd": round(mdd, 2),
        "win_rate": round(wr, 1), "avg_win": round(aw, 2),
        "avg_loss": round(al, 2), "profit_factor": round(pf, 2),
    }


def main():
    print("=" * 75)
    print("  ORB + SCANNER COMBO — Side-by-Side Comparison")
    print("=" * 75)

    TEST_STOCKS = ['RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'ICICIBANK',
                   'SBIN', 'BHARTIARTL', 'KOTAKBANK', 'ITC', 'LT']

    # ── Load features & labels — identify scanner picks ──
    features = pd.read_parquet(FEATURES_PATH)
    labels = pd.read_parquet(LABELS_PATH)
    features["date"] = pd.to_datetime(features["date"])
    labels["date"] = pd.to_datetime(labels["date"])

    df = features.merge(labels[["symbol", "date", "return_pct"]], on=["symbol", "date"], how="inner")
    feats = [f for f in ALL_FEATURES if f in df.columns]
    df = df.dropna(subset=feats)
    df = df[df["symbol"].isin(TEST_STOCKS)]
    df = df[(df["date"] >= "2023-01-01") & (df["date"] < "2024-01-01")]

    candidates = apply_stage1(df)
    candidates["is_scanner_pick"] = True
    df = df.merge(candidates[["symbol", "date", "is_scanner_pick"]], on=["symbol", "date"], how="left")
    df["is_scanner_pick"] = df["is_scanner_pick"].fillna(False)

    print(f"\nTest period: 2023 (full year)")
    print(f"Stocks: {', '.join(TEST_STOCKS)}")
    print(f"Total observations: {len(df):,}")
    print(f"Scanner picks: {candidates.shape[0]:,} ({candidates.shape[0]/len(df)*100:.1f}%)")
    print()

    # ── Query candle data ──
    conn = duckdb.connect(":memory:")

    all_trades = []

    for sym in TEST_STOCKS:
        try:
            candles = conn.execute(f"""
                SELECT timestamp, open, high, low, close
                FROM read_parquet('{CANDLES_DIR}/symbol={sym}/data.parquet', hive_partitioning=true)
                WHERE timestamp >= '2023-01-01 09:15:00'
                  AND timestamp <= '2023-12-31 15:15:00'
                ORDER BY timestamp
            """).fetchdf()
        except Exception:
            print(f"  Warning: no data for {sym}")
            continue

        candles["date"] = candles["timestamp"].dt.date

        for date, day_df in candles.groupby("date"):
            day_df = day_df.reset_index(drop=True)

            # Check if this stock was a scanner pick today
            date_dt = pd.Timestamp(date)
            scanner_match = df[(df["symbol"] == sym) & (df["date"].dt.date == date)]
            is_scanner = scanner_match["is_scanner_pick"].iloc[0] if len(scanner_match) > 0 else False

            # Opening range: 09:15-09:30
            range_mask = (day_df["timestamp"].dt.hour == 9) & (day_df["timestamp"].dt.minute < 30)
            range_candles = day_df[range_mask]
            if len(range_candles) == 0:
                continue

            range_high = range_candles["high"].max()
            range_low = range_candles["low"].min()

            # Post-range
            early_mask = (day_df["timestamp"].dt.hour == 9) & (day_df["timestamp"].dt.minute >= 30)
            post_mask = early_mask | (day_df["timestamp"].dt.hour > 9)
            post_range = day_df[post_mask].copy()
            if post_range.empty:
                continue

            close_1515_mask = (post_range["timestamp"].dt.hour == 15) & (post_range["timestamp"].dt.minute == 15)
            close_1515 = post_range[close_1515_mask]["close"].iloc[0] if close_1515_mask.any() else post_range.iloc[-1]["close"]

            # Early breakout detection (5 min after range)
            early_break_mask = (post_range["timestamp"].dt.hour == 9) & (post_range["timestamp"].dt.minute < 35)
            early_candles = post_range[early_break_mask]

            broke_high = early_candles["high"].max() > range_high if not early_candles.empty else post_range["high"].max() > range_high
            broke_low = early_candles["low"].min() < range_low if not early_candles.empty else post_range["low"].min() < range_low

            # Entry: at range boundary + slippage
            if broke_high:
                entry = range_high * (1 + SLIPPAGE_PCT / 100)
                exit_px = close_1515 * (1 - SLIPPAGE_PCT / 100)
                ret = (exit_px - entry) / entry * 100
                stop_hit = post_range["low"].min() <= range_low
                all_trades.append({
                    "symbol": sym, "date": date, "direction": "long",
                    "return_pct": round(ret, 2),
                    "range_size": round(range_high - range_low, 2),
                    "stop_hit": stop_hit,
                    "is_scanner_pick": is_scanner,
                })

            if broke_low:
                entry = range_low * (1 - SLIPPAGE_PCT / 100)  # sell at low
                exit_px = close_1515 * (1 + SLIPPAGE_PCT / 100)  # buy back
                ret = (entry - exit_px) / entry * 100
                stop_hit = post_range["high"].max() >= range_high
                all_trades.append({
                    "symbol": sym, "date": date, "direction": "short",
                    "return_pct": round(ret, 2),
                    "range_size": round(range_high - range_low, 2),
                    "stop_hit": stop_hit,
                    "is_scanner_pick": is_scanner,
                })

    conn.close()

    trades = pd.DataFrame(all_trades)
    print(f"Total trades: {len(trades)}")
    print()

    # ── Split: ORB on ALL vs ORB on SCANNER only ──
    orb_all = trades
    orb_scanner = trades[trades["is_scanner_pick"] == True]

    # Scanner-only baseline: pick top 3 by ret_30m each day from scanner picks
    scanner_picks = candidates.copy()
    scanner_picks = scanner_picks[scanner_picks["symbol"].isin(TEST_STOCKS)]
    scanner_daily = []
    for date, day_df in scanner_picks.groupby("date"):
        if len(day_df) >= 3:
            top3 = day_df.nlargest(3, "ret_30m")
            scanner_daily.append(top3["return_pct"].mean())
        elif len(day_df) > 0:
            scanner_daily.append(day_df["return_pct"].mean())
    scan_daily_s = pd.Series(scanner_daily)
    scan_cost = SLIPPAGE_PCT * 2
    scan_daily = scan_daily_s - scan_cost

    # Print comparison
    for label, data in [("ORB on ALL stocks", orb_all), ("ORB on SCANNER picks only", orb_scanner)]:
        print(f"\n{'─'*65}")
        print(f"  {label}")
        print(f"{'─'*65}")

        if len(data) == 0:
            print("  No trades.")
            continue

        n_long = (data["direction"] == "long").sum()
        n_short = (data["direction"] == "short").sum()
        stop_rate = data["stop_hit"].mean() * 100

        print(f"  Trades: {len(data)} ({n_long} long, {n_short} short)")
        print(f"  Stop hit: {stop_rate:.0f}%")
        print(f"  Avg return: {data['return_pct'].mean():+.2f}%")
        print(f"  Win rate: {(data['return_pct']>0).mean()*100:.1f}%")
        print(f"  Avg range size: {data['range_size'].mean():.2f}")

        # Stopped vs Held
        stopped = data[data["stop_hit"]]
        held = data[~data["stop_hit"]]
        print(f"  Stopped trades: {len(stopped)} avg ret: {stopped['return_pct'].mean():+.2f}%")
        print(f"  Held to close:  {len(held)} avg ret: {held['return_pct'].mean():+.2f}%")

    # ── Daily portfolio metrics ──
    print(f"\n{'='*65}")
    print(f"  PORTFOLIO COMPARISON")
    print(f"{'='*65}")
    print(f"{'Metric':<35} {'ORB All':<15} {'ORB Scanner':<15} {'ScannerOnly':<15}")
    print("-" * 80)

    for data, label, key in [
        (orb_all, "ORB All", None),
        (orb_scanner, "ORB Scanner", None),
        (scan_daily, "Scanner Only", None),
    ]:
        if isinstance(data, pd.Series):
            daily_ret = data
        else:
            daily_ret = data.groupby("date")["return_pct"].mean()

        metrics = compute_metrics(daily_ret, label)

        if key is None:
            key = label

    # Manual table
    def orb_daily(data):
        return data.groupby("date")["return_pct"].mean()

    m_all = compute_metrics(orb_daily(orb_all), "ORB All")
    m_scanner_orb = compute_metrics(orb_daily(orb_scanner), "ORB Scanner")
    m_scanner_only = compute_metrics(scan_daily, "Scanner Only")

    for metric_key, display in [
        ("total_return", "Total Return %"),
        ("sharpe", "Sharpe"),
        ("sortino", "Sortino"),
        ("max_dd", "Max DD %"),
        ("win_rate", "Win Rate %"),
        ("profit_factor", "Profit Factor"),
    ]:
        def fmt(d):
            v = d.get(metric_key, "N/A")
            return f"{v:>14}" if isinstance(v, (int, float)) else f"{'N/A':>14}"

        print(f"{display:<35} {fmt(m_all):<15} {fmt(m_scanner_orb):<15} {fmt(m_scanner_only):<15}")

    # ── Key insight: does filtering improve ORB? ──
    print(f"\n{'='*65}")
    print(f"  VERDICT")
    print(f"{'='*65}")

    orb_all_avg = orb_all["return_pct"].mean()
    orb_scanner_avg = orb_scanner["return_pct"].mean()
    orb_scanner_win = (orb_scanner["return_pct"] > 0).mean() * 100
    orb_all_win = (orb_all["return_pct"] > 0).mean() * 100

    print(f"  ORB (all):       avg ret={orb_all_avg:+.2f}%, win rate={orb_all_win:.0f}%")
    print(f"  ORB (scanner):   avg ret={orb_scanner_avg:+.2f}%, win rate={orb_scanner_win:.0f}%")
    print(f"  Scanner only:    avg ret={scan_daily.mean():+.2f}%")

    improvement = (orb_scanner_avg - orb_all_avg) / abs(orb_all_avg) * 100 if orb_all_avg != 0 else 0
    print(f"\n  Scanner filtering {'IMPROVES' if orb_scanner_avg > orb_all_avg else 'HURTS'} ORB by {improvement:.0f}%")

    # ── Save ──
    report = {
        "config": {"slippage_pct": SLIPPAGE_PCT, "test_year": 2023, "stocks": TEST_STOCKS},
        "orb_all": {"n_trades": len(orb_all), **m_all},
        "orb_scanner": {"n_trades": len(orb_scanner), **m_scanner_orb},
        "scanner_only": {"n_days": len(scan_daily), **m_scanner_only},
        "verdict": f"Scanner filtering {'improved' if orb_scanner_avg > orb_all_avg else 'hurt'} ORB avg return from {orb_all_avg:+.2f}% to {orb_scanner_avg:+.2f}%",
    }
    (POC_DATA / "orb_scanner_combo.json").write_text(json.dumps(report, indent=2))
    print(f"\nReport saved.")

    # Also print the 2x2: ORB vs Scanner
    print(f"\n{'─'*65}")
    print("  EXPANDED VIEW: Stopped vs Held, ALL vs SCANNER")
    print(f"{'─'*65}")
    for label, data in [("ALL stocks", orb_all), ("Scanner picks", orb_scanner)]:
        stopped = data[data["stop_hit"]]
        held = data[~data["stop_hit"]]
        print(f"\n  {label}:")
        print(f"    Stopped ({len(stopped)} trades): win_rate={(stopped['return_pct']>0).mean()*100:.0f}%, avg={stopped['return_pct'].mean():+.2f}%")
        print(f"    Held   ({len(held)} trades): win_rate={(held['return_pct']>0).mean()*100:.0f}%, avg={held['return_pct'].mean():+.2f}%")


if __name__ == "__main__":
    main()
