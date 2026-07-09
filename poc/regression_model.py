"""Regression Model — Predict exact return_pct (09:45→15:15) instead of binary label.

Compares regression vs classification on same Precision@3 metric.
Adds regression-specific metrics: Rank IC, top-decile mean return.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import FEATURES_PATH, LABELS_PATH, POC_DATA
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
try:
    import lightgbm as lgb
    from sklearn.metrics import average_precision_score, mean_squared_error
except ImportError as e:
    print(f"ERROR: {e}")
    sys.exit(1)

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

# Stage 1 rules from meta-labeling approach
STAGE1_RULES = {
    "ret_30m > 1%": ("ret_30m", 1.0),
    "rvol > 1.5": ("rvol", 1.5),
    "beats_nifty_30m == 1": ("beats_nifty_30m", None),
}


def apply_stage1(df: pd.DataFrame) -> pd.DataFrame:
    """Apply Stage 1 rules to generate candidate pool."""
    candidates = df.copy()
    for rule_name, (col, threshold) in STAGE1_RULES.items():
        if threshold is not None:
            candidates = candidates[candidates[col] > threshold]
        else:
            candidates = candidates[candidates[col] == 1]
    return candidates


def precision_at_3(test_df: pd.DataFrame, score_col: str) -> float:
    """Precision@3: pick top 3 by score_col, check if they're top-3 gainers by actual return."""
    daily_prec = []
    for date, day_df in test_df.groupby("date"):
        if len(day_df) < 3:
            continue
        top3_actual = set(day_df.nlargest(3, "return_pct").index)
        top3_pred = set(day_df.nlargest(3, score_col).index)
        hits = len(top3_pred & top3_actual)
        daily_prec.append(hits / 3.0)
    return float(np.mean(daily_prec)) if daily_prec else 0.0


def rank_ic(test_df: pd.DataFrame, pred_col: str, actual_col: str = "return_pct") -> float:
    """Spearman Rank IC between predictions and actual returns."""
    daily_ics = []
    for date, day_df in test_df.groupby("date"):
        if len(day_df) < 10:
            continue
        r, _ = spearmanr(day_df[pred_col], day_df[actual_col])
        if not np.isnan(r):
            daily_ics.append(r)
    return float(np.mean(daily_ics)) if daily_ics else 0.0


def top_decile_mean_return(test_df: pd.DataFrame, pred_col: str) -> float:
    """Mean actual return of stocks in top decile by predicted score."""
    daily_returns = []
    for date, day_df in test_df.groupby("date"):
        if len(day_df) < 10:
            continue
        n_top = max(1, len(day_df) // 10)
        top = day_df.nlargest(n_top, pred_col)
        daily_returns.append(top["return_pct"].mean())
    return float(np.mean(daily_returns)) if daily_returns else 0.0


def top_quintile_spread(test_df: pd.DataFrame, pred_col: str, actual_col: str = "return_pct") -> float:
    """Mean return of top quintile minus bottom quintile."""
    spreads = []
    for date, day_df in test_df.groupby("date"):
        if len(day_df) < 20:
            continue
        n = len(day_df) // 5
        top = day_df.nlargest(n, pred_col)[actual_col].mean()
        bot = day_df.nsmallest(n, pred_col)[actual_col].mean()
        spreads.append(top - bot)
    return float(np.mean(spreads)) if spreads else 0.0


def main():
    features = pd.read_parquet(FEATURES_PATH)
    labels = pd.read_parquet(LABELS_PATH)

    features["date"] = pd.to_datetime(features["date"])
    labels["date"] = pd.to_datetime(labels["date"])

    df = features.merge(labels[["symbol", "date", "return_pct"]], on=["symbol", "date"], how="inner")
    df["year"] = df["date"].dt.year

    # Filter available features
    feats = [f for f in ALL_FEATURES if f in df.columns]
    df = df.dropna(subset=feats)
    df = df[df["year"] >= 2021]  # Need data for train

    print(f"Dataset: {len(df):,} rows, {df['date'].nunique()} days, {df['symbol'].nunique()} symbols")
    print(f"return_pct: mean={df['return_pct'].mean():+.4f}%, median={df['return_pct'].median():+.4f}%")
    print(f"  >=5% movers: {(df['return_pct']>=5).mean()*100:.2f}% of rows")
    print(f"Features: {len(feats)}")
    print()

    # ── Approach A: Stage 1 + classification (meta-label baseline) ──
    # ── Approach B: Stage 1 + regression (predict return_pct) ───────
    # ── Approach C: Full universe regression ────────────────────────
    # ── Approach D: Naive momentum rule (top 3 by ret_30m) ──────────

    candidates = apply_stage1(df)
    candidates = candidates.dropna(subset=feats)
    print(f"Stage 1 filter: {len(df):,} → {len(candidates):,} ({len(candidates)/len(df)*100:.1f}%)")
    print()

    results = []

    for test_year in [2023, 2024, 2025]:
        train_cand = candidates[candidates["year"].between(test_year - 2, test_year - 1)]
        test_cand = candidates[candidates["year"] == test_year]
        test_full = df[df["year"] == test_year]

        if len(train_cand) < 100 or len(test_cand) < 30:
            continue

        X_train_c, y_train_c = train_cand[feats], train_cand["return_pct"]
        X_test_c, y_test_c = test_cand[feats], test_cand["return_pct"]
        X_test_f = test_full[feats]

        # ── B: REGRESSION on candidates ──
        params_reg = {
            "objective": "regression", "metric": "rmse",
            "num_leaves": 31, "max_depth": 6,
            "learning_rate": 0.05, "min_child_weight": 5,
            "subsample": 0.8, "colsample_bytree": 0.8,
            "reg_alpha": 0.1, "reg_lambda": 1.0,
            "verbose": -1, "seed": 42,
        }
        dtrain_r = lgb.Dataset(X_train_c, label=y_train_c)
        dtest_r = lgb.Dataset(X_test_c, label=y_test_c, reference=dtrain_r)
        model_reg = lgb.train(
            params_reg, dtrain_r, num_boost_round=500,
            valid_sets=[dtest_r],
            callbacks=[lgb.early_stopping(50), lgb.log_evaluation(0)],
        )
        preds_reg = model_reg.predict(X_test_c, num_iteration=model_reg.best_iteration)
        test_cand_reg = test_cand.copy()
        test_cand_reg["pred_return"] = preds_reg

        # ── A: CLASSIFICATION (binary is_top_gainer) on candidates ──
        train_cls = train_cand.copy()
        test_cls = test_cand.copy()
        for date, day_df in train_cls.groupby("date"):
            if len(day_df) >= 3:
                top3 = day_df.nlargest(3, "return_pct").index
                train_cls.loc[top3, "is_top_gainer"] = 1
            else:
                train_cls.loc[day_df.index, "is_top_gainer"] = 0
        train_cls["is_top_gainer"] = train_cls.get("is_top_gainer", 0).fillna(0)
        for date, day_df in test_cls.groupby("date"):
            if len(day_df) >= 3:
                top3 = day_df.nlargest(3, "return_pct").index
                test_cls.loc[top3, "is_top_gainer"] = 1
            else:
                test_cls.loc[day_df.index, "is_top_gainer"] = 0
        test_cls["is_top_gainer"] = test_cls.get("is_top_gainer", 0).fillna(0)

        y_train_cls = train_cls["is_top_gainer"]
        y_test_cls = test_cls["is_top_gainer"]

        scale_pos = (y_train_cls == 0).sum() / max((y_train_cls == 1).sum(), 1)
        params_cls = {
            "objective": "binary", "metric": "auc",
            "num_leaves": 31, "max_depth": 6,
            "learning_rate": 0.05, "min_child_weight": 5,
            "subsample": 0.8, "colsample_bytree": 0.8,
            "scale_pos_weight": scale_pos,
            "verbose": -1, "seed": 42,
        }
        dtrain_c = lgb.Dataset(X_train_c, label=y_train_cls)
        dtest_c = lgb.Dataset(X_test_c, label=y_test_cls, reference=dtrain_c)
        model_cls = lgb.train(
            params_cls, dtrain_c, num_boost_round=500,
            valid_sets=[dtest_c],
            callbacks=[lgb.early_stopping(50), lgb.log_evaluation(0)],
        )
        preds_cls = model_cls.predict(X_test_c, num_iteration=model_cls.best_iteration)
        test_cls["pred_prob"] = preds_cls

        # ── C: FULL UNIVERSE REGRESSION ──
        train_full = df[df["year"].between(test_year - 2, test_year - 1)]
        test_full_actual = test_full.copy()
        X_train_f, y_train_f = train_full[feats], train_full["return_pct"]
        X_test_f_actual = test_full[feats]

        dtrain_f = lgb.Dataset(X_train_f, label=y_train_f)
        model_reg_full = lgb.train(
            {**params_reg, "learning_rate": 0.03, "num_leaves": 63},
            dtrain_f, num_boost_round=500,
            valid_sets=None,
            callbacks=[lgb.log_evaluation(0)],
        )
        preds_reg_full = model_reg_full.predict(X_test_f_actual)
        test_full_actual["pred_return"] = preds_reg_full

        # ── METRICS ──

        # 1. Precision@3 (regression on candidates)
        reg_prec3 = precision_at_3(test_cand_reg, score_col="pred_return")

        # 2. Precision@3 (classification on candidates)
        cls_prec3 = precision_at_3(test_cls, score_col="pred_prob")

        # 3. Precision@3 (naive momentum on candidates)
        mom_prec3 = precision_at_3(test_cand, score_col="ret_30m")

        # 4. Precision@3 (naive momentum on full universe)
        full_mom_prec3 = precision_at_3(test_full, score_col="ret_30m")

        # 5. Precision@3 (full universe regression)
        full_reg_prec3 = precision_at_3(test_full_actual, score_col="pred_return")

        # 6. Rank IC (regression)
        reg_ric = rank_ic(test_cand_reg, pred_col="pred_return")

        # 7. Rank IC (classification)
        cls_ric = rank_ic(test_cls, pred_col="pred_prob")

        # 8. Top-decile mean return (regression)
        reg_td = top_decile_mean_return(test_cand_reg, pred_col="pred_return")

        # 9. Top-decile mean return (classification)
        cls_td = top_decile_mean_return(test_cls, pred_col="pred_prob")

        # 10. Top-quintile spread
        reg_qs = top_quintile_spread(test_cand_reg, pred_col="pred_return")
        cls_qs = top_quintile_spread(test_cls, pred_col="pred_prob")

        # 11. RMSE (regression only)
        reg_rmse = np.sqrt(mean_squared_error(y_test_c, preds_reg))

        # 12. Classification AP
        cls_ap = average_precision_score(y_test_cls, preds_cls)

        results.append({
            "test_year": test_year,
            "candidates_per_day": len(test_cand) / max(test_cand["date"].nunique(), 1),
            "regression": {
                "precision@3": float(reg_prec3),
                "rank_ic": float(reg_ric),
                "top_decile_mean_ret": float(reg_td),
                "quintile_spread": float(reg_qs),
                "rmse": float(reg_rmse),
            },
            "classification": {
                "precision@3": float(cls_prec3),
                "rank_ic": float(cls_ric),
                "top_decile_mean_ret": float(cls_td),
                "quintile_spread": float(cls_qs),
                "ap": float(cls_ap),
                "baseline": float(y_test_cls.mean()),
            },
            "baselines": {
                "momentum_candidates_prec@3": float(mom_prec3),
                "momentum_full_prec@3": float(full_mom_prec3),
                "regression_full_prec@3": float(full_reg_prec3),
            },
        })

        print(f"  {test_year}: Cand/day={len(test_cand)/max(test_cand['date'].nunique(),1):.1f}")
        print(f"    REGRESSION: Prec@3={reg_prec3:.4f} | RankIC={reg_ric:.4f} | TopDec={reg_td:+.2f}% | QSpread={reg_qs:+.2f}% | RMSE={reg_rmse:.2f}")
        print(f"    CLASSIFICATION: Prec@3={cls_prec3:.4f} | RankIC={cls_ric:.4f} | TopDec={cls_td:+.2f}% | QSpread={cls_qs:+.2f}% | AP={cls_ap:.4f}")
        print(f"    BASELINES: Mom(cand)={mom_prec3:.4f} | Mom(full)={full_mom_prec3:.4f} | RegFull={full_reg_prec3:.4f}")

    # Summary
    print(f"\n{'='*75}")
    print("REGRESSION vs CLASSIFICATION — 3-Year Summary")
    print(f"{'='*75}")

    print(f"\n{'Metric':<30} {'Regression':<15} {'Classification':<15} {'Mom Rule':<15}")
    print("-" * 75)

    for metric, key in [
        ("Precision@3 (candidates)", "precision@3"),
        ("Rank IC", "rank_ic"),
        ("Top-decile mean return", "top_decile_mean_ret"),
        ("Quintile spread", "quintile_spread"),
    ]:
        reg_vals = [r["regression"][key] for r in results]
        cls_vals = [r["classification"][key] for r in results]
        reg_avg = np.mean(reg_vals) if reg_vals else 0
        cls_avg = np.mean(cls_vals) if cls_vals else 0
        mom_cand = np.mean([r["baselines"]["momentum_candidates_prec@3"] for r in results])
        mom_full = np.mean([r["baselines"]["momentum_full_prec@3"] for r in results])

        if key == "precision@3":
            print(f"{metric:<30} {reg_avg:<15.4f} {cls_avg:<15.4f} {mom_cand:<15.4f} (cand)")
            print(f"{'':<30} {'':<15} {'':<15} {mom_full:<15.4f} (full)")
        else:
            print(f"{metric:<30} {reg_avg:<15.4f} {cls_avg:<15.4f} {'N/A':<15}")

    print(f"\nClassification mean AP: {np.mean([r['classification']['ap'] for r in results]):.4f}")

    # Which approach wins?
    reg_prec = np.mean([r["regression"]["precision@3"] for r in results])
    cls_prec = np.mean([r["classification"]["precision@3"] for r in results])
    mom_prec = np.mean([r["baselines"]["momentum_candidates_prec@3"] for r in results])

    print(f"\n{'='*75}")
    print("VERDICT")
    print(f"{'='*75}")
    print(f"  Regression Prec@3:        {reg_prec:.4f} (lift vs cand random: {reg_prec/(1/501*candidates['date'].nunique()/candidates['date'].nunique()):.2f}x)")
    print(f"  Classification Prec@3:     {cls_prec:.4f}")
    print(f"  Momentum rule Prec@3:      {mom_prec:.4f}")
    print(f"  Random (full universe):    {(3/df['symbol'].nunique()):.4f}")

    winner = "REGRESSION" if reg_prec >= cls_prec else "CLASSIFICATION"
    print(f"\n  Winner: {winner}")
    print(f"  Reg/Cls ratio: {reg_prec/max(cls_prec, 0.001):.2f}x")

    # Save report
    report = {
        "method": "regression_vs_classification",
        "test_years": [2023, 2024, 2025],
        "n_features": len(feats),
        "stage1_filter_pct": len(candidates) / len(df) * 100,
        "results": results,
        "winning_approach": winner,
        "reg_vs_cls_ratio": float(reg_prec / max(cls_prec, 0.001)),
    }
    (POC_DATA / "regression_report.json").write_text(json.dumps(report, indent=2))
    print(f"\nSaved: {POC_DATA / 'regression_report.json'}")


if __name__ == "__main__":
    main()
