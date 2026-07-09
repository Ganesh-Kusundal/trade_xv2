"""Meta-Labeling: Two-Stage Gainer Prediction.

Stage 1 — Simple rules generate candidate pool:
  - ret_30m > 1%      (confirmed morning momentum)
  - rvol > 1.5        (volume surge)
  - beats_nifty_30m   (relative strength)

Stage 2 — ML model filters candidates:
  - Trained only on Stage 1 candidates
  - Predicts which candidates become top-3 gainers
  - Compares vs: candidates only (no ML), random selection

This approach should work better because Stage 1 removes noise,
allowing Stage 2 to focus on finer-grained patterns.
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

# Stage 1: Simple rules to generate candidates
STAGE1_RULES = {
    "ret_30m > 1%": ("ret_30m", 1.0),
    "rvol > 1.5": ("rvol", 1.5),
    "beats_nifty_30m == 1": ("beats_nifty_30m", None),
}

STAGE2_FEATURES = [
    "ret_30m", "range_30m", "rvol", "vol_surge", "obv_delta",
    "gap_up_pct", "rsi_14", "mom_5d", "mom_10d", "mom_20d",
    "rel_strength_30m", "rel_strength_5d",
    "rank_ret_30m", "rank_gap_up", "rank_rvol",
    "rank_rel_strength", "rank_range", "rank_mom_5d",
    "avg_vol_30m", "vol_10d", "vol_20d", "atr_ratio",
    "nifty_ret_30m", "nifty_mom_5d", "nifty_mom_10d",
    "prev_day_direction", "daily_vol_ratio", "vol_trend",
    "avg_range_10d", "prev_day_ret",
]

def apply_stage1(df: pd.DataFrame) -> pd.DataFrame:
    """Apply Stage 1 rules to generate candidate pool."""
    candidates = df.copy()
    for rule_name, (col, threshold) in STAGE1_RULES.items():
        if threshold is not None:
            candidates = candidates[candidates[col] > threshold]
        else:
            candidates = candidates[candidates[col] == 1]
    return candidates

def create_gainer_labels(df: pd.DataFrame) -> pd.DataFrame:
    """Label top-3 gainers per day."""
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
    df["year"] = df["date"].dt.year
    
    # Filter to test period
    df = df[df["year"] >= 2021]
    
    print(f"Full universe: {len(df):,} rows, {df['date'].nunique()} days")
    print(f"Top gainer rate: {df['is_top_gainer'].mean()*100:.2f}%")
    print()
    
    # Stage 1: Apply simple rules
    candidates = apply_stage1(df)
    feats = [f for f in STAGE2_FEATURES if f in candidates.columns]
    candidates = candidates.dropna(subset=feats)
    
    print(f"=== STAGE 1: Simple Rules ===")
    print(f"Universe: {len(df):,} -> Candidates: {len(candidates):,} ({len(candidates)/len(df)*100:.1f}%)")
    print(f"Candidate top gainer rate: {candidates['is_top_gainer'].mean()*100:.2f}%")
    print()
    
    # Baseline 1: Pick random from candidates
    # Baseline 2: Pick top 3 by ret_30m from candidates
    # Stage 2: ML model
    
    all_results = []
    
    for test_year in [2023, 2024, 2025]:
        train = candidates[candidates["year"].between(test_year - 2, test_year - 1)]
        test = candidates[candidates["year"] == test_year]
        
        if len(train) < 100 or len(test) < 30:
            continue
        
        # Baseline 1: Random selection from candidates
        test_years_candidates = candidates[candidates["year"] == test_year]
        random_prec = []
        for date, day_df in test_years_candidates.groupby("date"):
            if len(day_df) < 3:
                continue
            random_top3 = day_df.sample(min(3, len(day_df)))
            hits = random_top3["is_top_gainer"].sum()
            random_prec.append(hits / 3.0)
        
        # Baseline 2: Top 3 by ret_30m (momentum rule)
        momentum_prec = []
        for date, day_df in test_years_candidates.groupby("date"):
            if len(day_df) < 3:
                continue
            mom_top3 = day_df.nlargest(3, "ret_30m")
            hits = mom_top3["is_top_gainer"].sum()
            momentum_prec.append(hits / 3.0)
        
        # Stage 2: ML model
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
        
        # Stage 2 Precision@3: pick top 3 by ML score from candidates
        ml_prec = []
        test_df = test.copy()
        test_df["ml_score"] = preds
        for date, day_df in test_df.groupby("date"):
            if len(day_df) < 3:
                continue
            ml_top3 = day_df.nlargest(3, "ml_score")
            hits = ml_top3["is_top_gainer"].sum()
            ml_prec.append(hits / 3.0)
        
        ap = average_precision_score(y_test, preds)
        baseline_rate = y_test.mean()
        
        all_results.append({
            "test_year": test_year,
            "candidates_per_day": len(test) / test["date"].nunique(),
            "baseline_rate": float(baseline_rate),
            "ml_ap": float(ap),
            "random_prec@3": float(np.mean(random_prec)) if random_prec else 0,
            "momentum_prec@3": float(np.mean(momentum_prec)) if momentum_prec else 0,
            "ml_prec@3": float(np.mean(ml_prec)) if ml_prec else 0,
            "ml_prec_lift_vs_random": float(np.mean(ml_prec) / max(np.mean(random_prec), 0.001)) if ml_prec and random_prec else 0,
        })
        
        print(f"  {test_year}:")
        print(f"    Candidates/day: {len(test)/test['date'].nunique():.1f}")
        print(f"    Baseline rate: {baseline_rate:.3f}")
        print(f"    ML AP: {ap:.4f}")
        print(f"    Random Prec@3: {np.mean(random_prec):.4f}")
        print(f"    Momentum Prec@3: {np.mean(momentum_prec):.4f}")
        print(f"    ML Prec@3: {np.mean(ml_prec):.4f}")
        print(f"    ML lift vs random: {np.mean(ml_prec)/max(np.mean(random_prec), 0.001):.2f}x")
    
    # Summary
    print(f"\n{'='*60}")
    print(f"META-LABELING SUMMARY")
    print(f"{'='*60}")
    
    avg_random = np.mean([r["random_prec@3"] for r in all_results])
    avg_momentum = np.mean([r["momentum_prec@3"] for r in all_results])
    avg_ml = np.mean([r["ml_prec@3"] for r in all_results])
    avg_lift = np.mean([r["ml_prec_lift_vs_random"] for r in all_results])
    avg_ap = np.mean([r["ml_ap"] for r in all_results])
    
    print(f"Stage 1 candidates/day: {all_results[0]['candidates_per_day']:.1f}")
    print(f"Random selection Prec@3:    {avg_random:.4f}")
    print(f"Momentum rule Prec@3:       {avg_momentum:.4f}")
    print(f"ML filtered Prec@3:         {avg_ml:.4f}")
    print(f"ML lift vs random:          {avg_lift:.2f}x")
    print(f"ML mean AP:                 {avg_ap:.4f}")
    
    print(f"\nImprovement of ML vs Momentum rule: {(avg_ml/avg_momentum - 1)*100:.1f}%" if avg_momentum > 0 else "")
    
    # Save report
    report = {
        "method": "meta_labeling",
        "stage1_rules": list(STAGE1_RULES.keys()),
        "n_stage2_features": len(feats),
        "results": all_results,
        "avg_random_prec3": float(avg_random),
        "avg_momentum_prec3": float(avg_momentum),
        "avg_ml_prec3": float(avg_ml),
        "avg_ml_lift_vs_random": float(avg_lift),
        "avg_ml_ap": float(avg_ap),
    }
    (POC_DATA / "meta_label_report.json").write_text(json.dumps(report, indent=2))
    print(f"\nSaved: {POC_DATA / 'meta_label_report.json'}")

if __name__ == "__main__":
    main()
