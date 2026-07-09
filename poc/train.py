"""Momentum PoC — LightGBM Walk-Forward Training (50+ Features, GPU)."""
from __future__ import annotations
import json, pickle, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (DATASET_PATH, FEATURES_PATH, LABELS_PATH, MODEL_PATH, N_ESTIMATORS, POC_DATA)
import numpy as np
import pandas as pd
try:
    import lightgbm as lgb
    from sklearn.metrics import average_precision_score
except ImportError as e:
    print(f"ERROR: {e}. Run: pip install lightgbm scikit-learn")
    sys.exit(1)

# All 50+ feature columns (auto-detected from features.parquet)
FEATURE_COLS = None  # Will be set dynamically

# Walk-forward config
TRAIN_WINDOW_YEARS = 2
TEST_WINDOW_YEARS = 1
FIRST_TRAIN_END = 2022
LAST_TEST_YEAR = 2025

# LightGBM params
LGB_PARAMS = {
    "objective": "binary",
    "metric": "auc",
    "boosting_type": "gbdt",
    "num_leaves": 63,
    "max_depth": 8,
    "learning_rate": 0.03,
    "min_child_weight": 10,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "reg_alpha": 0.1,
    "reg_lambda": 1.0,
    "min_split_gain": 0.01,
    "verbose": -1,
    "seed": 42,
}

def load_dataset():
    """Load and merge features + labels."""
    features = pd.read_parquet(FEATURES_PATH)
    labels = pd.read_parquet(LABELS_PATH)
    features["date"] = pd.to_datetime(features["date"])
    labels["date"] = pd.to_datetime(labels["date"])
    merged = features.merge(labels[["symbol","date","label","return_pct"]], on=["symbol","date"], how="inner")
    print(f"Dataset: {len(merged):,} rows, {merged['label'].mean()*100:.2f}% positive")
    
    # Auto-detect feature columns (all numeric except symbol, date, label, return_pct)
    exclude = {"symbol", "date", "label", "return_pct", "close_0945"}
    global FEATURE_COLS
    FEATURE_COLS = [c for c in merged.select_dtypes(include=[np.number]).columns if c not in exclude]
    print(f"Features: {len(FEATURE_COLS)} columns")
    
    # Log-scale some features for better distribution
    for col in ["rvol", "daily_vol_ratio", "vol_trend"]:
        if col in FEATURE_COLS:
            merged[col] = np.log1p(merged[col].clip(0.001, 100))
    
    merged = merged.dropna(subset=FEATURE_COLS)
    merged["year"] = merged["date"].dt.year
    return merged

def walk_forward(df):
    """Walk-forward: 2-year train, 1-year test."""
    results = []
    all_preds, all_labels, all_dates, all_symbols = [], [], [], []
    
    train_end = FIRST_TRAIN_END
    test_start = train_end + 1
    
    print(f"\n{'='*60}")
    print(f"LIGHTGBM WALK-FORWARD ({len(FEATURE_COLS)} features)")
    print(f"{'='*60}")
    
    while test_start <= LAST_TEST_YEAR:
        test_end = test_start + TEST_WINDOW_YEARS - 1
        train_start = train_end - TRAIN_WINDOW_YEARS + 1
        
        train = df[(df["year"] >= train_start) & (df["year"] <= train_end)]
        test = df[(df["year"] >= test_start) & (df["year"] <= test_end)]
        
        if len(train) < 1000 or len(test) < 100:
            print(f"  {train_start}-{train_end} -> {test_start}-{test_end}: SKIPPED")
            train_end += 1; test_start += 1
            continue
        
        X_train, y_train = train[FEATURE_COLS], train["label"]
        X_test, y_test = test[FEATURE_COLS], test["label"]
        
        # Class weight
        scale_pos = (y_train == 0).sum() / max((y_train == 1).sum(), 1)
        params = {**LGB_PARAMS, "scale_pos_weight": scale_pos}
        
        dtrain = lgb.Dataset(X_train, label=y_train)
        dtest = lgb.Dataset(X_test, label=y_test, reference=dtrain)
        
        model = lgb.train(
            params, dtrain, num_boost_round=N_ESTIMATORS,
            valid_sets=[dtest],
            callbacks=[lgb.early_stopping(50), lgb.log_evaluation(0)],
        )
        
        preds = model.predict(X_test, num_iteration=model.best_iteration)
        ap = average_precision_score(y_test, preds)
        
        all_preds.extend(preds.tolist())
        all_labels.extend(y_test.tolist())
        all_dates.extend(test["date"].tolist())
        all_symbols.extend(test["symbol"].tolist())
        
        # Feature importance
        imp = pd.Series(model.feature_importance(importance_type="gain"), index=FEATURE_COLS)
        top5 = imp.nlargest(5).to_dict()
        
        results.append({
            "window": f"{train_start}-{train_end} -> {test_start}-{test_end}",
            "train_rows": len(train), "test_rows": len(test),
            "test_positives": int(y_test.sum()),
            "ap": float(ap),
            "top5_features": {k: round(v, 1) for k, v in top5.items()},
        })
        
        print(f"  {train_start}-{train_end} -> {test_start}-{test_end}: AP={ap:.4f} (train={len(train):,}, test={len(test):,}, pos={int(y_test.sum())})")
        print(f"    Top features: {list(top5.keys())}")
        
        # Save model
        models_dir = MODEL_PATH.parent / "wf_models"
        models_dir.mkdir(exist_ok=True)
        model.save_model(str(models_dir / f"model_{test_start}.txt"))
        
        train_end += 1; test_start += 1
    
    aps = [r["ap"] for r in results]
    print(f"\n--- Summary ---")
    print(f"Windows: {len(results)}, Mean AP: {np.mean(aps):.4f} +/- {np.std(aps):.4f}")
    print(f"Min AP: {np.min(aps):.4f}, Max AP: {np.max(aps):.4f}")
    
    return {
        "results": results,
        "mean_ap": float(np.mean(aps)), "std_ap": float(np.std(aps)),
        "all_preds": all_preds, "all_labels": all_labels,
        "all_dates": all_dates, "all_symbols": all_symbols,
    }

def main():
    df = load_dataset()
    wf = walk_forward(df)
    
    # Save report
    report = {"walk_forward_results": wf["results"], "mean_ap": wf["mean_ap"], "std_ap": wf["std_ap"]}
    (POC_DATA / "train_report.json").write_text(json.dumps(report, indent=2))
    
    # Save predictions
    preds_df = pd.DataFrame({
        "symbol": wf["all_symbols"], "date": wf["all_dates"],
        "pred_score": wf["all_preds"], "label": wf["all_labels"],
    })
    preds_df.to_parquet(str(POC_DATA / "wf_predictions.parquet"), index=False)
    
    print(f"\nReport: {POC_DATA / 'train_report.json'}")
    print(f"Predictions: {POC_DATA / 'wf_predictions.parquet'}")

if __name__ == "__main__":
    main()
