"""Momentum PoC — Improved Scanner v2.

Key insight: Don't try to predict 5% moves. Instead:
1. Pick WIDER (top 10 stocks, not top 3)
2. Filter for CONFIRMED momentum (stock already up >1%)
3. Use STOP LOSS (exit if stock drops 1% from entry)
4. Let WINNERS RUN (no take profit, hold until close)

This approach captures the upside while limiting downside.
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
    # STRATEGY: Pick top 10, filter for confirmed momentum, use stop loss
    # ═══════════════════════════════════════════════════════════════════
    
    STOP_LOSS_PCT = -1.0  # Exit if stock drops 1% from entry
    
    results = []
    
    for date, day_df in df.groupby("date"):
        day_df = day_df.copy()
        
        # Filter 1: Stock must be up at least 1% by 09:45 (confirmed momentum)
        confirmed = day_df[day_df["ret_30m"] > 1.0].copy()
        
        if len(confirmed) == 0:
            continue
        
        # Filter 2: Volume must be above average (rvol > 1.0)
        confirmed = confirmed[confirmed["rvol"] > 1.0]
        
        if len(confirmed) == 0:
            continue
        
        # Pick top 10 by morning momentum
        top_n = min(10, len(confirmed))
        top_stocks = confirmed.nlargest(top_n, "ret_30m")
        
        # Apply stop loss: if return_pct < STOP_LOSS_PCT, treat as loss
        # (In reality, we'd exit at stop loss level, but we can approximate)
        
        # For each stock, calculate return with stop loss
        portfolio_returns = []
        for _, row in top_stocks.iterrows():
            ret = row["return_pct"]
            # If return would have hit stop loss, we exit at stop loss
            if ret < STOP_LOSS_PCT:
                ret = STOP_LOSS_PCT
            portfolio_returns.append(ret)
        
        avg_ret = np.mean(portfolio_returns)
        net_ret = avg_ret - (2 * BROKERAGE_PCT)
        n_hits = sum(1 for r in top_stocks["return_pct"] if r >= 5)
        
        results.append({
            "date": str(date.date()) if hasattr(date, "date") else str(date),
            "n_candidates": len(confirmed),
            "n_trades": len(top_stocks),
            "n_hits": int(n_hits),
            "gross_return": float(avg_ret),
            "net_return": float(net_ret),
            "symbols": top_stocks["symbol"].tolist(),
            "returns": top_stocks["return_pct"].tolist(),
        })
    
    if not results:
        print("ERROR: No trading days"); sys.exit(1)
    
    daily_returns = np.array([r["net_return"] for r in results])
    daily_prec = np.array([r["n_hits"] / len(results) for r in results])
    
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
    print(f"IMPROVED SCANNER v2 (Top-10, Confirmed Momentum, Stop Loss)")
    print(f"{'='*60}")
    print(f"Trading days:       {total_days}")
    print(f"Mean daily return:  {mean_daily:+.3f}%")
    print(f"Sharpe ratio:       {sharpe:.2f}")
    print(f"Total return:       {total_return:+.1f}%")
    print(f"Max drawdown:       {max_drawdown:.1f}%")
    print(f"Win rate:           {win_rate:.1f}%")
    print(f"Hit rate (>=5%):    {hit_rate:.1f}%")
    print(f"Days with >=1 hit:  {days_with_hit/total_days*100:.1f}%")
    print(f"Avg stocks/day:     {total_picks/total_days:.1f}")
    
    # Save results
    report = {
        "type": "improved_scanner_v2",
        "total_trading_days": total_days,
        "mean_daily_return": round(float(mean_daily), 4),
        "sharpe_ratio": round(float(sharpe), 2),
        "total_return_pct": round(float(total_return), 2),
        "max_drawdown_pct": round(float(max_drawdown), 2),
        "win_rate_pct": round(float(win_rate), 1),
        "hit_rate_pct": round(float(hit_rate), 1),
        "days_with_hit_pct": round(days_with_hit/total_days*100, 1),
        "stop_loss_pct": STOP_LOSS_PCT,
    }
    (POC_DATA / "scanner_v2_results.json").write_text(json.dumps(report, indent=2))
    
    # Show sample trades
    print(f"\n--- Sample Trades ---")
    for r in results[:5]:
        print(f"  {r['date']}: {len(r['symbols'])} stocks, net: {r['net_return']:.2f}%, hits: {r['n_hits']}")
    
    print(f"\nSaved: {POC_DATA / 'scanner_v2_results.json'}")

if __name__ == "__main__":
    main()
