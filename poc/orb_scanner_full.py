"""ORB + Scanner — Full Universe (501 stocks, 2023-2025).

Honest ORB simulation:
  1. Opening range: 09:15-09:30
  2. Long breakout: close > range_high
  3. Short breakout: close < range_low
  4. Stop-out check: did intraday price hit opposite side of range?
  5. Close inside range: no trade (ambiguous)
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


def main():
    print("=" * 75)
    print("  ORB + SCANNER — Full Universe (2023-2025)")
    print("  Honest simulation with stop-out detection via intraday H/L")
    print("=" * 75)

    # ── Load features & labels ──
    print("\nLoading features & labels...")
    features = pd.read_parquet(FEATURES_PATH)
    labels = pd.read_parquet(LABELS_PATH)
    features["date"] = pd.to_datetime(features["date"])
    labels["date"] = pd.to_datetime(labels["date"])

    df = features.merge(labels[["symbol", "date", "return_pct"]], on=["symbol", "date"], how="inner")
    df["year"] = df["date"].dt.year
    feats = [f for f in ALL_FEATURES if f in df.columns]
    df = df.dropna(subset=feats)
    df = df[df["year"].isin(TEST_YEARS)]

    candidates = apply_stage1(df)
    candidates["is_scanner_pick"] = True
    df = df.merge(candidates[["symbol", "date", "is_scanner_pick"]], on=["symbol", "date"], how="left")
    df["is_scanner_pick"] = df["is_scanner_pick"].fillna(False)

    scanner_count = df["is_scanner_pick"].sum()
    print(f"Universe: {df['symbol'].nunique()} stocks, {df.shape[0]:,} observations")
    print(f"Scanner picks: {scanner_count:,} ({scanner_count/len(df)*100:.1f}%)")

    # ── Batch query with intraday H/L for stop detection ──
    print("\nBatch querying opening ranges + intraday H/L...")
    start = time.time()

    conn = duckdb.connect(":memory:")
    year_symbols = df.groupby(["symbol", "year"])["date"].first().reset_index()
    year_symbols["year"] = year_symbols["year"].astype(int)

    all_ranges = []
    processed = 0

    for _, row in year_symbols.iterrows():
        sym = row["symbol"]
        yr = row["year"]

        try:
            range_data = conn.execute(f"""
                SELECT 
                    DATE(timestamp) as trade_date,
                    MAX(high) FILTER (WHERE hour(timestamp) = 9 AND minute(timestamp) >= 15 AND minute(timestamp) < 30) as range_high,
                    MIN(low) FILTER (WHERE hour(timestamp) = 9 AND minute(timestamp) >= 15 AND minute(timestamp) < 30) as range_low,
                    MIN(low) FILTER (WHERE hour(timestamp) > 9 OR (hour(timestamp) = 9 AND minute(timestamp) >= 30)) as post_range_low,
                    MAX(high) FILTER (WHERE hour(timestamp) > 9 OR (hour(timestamp) = 9 AND minute(timestamp) >= 30)) as post_range_high,
                    MIN(close) FILTER (WHERE hour(timestamp) = 15 AND minute(timestamp) = 15) as close_1515
                FROM read_parquet('{CANDLES_DIR}/symbol={sym}/data.parquet', hive_partitioning=true)
                WHERE year(timestamp) = {yr}
                  AND hour(timestamp) >= 9 AND hour(timestamp) <= 15
                GROUP BY DATE(timestamp)
                HAVING range_high IS NOT NULL AND range_low IS NOT NULL 
                   AND close_1515 IS NOT NULL AND post_range_low IS NOT NULL
            """).fetchdf()

            if not range_data.empty:
                range_data["symbol"] = sym
                all_ranges.append(range_data)

        except Exception:
            pass

        processed += 1
        if processed % 100 == 0:
            print(f"  Processed {processed}/{len(year_symbols)} symbol-year pairs... ({time.time()-start:.0f}s)")

    ranges_df = pd.concat(all_ranges, ignore_index=True) if all_ranges else pd.DataFrame()
    conn.close()

    elapsed = time.time() - start
    print(f"  Stock-days computed: {len(ranges_df):,} ({elapsed:.0f}s)")

    # ── Merge with scanner picks ──
    ranges_df["date"] = pd.to_datetime(ranges_df["trade_date"])
    ranges_df = ranges_df.rename(columns={"trade_date": "date_str"})
    ranges_df = ranges_df.merge(
        df[["symbol", "date", "is_scanner_pick", "return_pct", "ret_30m"]],
        on=["symbol", "date"], how="left"
    )
    ranges_df["is_scanner_pick"] = ranges_df["is_scanner_pick"].fillna(False)

    # ── Honest ORB simulation with stop-out detection ──
    print("\nSimulating ORB with stop-out detection...")

    def honest_orb(row, slippage_pct):
        """Honest ORB: detect breakout direction + check if stop was hit.
        
        Logic:
          - Long: close > range_high, BUT only if post_range_low > range_low (no stop hit)
          - Short: close < range_low, BUT only if post_range_high < range_high (no stop hit)
          - Stop hit: return = range size loss (entered then stopped at opposite side)
          - Close inside range: no trade
        """
        rh, rl = row["range_high"], row["range_low"]
        c15 = row["close_1515"]
        prl = row["post_range_low"]  # Lowest price AFTER 09:30
        prh = row["post_range_high"]  # Highest price AFTER 09:30

        if pd.isna(rh) or pd.isna(rl) or pd.isna(c15) or pd.isna(prl) or pd.isna(prh):
            return 0.0
        if rh <= rl:
            return 0.0

        slip = slippage_pct / 100  # 0.05%

        if c15 > rh:
            # Long breakout direction
            if prl <= rl:
                # STOP HIT — price dipped to range_low before closing above range_high
                # Entered at range_high, stopped at range_low
                ret = (rl - rh) / rh  # negative: lost the range width
                return round((ret - slip * 2) * 100, 2)
            else:
                # NO STOP — held the long breakout
                ret = (c15 - rh) / rh
                return round((ret - slip * 2) * 100, 2)

        elif c15 < rl:
            # Short breakout direction
            if prh >= rh:
                # STOP HIT — price rose to range_high before closing below range_low
                # Entered at range_low, stopped at range_high
                ret = (rl - rh) / rl  # negative: lost the range width
                return round((ret - slip * 2) * 100, 2)
            else:
                # NO STOP — held the short breakout
                ret = (rl - c15) / rl
                return round((ret - slip * 2) * 100, 2)

        else:
            # Close inside range — no confirmed breakout direction
            return 0.0

    ranges_df["orb_return"] = ranges_df.apply(
        lambda row: honest_orb(row, SLIPPAGE_PCT), axis=1
    )

    # Breakdown stats
    n_breakout = (ranges_df["orb_return"] != 0).sum()
    n_stopped = ((ranges_df["orb_return"] < 0)).sum()
    n_held = ((ranges_df["orb_return"] > 0)).sum()
    n_no_trade = (ranges_df["orb_return"] == 0).sum()
    print(f"  Total stock-days: {len(ranges_df):,}")
    print(f"  Trades (confirmed breakout): {n_breakout:,} ({n_breakout/len(ranges_df)*100:.1f}%)")
    print(f"    Held to close (profit):  {n_held:,}")
    print(f"    Stopped out (loss):      {n_stopped:,}")
    print(f"  No breakout (close inside range): {n_no_trade:,}")

    # ── ORB All Stocks ──
    orb_all = ranges_df[ranges_df["orb_return"] != 0].copy()
    orb_all_daily = orb_all.groupby("date")["orb_return"].mean()

    # ── ORB Scanner Picks Only ──
    orb_scanner = ranges_df[(ranges_df["is_scanner_pick"]) & (ranges_df["orb_return"] != 0)].copy()
    orb_scanner_daily = orb_scanner.groupby("date")["orb_return"].mean()

    # ── Scanner Only Baseline ──
    scanner_picks = df[df["is_scanner_pick"]].copy()
    scanner_daily = []
    for date, day_df in scanner_picks.groupby("date"):
        if len(day_df) >= TOP_K:
            top3 = day_df.nlargest(TOP_K, "ret_30m")
            scanner_daily.append(top3["return_pct"].mean())
        elif len(day_df) > 0:
            scanner_daily.append(day_df["return_pct"].mean())
    scan_daily_s = pd.Series(scanner_daily)
    scan_cost = SLIPPAGE_PCT * 2
    scan_daily = scan_daily_s - scan_cost

    # ── Print Results ──
    print(f"\n{'═'*75}")
    print(f"  RESULTS — Full Universe, 2023-2025")
    print(f"{'═'*75}")

    for label, data in [
        ("ORB (all stocks)", orb_all_daily),
        ("ORB (scanner picks)", orb_scanner_daily),
        ("Scanner only (top 3 by ret_30m)", scan_daily),
    ]:
        if len(data) < 5:
            print(f"\n  {label}: Insufficient data ({len(data)} days)")
            continue
        metrics = compute_metrics(data, label)
        print(f"\n  {'─'*65}")
        print(f"  {metrics['name']}")
        print(f"  {'─'*65}")
        print(f"  Total return:  {metrics['total_return']:>+8.2f}%  CAGR: {metrics['cagr']:>+7.2f}%")
        print(f"  Sharpe:        {metrics['sharpe']:>8.2f}      Sortino: {metrics['sortino']:>7.2f}")
        print(f"  Max DD:        {metrics['max_dd']:>8.2f}%     Calmar: {metrics['calmar']:>7.2f}")
        print(f"  Win rate:      {metrics['win_rate']:>7.1f}%      PF: {metrics['profit_factor']:>8.2f}")
        print(f"  Avg win/loss:  {metrics['avg_win']:.2f}% / {metrics['avg_loss']:.2f}%")
        print(f"  Days:          {metrics['n_days']}")

    # ── Summary Table ──
    print(f"\n{'═'*75}")
    print(f"  HEAD-TO-HEAD COMPARISON")
    print(f"{'═'*75}")
    print(f"{'Metric':<30} {'ORB All':<15} {'ORB Scanner':<15} {'Scanner Only':<15}")
    print("-" * 75)

    m_orb_all = compute_metrics(orb_all_daily, "ORB All")
    m_orb_scanner = compute_metrics(orb_scanner_daily, "ORB Scanner")
    m_scanner = compute_metrics(scan_daily, "Scanner Only")

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
        print(f"{display:<30} {fmt(m_orb_all):<15} {fmt(m_orb_scanner):<15} {fmt(m_scanner):<15}")

    # ── ORB Scanner Trade Stats ──
    if not orb_scanner.empty:
        print(f"\n{'═'*75}")
        print(f"  ORB SCANNER TRADE STATS")
        print(f"{'═'*75}")
        print(f"  Total trades:     {len(orb_scanner)}")
        print(f"  Trading days:     {orb_scanner['date'].nunique()}")
        print(f"  Avg trades/day:   {len(orb_scanner) / orb_scanner['date'].nunique():.1f}")
        print(f"  Stopped out:      {(orb_scanner['orb_return'] < 0).sum()} ({(orb_scanner['orb_return'] < 0).mean()*100:.0f}%)")
        print(f"  Held to close:    {(orb_scanner['orb_return'] > 0).sum()} ({(orb_scanner['orb_return'] > 0).mean()*100:.0f}%)")
        print(f"  Return range:     [{orb_scanner['orb_return'].min():+.2f}%, {orb_scanner['orb_return'].max():+.2f}%]")

    # ── Save ──
    report = {
        "config": {"slippage_pct": SLIPPAGE_PCT, "test_years": TEST_YEARS,
                   "scanner_filter_pct": scanner_count/len(df)*100},
        "orb_all": m_orb_all,
        "orb_scanner": m_orb_scanner,
        "scanner_only": m_scanner,
    }
    report_path = POC_DATA / "orb_scanner_full_universe.json"
    report_path.write_text(json.dumps(report, indent=2))
    print(f"\nReport saved: {report_path}")


if __name__ == "__main__":
    main()
