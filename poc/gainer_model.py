"""Gainer Prediction Model — Train on top-3 gainer signature.

Uses the morning signature features identified in analysis:
- Volume surge (obv_delta, rvol, avg_vol_30m)
- Volatility (range_30m, atr_ratio)
- Momentum (ret_30m, mom_5d, mom_10d, mom_20d)
- Relative strength (beats_nifty_30m, rel_strength_30m, rank_ret_30m)
"""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import FEATURES_PATH, LABELS_PATH, POC_DATA
import numpy as np
import pandas as pd
try:
    import lightgbm as lgb
    from sklearn.metrics import average_precision_score
except ImportError as e:
    print(f"ERROR: {e}")
    sys.exit(1)

# Features that characterize top gainer morning signature
GAINER_FEATURES = [
    "ret_30m", "range_30m", "rvol", "vol_surge", "obv_delta",
    "gap_up_pct", "rsi_14", "macd_hist", "mom_5d", "mom_10d", "mom_20d",
    "beats_nifty_30m", "rel_strength_30m", "rel_strength_5d",
    "rank_ret_30m", "rank_gap_up", "rank_rvol", "rank_rel_strength",
    "rank_range", "rank_mom_5d", "rank_obv",
    "avg_vol_30m", "vol_10d", "vol_20d", "atr_ratio",
    "nifty_ret_30m", "nifty_mom_5d", "nifty_mom_10d",
    "prev_day_direction", "daily_vol_ratio", "vol_trend",
    "avg_range_10d", "prev_day_ret",
]

def create_gainer_labels(df: pd.DataFrame) -> pd.DataFrame:
    """Label top-3 gainers per day (by actual return_pct)."""
    df = df.copy()
    df["is_top_gainer"] = 0
    for date, day_df in df.groupby("date"):
        if len(day_df) < 3:
            continue
        top3 = day_df.nlargest(3, "return_pct").index
        df.loc[top3, "is_top_gainer"] = 1
    return df

def main():
    features = pd.read_parquet(FEATURES_PATH)
    labels = pd.read_parquet(LABELS_PATH)
    
    features["date"] = pd.to_datetime(features["date"])
    labels["date"] = pd.to_datetime(labels["date"])
    
    df = features.merge(labels[["symbol", "date", "return_pct"]], on=["symbol", "date"], how="inner")
    df = create_gainer_labels(df)
    
    # Filter to available features
    feats = [f for f in GAINER_FEATURES if f in df.columns]
    print(f"Using {len(feats)} features")
    
    df = df.dropna(subset=feats)
    df["year"] = df["date"].dt.year
    
    print(f"Dataset: {len(df):,} rows")
    print(f"Top gainer label: {df['is_top_gainer'].mean()*100:.2f}% positive")
    print()
    
    # Walk-forward validation
    results = []
    all_preds, all_labels, all_dates = [], [], []
    
    for test_year in [2023, 2024, 2025]:
        train = df[df["year"].between(test_year - 2, test_year - 1)]
        test = df[df["year"] == test_year]
        
        if len(train) < 1000 or len(test) < 100:
            continue
        
        X_train, y_train = train[feats], train["is_top_gainer"]
        X_test, y_test = test[feats], test["is_top_gainer"]
        
        scale_pos = (y_train == 0).sum() / max((y_train == 1).sum(), 1)
        
        params = {
            "objective": "binary", "metric": "auc",
            "num_leaves": 31, "max_depth": 6,
            "learning_rate": 0.05, "min_child_weight": 5,
            "subsample": 0.8, "colsample_bytree": 0.8,
            "scale_pos_weight": scale_pos,
            "verbose": -1, "seed": 42,
        }
        
        dtrain = lgb.Dataset(X_train, label=y_train)
        dtest = lgb.Dataset(X_test, label=y_test, reference=dtrain)
        
        model = lgb.train(
            params, dtrain, num_boost_round=500,
            valid_sets=[dtest],
            callbacks=[lgb.early_stopping(50), lgb.log_evaluation(0)],
        )
        
        preds = model.predict(X_test, num_iteration=model.best_iteration)
        ap = average_precision_score(y_test, preds)
        baseline = y_test.mean()
        
        # Per-day precision@3: pick top 3 by score, check if they're top gainers
        test_df = test.copy()
        test_df["pred_score"] = preds
        daily_prec = []
        for date, day_df in test_df.groupby("date"):
            if len(day_df) < 3:
                continue
            pred_top3 = day_df.nlargest(3, "pred_score")
            hits = pred_top3["is_top_gainer"].sum()
            daily_prec.append(hits / 3.0)
        
        mean_prec = np.mean(daily_prec) if daily_prec else 0
        
        results.append({
            "test_year": test_year,
            "ap": float(ap),
            "baseline": float(baseline),
            "precision@3": float(mean_prec),
            "train_rows": len(train),
            "test_rows": len(test),
            "positives": int(y_test.sum()),
        })
        
        print(f"  {test_year}: AP={ap:.4f} (baseline={baseline:.3f}) Prec@3={mean_prec:.4f} (train={len(train):,}, test={len(test):,})")
        
        all_preds.extend(preds.tolist())
        all_labels.extend(y_test.tolist())
        all_dates.extend(test["date"].tolist())
    
    # Summary
    print(f"\n--- Summary ---")
    mean_ap = np.mean([r["ap"] for r in results])
    mean_prec = np.mean([r["precision@3"] for r in results])
    print(f"Mean AP: {mean_ap:.4f}")
    print(f"Mean Precision@3: {mean_prec:.4f}")
    
    # Save results
    report = {
        "model_type": "gainer_prediction",
        "n_features": len(feats),
        "walk_forward_results": results,
        "mean_ap": float(mean_ap),
        "mean_precision_at_3": float(mean_prec),
    }
    (POC_DATA / "gainer_report.json").write_text(json.dumps(report, indent=2))
    print(f"\nSaved: {POC_DATA / 'gainer_report.json'}")

if __name__ == "__main__":
    main()
