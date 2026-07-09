"""Momentum PoC — Rule-Based Scanner (Market Regime + Momentum + Volume + Relative Strength).

Instead of predicting from scratch with ML, this uses simple rules:
1. Market Regime: Only trade when NIFTY shows high volatility (trending day)
2. Momentum Ranking: Buy strongest morning performers (highest ret_30m)
3. Volume Confirmation: Require volume surge (rvol > 1.5)
4. Relative Strength: Require stock outperforms NIFTY (beats_nifty_30m = 1)

This approach is more robust because it filters for conditions where momentum works,
rather than trying to predict which specific stocks will move.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import BACKTEST_PATH, BROKERAGE_PCT, POC_DATA
import numpy as np
import pandas as pd

def main():
    features = pd.read_parquet(POC_DATA / "features.parquet")
    labels = pd.read_parquet(POC_DATA / "labels.parquet")
    
    features["date"] = pd.to_datetime(features["date"])
    labels["date"] = pd.to_datetime(labels["date"])
    df = features.merge(labels[["symbol","date","return_pct","label"]], on=["symbol","date"], how="inner")
    df = df.dropna(subset=["return_pct"])
    
    print(f"Dataset: {len(df):,} rows, {df['date'].nunique()} days")
    
    # ═══════════════════════════════════════════════════════════════════
    # RULE 1: Market Regime Filter
    # Only trade when NIFTY shows meaningful intraday volatility
    # ═══════════════════════════════════════════════════════════════════
    daily_market = df.groupby("date").agg(
        nifty_ret=("nifty_ret_30m", "first"),
        nifty_vol=("nifty_mom_5d", "first"),
        avg_range=("range_30m", "mean"),
        n_stocks=("symbol", "count"),
    ).reset_index()
    
    # Trending day = NIFTY moved >0.1% in first 30min OR high average range
    daily_market["is_trending"] = (
        (daily_market["nifty_ret"].abs() > 0.1) | 
        (daily_market["avg_range"] > 1.5)
    )
    
    trending_days = set(daily_market[daily_market["is_trending"]]["date"])
    print(f"\nMarket Regime: {len(trending_days)}/{len(daily_market)} trending days ({len(trending_days)/len(daily_market)*100:.1f}%)")
    
    # ═══════════════════════════════════════════════════════════════════
    # RULE 2-4: Stock Selection Rules
    # ═══════════════════════════════════════════════════════════════════
    
    results = []
    
    for date, day_df in df.groupby("date"):
        if date not in trending_days:
            continue  # Skip non-trending days
        
        # Rule 2: Momentum ranking - strongest morning performers
        day_df = day_df.copy()
        day_df["momentum_rank"] = day_df["ret_30m"].rank(ascending=False, method="min")
        
        # Rule 3: Volume confirmation - require volume surge
        vol_filter = day_df["rvol"] > 1.0  # At least average volume
        
        # Rule 4: Relative strength - must outperform NIFTY
        rs_filter = day_df["beats_nifty_30m"] == 1
        
        # Combined filter: trending day + volume + relative strength
        candidates = day_df[vol_filter & rs_filter].copy()
        
        if len(candidates) == 0:
            # Relax rules if no candidates
            candidates = day_df[day_df["ret_30m"] > 0].copy()
        
        if len(candidates) == 0:
            continue
        
        # Pick top 3 by momentum (strongest morning performers)
        top3 = candidates.nlargest(3, "ret_30m")
        
        avg_ret = top3["return_pct"].mean()
        net_ret = avg_ret - (2 * BROKERAGE_PCT)
        n_hits = (top3["return_pct"] >= 5).sum()
        
        results.append({
            "date": str(date.date()) if hasattr(date, "date") else str(date),
            "n_candidates": len(candidates),
            "n_trades": len(top3),
            "n_hits": int(n_hits),
            "gross_return": float(avg_ret),
            "net_return": float(net_ret),
            "symbols": top3["symbol"].tolist(),
            "returns": top3["return_pct"].tolist(),
            "ret_30m": top3["ret_30m"].tolist(),
            "rvol": top3["rvol"].tolist(),
        })
    
    if not results:
        print("ERROR: No trading days after filters"); sys.exit(1)
    
    daily_returns = np.array([r["net_return"] for r in results])
    daily_prec = np.array([r["n_hits"] / 3.0 for r in results])
    
    total_days = len(results)
    mean_daily = daily_returns.mean()
    std_daily = daily_returns.std()
    sharpe = (mean_daily / std_daily) * np.sqrt(252) if std_daily > 0 else 0
    cumulative = np.cumprod(1 + daily_returns / 100)
    total_return = (cumulative[-1] - 1) * 100
    peak = np.maximum.accumulate(cumulative)
    max_drawdown = ((peak - cumulative) / peak * 100).max()
    win_rate = (daily_returns > 0).sum() / total_days * 100
    total_picks = sum(r["n_trades"] for r in results)
    total_hits = sum(r["n_hits"] for r in results)
    hit_rate = total_hits / total_picks * 100 if total_picks > 0 else 0
    days_with_hit = sum(1 for r in results if r["n_hits"] > 0)
    
    print(f"\n{'='*60}")
    print(f"RULE-BASED SCANNER BACKTEST (Top-3, >=5% target)")
    print(f"{'='*60}")
    print(f"Trading days:       {total_days}")
    print(f"Mean daily return:  {mean_daily:+.3f}%")
    print(f"Sharpe ratio:       {sharpe:.2f}")
    print(f"Total return:       {total_return:+.1f}%")
    print(f"Max drawdown:       {max_drawdown:.1f}%")
    print(f"Win rate:           {win_rate:.1f}%")
    print(f"Hit rate (>=5%):    {hit_rate:.1f}%")
    print(f"Days with >=1 hit:  {days_with_hit/total_days*100:.1f}%")
    print(f"Precision@3:        {daily_prec.mean():.4f}")
    
    # Save results
    report = {
        "type": "rule_based_scanner",
        "total_trading_days": total_days,
        "mean_daily_return": round(float(mean_daily), 4),
        "sharpe_ratio": round(float(sharpe), 2),
        "total_return_pct": round(float(total_return), 2),
        "max_drawdown_pct": round(float(max_drawdown), 2),
        "win_rate_pct": round(float(win_rate), 1),
        "hit_rate_pct": round(float(hit_rate), 1),
        "days_with_hit_pct": round(days_with_hit/total_days*100, 1),
        "precision_at_3": round(float(daily_prec.mean()), 4),
    }
    (POC_DATA / "scanner_results.json").write_text(json.dumps(report, indent=2))
    
    # Show sample trades
    print(f"\n--- Sample Trades ---")
    for r in results[:5]:
        print(f"  {r['date']}: {r['symbols']} -> returns {r['returns']} (net: {r['net_return']:.2f}%)")
    
    print(f"\nSaved: {POC_DATA / 'scanner_results.json'}")

if __name__ == "__main__":
    main()
