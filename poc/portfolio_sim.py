"""Portfolio Simulation: Momentum Rule (Stage 1 → top 3 by ret_30m).

Simulates a daily intraday strategy:
  - Stage 1: ret_30m > 1%, rvol > 1.5, beats_nifty_30m == 1
  - Pick top 3 stocks by ret_30m from candidates
  - Equal weight (33.3% each)
  - Entry 09:45, Exit 15:15
  - Slippage 0.05% each way per leg
  - Compare vs NIFTY benchmark
"""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import FEATURES_PATH, LABELS_PATH, POC_DATA
import numpy as np
import pandas as pd

# ── Configuration ──
SLIPPAGE_PCT = 0.05         # per leg each way (entry + exit = 0.10% per leg)
TOP_K = 3                    # picks per day
START_CAPITAL = 10_00_000    # ₹10 lakhs
TEST_YEARS = [2023, 2024, 2025]

# Stage 1 rules (best approach from all_approaches.py)
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


def compute_metrics(daily_returns: pd.Series, nifty_returns: pd.Series | None, name: str) -> dict:
    """Compute comprehensive portfolio metrics from daily returns series."""
    daily = daily_returns.dropna().values
    if len(daily) < 5:
        return {"error": "Insufficient data", "name": name}

    n_days = len(daily)
    mean_daily = np.mean(daily)
    std_daily = np.std(daily)

    # Sharpe (annualized, assuming 252 trading days)
    sharpe = (mean_daily / std_daily) * np.sqrt(252) if std_daily > 0 else 0.0

    # Sortino (downside deviation)
    downside = daily[daily < 0]
    downside_std = np.std(downside) if len(downside) > 1 else std_daily
    sortino = (mean_daily / downside_std) * np.sqrt(252) if downside_std > 0 else 0.0

    # Cumulative returns & drawdown
    cumulative = np.cumprod(1 + daily / 100)
    total_return_pct = (cumulative[-1] - 1) * 100

    # CAGR
    years = n_days / 252
    cagr = ((cumulative[-1]) ** (1 / years) - 1) * 100 if years > 0 else 0.0

    # Max drawdown
    peak = np.maximum.accumulate(cumulative)
    dd = (peak - cumulative) / peak * 100
    max_dd = np.max(dd)

    # Calmar ratio
    calmar = cagr / max_dd if max_dd > 0 else 0.0

    # Win/loss stats
    wins = daily[daily > 0]
    losses = daily[daily < 0]
    win_rate = len(wins) / n_days * 100
    avg_win = np.mean(wins) if len(wins) > 0 else 0.0
    avg_loss = abs(np.mean(losses)) if len(losses) > 0 else 0.0
    avg_win_loss = avg_win / avg_loss if avg_loss > 0 else 0.0

    # Profit factor
    gross_profit = np.sum(wins) if len(wins) > 0 else 0
    gross_loss = abs(np.sum(losses)) if len(losses) > 0 else 0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0.0

    # Max consecutive wins/losses
    runs = np.diff(np.concatenate(([0], (daily > 0).astype(int), [0])))
    run_starts = np.where(runs == 1)[0]
    run_ends = np.where(runs == -1)[0]
    run_lengths = run_ends - run_starts
    max_consec_wins = int(np.max(run_lengths)) if len(run_lengths) > 0 else 0
    runs_loss = np.diff(np.concatenate(([0], (daily < 0).astype(int), [0])))
    loss_starts = np.where(runs_loss == 1)[0]
    loss_ends = np.where(runs_loss == -1)[0]
    loss_lengths = loss_ends - loss_starts
    max_consec_losses = int(np.max(loss_lengths)) if len(loss_lengths) > 0 else 0

    # Volatility (annualized)
    ann_vol = std_daily * np.sqrt(252)

    # Benchmark comparison (if available)
    alpha = beta = None
    if nifty_returns is not None:
        nifty = nifty_returns.dropna()
        common_idx = daily_returns.dropna().index.intersection(nifty.index)
        if len(common_idx) > 20:
            strat_common = daily_returns[common_idx].values
            nifty_common = nifty[common_idx].values
            # Beta
            cov = np.cov(strat_common, nifty_common)
            beta = cov[0, 1] / cov[1, 1] if cov[1, 1] > 0 else 0
            # Alpha (annualized)
            rf_daily = 0.0  # Assume 0% risk-free for intraday
            alpha = (np.mean(strat_common) - beta * np.mean(nifty_common)) * 252
            # Correlation
            corr = np.corrcoef(strat_common, nifty_common)[0, 1]
        else:
            alpha = beta = corr = None

    result = {
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
    if alpha is not None:
        result["alpha"] = round(alpha, 2)
        result["beta"] = round(beta, 2)
        result["correlation"] = round(corr, 2)
    return result


def apply_stage1(df: pd.DataFrame) -> pd.DataFrame:
    candidates = df.copy()
    for _, (col, threshold) in STAGE1_RULES.items():
        if threshold is not None:
            candidates = candidates[candidates[col] > threshold]
        else:
            candidates = candidates[candidates[col] == 1]
    return candidates


def main():
    print("=" * 70)
    print("  PORTFOLIO SIMULATION — Momentum Rule (Stage 1 → top 3 by ret_30m)")
    print("=" * 70)

    # ── Load data ──
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
    print(f"Full universe: {df[df['year'].isin(TEST_YEARS)].shape[0]:,} rows")
    print(f"Stage 1 candidates: {candidates.shape[0]:,}")
    print(f"Candidates/day: ~{candidates.shape[0] / max(candidates['date'].nunique(),1):.0f}")
    print(f"Slippage: {SLIPPAGE_PCT:.2f}% each way ({SLIPPAGE_PCT*2:.2f}% round-trip per leg)")
    print()

    # ── Daily portfolio picks ──
    print(f"{'Date':<14} {'Picks':<30} {'Avg Ret':<9} {'1st Ret':<9} {'Best Ret':<9}")
    print("-" * 70)

    portfolio_returns = []  # Daily portfolio returns
    pick_details = []       # Per-pick details

    for date, day_df in candidates.groupby("date"):
        if len(day_df) < TOP_K:
            continue

        # Pick top K by morning momentum
        picks = day_df.nlargest(TOP_K, "ret_30m")

        # Portfolio return = equal-weight average - slippage
        raw_returns = picks["return_pct"].values
        slippage_cost = SLIPPAGE_PCT  # 0.05% entry + 0.05% exit = we take 0.05% here
        # Actually: each of 3 positions has 0.10% round-trip cost, but they're equally weighted
        # So total portfolio cost = 0.10% per day (0.10% of capital)
        # Entry cost: 0.05% on each of 3 positions at 33.3% weight = 0.05% of portfolio value
        # Exit cost: same 0.05% = 0.10% total
        portfolio_cost = SLIPPAGE_PCT * 2  # 0.10% per day

        portfolio_ret = np.mean(raw_returns) - portfolio_cost
        portfolio_returns.append({"date": date, "portfolio_return": portfolio_ret})

        for i, (_, pick) in enumerate(picks.iterrows()):
            pick_details.append({
                "date": date,
                "symbol": pick["symbol"],
                "ret_30m": pick["ret_30m"],
                "return_pct": pick["return_pct"],
                "rvol": pick["rvol"],
                "is_top3": int(pick["return_pct"] >= day_df.nlargest(3, "return_pct")["return_pct"].min()),
            })

        if len(portfolio_returns) <= 5 and date.year == TEST_YEARS[0]:
            print(f"{str(date.date()):<14} {picks['symbol'].tolist()!s:<30} {np.mean(raw_returns):<+9.2f}% {raw_returns[0]:<+9.2f}% {max(raw_returns):<+9.2f}%")

    # Skip remaining sample print
    n_days = len(portfolio_returns)
    print(f"  ... ({n_days - 5} more days)                     ") if n_days > 5 else ""

    # ── Build daily return series ──
    pf_df = pd.DataFrame(portfolio_returns).set_index("date")
    pf_df.index = pd.to_datetime(pf_df.index)

    # ── NIFTY benchmark ──
    # Compute market benchmark: equal-weight average return of all stocks each day
    print("\nComputing benchmarks...")
    full_test = df[df["year"].isin(TEST_YEARS)]
    market_returns = full_test.groupby("date")["return_pct"].mean()
    market_returns.index = pd.to_datetime(market_returns.index)

    # Also try to find NIFTY-specific benchmark from features
    nifty_daily = full_test[["date", "nifty_daily_ret_prev"]].drop_duplicates().set_index("date")
    nifty_daily.index = pd.to_datetime(nifty_daily.index)
    # nifty_daily_ret_prev is yesterday's full-day NIFTY return — not ideal for intraday comparison
    # Better: use nifty_ret_30m as a partial-day benchmark
    nifty_morning = full_test.groupby("date")["nifty_ret_30m"].first()
    nifty_morning.index = pd.to_datetime(nifty_morning.index)

    # ── Compute metrics ──
    print("\n" + "=" * 70)
    print("  PERFORMANCE METRICS")
    print("=" * 70)

    portfolio_series = pf_df["portfolio_return"]

    metrics_mom = compute_metrics(portfolio_series, None, "Momentum Rule")
    metrics_mkt = compute_metrics(market_returns, None, "Market Avg")
    metrics_nifty_morning = compute_metrics(nifty_morning, None, "NIFTY (09:15→09:45)")

    # Compare vs market
    metrics_mom_vs_mkt = compute_metrics(
        portfolio_series, market_returns, "Momentum vs Market"
    )

    # ── Print results ──
    for metrics in [metrics_mom, metrics_mkt, metrics_nifty_morning, metrics_mom_vs_mkt]:
        if "error" in metrics:
            print(f"\n{metrics['name']}: {metrics['error']}")
            continue

        print(f"\n{'─'*70}")
        print(f"  {metrics['name']}")
        print(f"{'─'*70}")
        print(f"  Trading days:           {metrics['n_trading_days']}")
        print(f"  Total return:           {metrics['total_return_pct']:>+8.2f}%")
        print(f"  CAGR:                   {metrics['cagr_pct']:>+8.2f}%")
        print(f"  Annual volatility:      {metrics['ann_volatility_pct']:>8.2f}%")
        print(f"  Sharpe ratio:           {metrics['sharpe_ratio']:>8.2f}")
        print(f"  Sortino ratio:          {metrics['sortino_ratio']:>8.2f}")
        print(f"  Calmar ratio:           {metrics['calmar_ratio']:>8.2f}")
        print(f"  Max drawdown:           {metrics['max_drawdown_pct']:>8.2f}%")
        print(f"  Win rate:               {metrics['win_rate_pct']:>7.1f}%")
        print(f"  Avg win / Avg loss:     {metrics['avg_win_pct']:.2f}% / {metrics['avg_loss_pct']:.2f}%")
        print(f"  Win/Loss ratio:         {metrics['avg_win_loss_ratio']:>8.2f}")
        print(f"  Profit factor:          {metrics['profit_factor']:>8.2f}")
        print(f"  Max consecutive wins:   {metrics['max_consecutive_wins']:>4d}")
        print(f"  Max consecutive losses: {metrics['max_consecutive_losses']:>4d}")

        # Show benchmark comparison if available
        if "alpha" in metrics and metrics["alpha"] is not None:
            print(f"  Alpha (annualized):     {metrics['alpha']:>+8.2f}%")

    # ── Comparison Summary ──
    print(f"\n{'='*70}")
    print(f"  HEAD-TO-HEAD COMPARISON (3 years: 2023-2025)")
    print(f"{'='*70}")
    print(f"{'Metric':<30} {'Momentum':<15} {'Market Avg':<15} {'NIFTY Morn':<15}")
    print("-" * 75)

    rows = [
        ("Total Return %", "total_return_pct"),
        ("CAGR %", "cagr_pct"),
        ("Sharpe", "sharpe_ratio"),
        ("Sortino", "sortino_ratio"),
        ("Calmar", "calmar_ratio"),
        ("Max DD %", "max_drawdown_pct"),
        ("Win Rate %", "win_rate_pct"),
        ("Profit Factor", "profit_factor"),
    ]

    for label, key in rows:
        mom = metrics_mom.get(key, "N/A")
        mkt = metrics_mkt.get(key, "N/A")
        nif = metrics_nifty_morning.get(key, "N/A")

        def fmt(v):
            if isinstance(v, (int, float)):
                return f"{v:>14}"
            return f"{'>14'}"  # shouldn't happen

        print(f"{label:<30} {fmt(mom):<15} {fmt(mkt):<15} {fmt(nif):<15}")

    # ── Equity curve (save as CSV for later plotting) ──
    pf_df["momentum_cum"] = START_CAPITAL * (1 + pf_df["portfolio_return"] / 100).cumprod()
    # Market cum
    mkt_align = market_returns.reindex(pf_df.index).fillna(0)
    pf_df["market_cum"] = START_CAPITAL * (1 + mkt_align / 100).cumprod()

    # Save equity curve
    equity_path = POC_DATA / "portfolio_equity_curve.csv"
    pf_df[["portfolio_return", "market_cum"]].to_csv(equity_path)
    print(f"\nEquity curve saved: {equity_path}")

    # ── Save report ──
    report = {
        "strategy": "Momentum Rule (Stage 1 → top 3 by ret_30m)",
        "test_years": TEST_YEARS,
        "config": {
            "slippage_pct": SLIPPAGE_PCT,
            "top_k": TOP_K,
            "stage1_rules": list(STAGE1_RULES.keys()),
        },
        "momentum_rule": metrics_mom,
        "market_avg": metrics_mkt,
        "nifty_morning": metrics_nifty_morning,
        "momentum_vs_market": metrics_mom_vs_mkt,
    }
    report_path = POC_DATA / "portfolio_report.json"
    report_path.write_text(json.dumps(report, indent=2))
    print(f"Report saved: {report_path}")


if __name__ == "__main__":
    main()
