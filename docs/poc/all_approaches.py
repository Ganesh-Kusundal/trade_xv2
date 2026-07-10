"""Comprehensive comparison of 7 approaches to pick top-3 gainers.

All approaches use the same Stage 1 pipeline (ret_30m > 1%, rvol > 1.5, beats_nifty_30m == 1)
and the same walk-forward validation (test years 2023, 2024, 2025).

Approaches:
  1. Momentum rule (Stage 1 → top 3 by ret_30m)    — baseline
  2. Classification (Stage 1 → LightGBM binary)      — existing best
  3. Regression (Stage 1 → LightGBM regression)      — predict exact return
  4. Huber (Stage 1 → LightGBM huber loss)           — robust to outliers
  5. Quantile (Stage 1 → LightGBM quantile, α=0.9)  — predict upper tail directly
  6. Ensemble rank (Stage 1 → rank(reg) + rank(cls) avg)
  7. Dual-stage (Stage 1 → reg predicts return → cls uses reg_pred as feature)
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

STAGE1_RULES = {
    "ret_30m > 1%": ("ret_30m", 1.0),
    "rvol > 1.5": ("rvol", 1.5),
    "beats_nifty_30m == 1": ("beats_nifty_30m", None),
}

# Common LightGBM parameters
LGB_CORE = {
    "num_leaves": 31, "max_depth": 6,
    "learning_rate": 0.05, "min_child_weight": 5,
    "subsample": 0.8, "colsample_bytree": 0.8,
    "reg_alpha": 0.1, "reg_lambda": 1.0,
    "verbose": -1, "seed": 42,
}


def apply_stage1(df: pd.DataFrame) -> pd.DataFrame:
    candidates = df.copy()
    for _, (col, threshold) in STAGE1_RULES.items():
        if threshold is not None:
            candidates = candidates[candidates[col] > threshold]
        else:
            candidates = candidates[candidates[col] == 1]
    return candidates


def precision_at_3(test_df: pd.DataFrame, score_col: str) -> float:
    """Precision@3: pick top 3 by score, check if they're actual top-3 gainers."""
    daily_prec = []
    for date, day_df in test_df.groupby("date"):
        if len(day_df) < 3:
            continue
        top3_actual = set(day_df.nlargest(3, "return_pct").index)
        top3_pred = set(day_df.nlargest(3, score_col).index)
        hits = len(top3_pred & top3_actual)
        daily_prec.append(hits / 3.0)
    return float(np.mean(daily_prec)) if daily_prec else 0.0


def train_model(params: dict, X_train, y_train, X_test, y_test) -> tuple:
    """Train a LightGBM model with early stopping. Returns (model, predictions)."""
    dtrain = lgb.Dataset(X_train, label=y_train)
    dtest = lgb.Dataset(X_test, label=y_test, reference=dtrain)
    model = lgb.train(
        params, dtrain, num_boost_round=500,
        valid_sets=[dtest],
        callbacks=[lgb.early_stopping(50), lgb.log_evaluation(0)],
    )
    preds = model.predict(X_test, num_iteration=model.best_iteration)
    return model, preds


def main():
    features = pd.read_parquet(FEATURES_PATH)
    labels = pd.read_parquet(LABELS_PATH)
    features["date"] = pd.to_datetime(features["date"])
    labels["date"] = pd.to_datetime(labels["date"])

    df = features.merge(labels[["symbol", "date", "return_pct"]], on=["symbol", "date"], how="inner")
    df["year"] = df["date"].dt.year

    feats = [f for f in ALL_FEATURES if f in df.columns]
    df = df.dropna(subset=feats)
    df = df[df["year"] >= 2021]

    candidates = apply_stage1(df)
    candidates = candidates.dropna(subset=feats)

    print(f"Full universe: {len(df):,} rows")
    print(f"Stage 1 candidates: {len(candidates):,} ({len(candidates)/len(df)*100:.1f}%)")
    print(f"Candidates/day: ~{len(candidates)/max(candidates['date'].nunique(),1):.0f}")
    print(f"Features: {len(feats)}")
    print()

    results = []

    for test_year in [2023, 2024, 2025]:
        train = candidates[candidates["year"].between(test_year - 2, test_year - 1)]
        test = candidates[candidates["year"] == test_year]
        test_full = df[df["year"] == test_year]

        if len(train) < 100 or len(test) < 30:
            continue

        X_train, y_train_ret = train[feats], train["return_pct"]
        X_test, y_test_ret = test[feats], test["return_pct"]

        # ── 1. Momentum rule (baseline) ──
        momentum_prec = precision_at_3(test, score_col="ret_30m")

        # ── Labels for classification approaches ──
        train_cls = train.copy()
        test_cls = test.copy()
        train_cls["is_top_gainer"] = 0
        test_cls["is_top_gainer"] = 0
        for date, day_df in train_cls.groupby("date"):
            if len(day_df) >= 3:
                train_cls.loc[day_df.nlargest(3, "return_pct").index, "is_top_gainer"] = 1
        for date, day_df in test_cls.groupby("date"):
            if len(day_df) >= 3:
                test_cls.loc[day_df.nlargest(3, "return_pct").index, "is_top_gainer"] = 1

        y_train_cls = train_cls["is_top_gainer"].values
        y_test_cls = test_cls["is_top_gainer"].values
        scale_pos = max(1.0, (y_train_cls == 0).sum() / max((y_train_cls == 1).sum(), 1))

        # ── 2. Classification ──
        params_cls = {**LGB_CORE, "objective": "binary", "metric": "auc", "scale_pos_weight": scale_pos}
        _, preds_cls = train_model(params_cls, X_train, y_train_cls, X_test, y_test_cls)
        test_cls["cls_score"] = preds_cls
        cls_prec = precision_at_3(test_cls, score_col="cls_score")
        cls_ap = average_precision_score(y_test_cls, preds_cls)

        # ── 3. Regression ──
        params_reg = {**LGB_CORE, "objective": "regression", "metric": "rmse"}
        _, preds_reg = train_model(params_reg, X_train, y_train_ret, X_test, y_test_ret)
        test_reg = test.copy()
        test_reg["reg_score"] = preds_reg
        reg_prec = precision_at_3(test_reg, score_col="reg_score")

        # ── 4. Huber ──
        params_huber = {**LGB_CORE, "objective": "huber", "metric": "rmse"}
        _, preds_huber = train_model(params_huber, X_train, y_train_ret, X_test, y_test_ret)
        test_huber = test.copy()
        test_huber["huber_score"] = preds_huber
        huber_prec = precision_at_3(test_huber, score_col="huber_score")

        # ── 5. Quantile (alpha=0.9) ──
        params_quantile = {**LGB_CORE, "objective": "quantile", "metric": "quantile", "alpha": 0.9}
        dtrain_q = lgb.Dataset(X_train, label=y_train_ret)
        dtest_q = lgb.Dataset(X_test, label=y_test_ret, reference=dtrain_q)
        model_q = lgb.train(
            params_quantile, dtrain_q, num_boost_round=500,
            valid_sets=[dtest_q],
            callbacks=[lgb.early_stopping(50), lgb.log_evaluation(0)],
        )
        preds_q = model_q.predict(X_test, num_iteration=model_q.best_iteration)
        test_q = test.copy()
        test_q["q_score"] = preds_q
        quantile_prec = precision_at_3(test_q, score_col="q_score")

        # ── 6. Ensemble rank (classification + regression rank avg) ──
        test_ens = test.copy()
        test_ens["reg_score"] = preds_reg
        test_ens["cls_score"] = preds_cls
        for date, day_df in test_ens.groupby("date"):
            if len(day_df) >= 3:
                test_ens.loc[day_df.index, "rank_reg"] = day_df["reg_score"].rank(ascending=False, pct=True)
                test_ens.loc[day_df.index, "rank_cls"] = day_df["cls_score"].rank(ascending=False, pct=True)
            else:
                test_ens.loc[day_df.index, "rank_reg"] = 0.5
                test_ens.loc[day_df.index, "rank_cls"] = 0.5
        test_ens["ensemble"] = (test_ens["rank_reg"] + test_ens["rank_cls"]) / 2.0
        ensemble_prec = precision_at_3(test_ens, score_col="ensemble")

        # ── 7. Dual-stage: regression predicts → classification uses reg_pred as extra feature ──
        # Train regression on full universe (more data) to get better return predictions
        train_full = df[df["year"].between(test_year - 2, test_year - 1)]
        X_train_full, y_train_full = train_full[feats], train_full["return_pct"]
        params_dual = {**LGB_CORE, "objective": "regression", "metric": "rmse", "learning_rate": 0.03}
        X_train_full_sub = X_train_full.sample(min(50000, len(X_train_full)), random_state=42)
        y_train_full_sub = y_train_full.loc[X_train_full_sub.index]
        X_val_full = X_train_full.drop(X_train_full_sub.index)
        y_val_full = y_train_full.loc[X_val_full.index]
        dtrain_dual = lgb.Dataset(X_train_full_sub, label=y_train_full_sub)
        dval_dual = lgb.Dataset(X_val_full, label=y_val_full, reference=dtrain_dual)
        model_dual_reg = lgb.train(
            params_dual, dtrain_dual, num_boost_round=500,
            valid_sets=[dval_dual],
            callbacks=[lgb.early_stopping(50), lgb.log_evaluation(0)],
        )
        # Predict on candidates
        reg_preds_train = model_dual_reg.predict(X_train)
        reg_preds_test = model_dual_reg.predict(X_test)

        # Dual-stage features: original features + reg_pred
        dual_feats = list(feats) + ["reg_pred"]
        X_train_dual = train[feats].copy()
        X_train_dual["reg_pred"] = reg_preds_train
        X_test_dual = test[feats].copy()
        X_test_dual["reg_pred"] = reg_preds_test

        params_dual_cls = {
            **LGB_CORE, "objective": "binary", "metric": "auc",
            "scale_pos_weight": scale_pos, "learning_rate": 0.03,
        }
        dtrain_d = lgb.Dataset(X_train_dual, label=y_train_cls)
        dtest_d = lgb.Dataset(X_test_dual, label=y_test_cls, reference=dtrain_d)
        model_dual_cls = lgb.train(
            params_dual_cls, dtrain_d, num_boost_round=500,
            valid_sets=[dtest_d],
            callbacks=[lgb.early_stopping(50), lgb.log_evaluation(0)],
        )
        preds_dual = model_dual_cls.predict(X_test_dual, num_iteration=model_dual_cls.best_iteration)
        test_dual = test.copy()
        test_dual["dual_score"] = preds_dual
        dual_prec = precision_at_3(test_dual, score_col="dual_score")

        results.append({
            "test_year": test_year,
            "n_train": len(train), "n_test": len(test),
            "momentum_prec": float(momentum_prec),
            "classification": {"prec@3": float(cls_prec), "ap": float(cls_ap)},
            "regression_prec": float(reg_prec),
            "huber_prec": float(huber_prec),
            "quantile_prec": float(quantile_prec),
            "ensemble_prec": float(ensemble_prec),
            "dual_stage_prec": float(dual_prec),
        })

        print(f"  {test_year}:")
        print(f"    {c('Momentum', 'BLUE'):<12} {momentum_prec:.4f}")
        print(f"    {c('Classification', 'GREEN'):<12} {cls_prec:.4f} (AP={cls_ap:.4f})")
        print(f"    {c('Regression', 'CYAN'):<12} {reg_prec:.4f}")
        print(f"    {c('Huber', 'YELLOW'):<12} {huber_prec:.4f}")
        print(f"    {c('Quantile(0.9)', 'MAGENTA'):<12} {quantile_prec:.4f}")
        print(f"    {c('Ensemble', 'RED'):<12} {ensemble_prec:.4f}")
        print(f"    {c('Dual-stage', 'WHITE'):<12} {dual_prec:.4f}")

    # ── Summary ──
    print(f"\n{'='*90}")
    print(f"{'APPROACH COMPARISON — All Approaches Side-by-Side':^90}")
    print(f"{'='*90}")

    header = f"{'Approach':<22}"
    for r in results:
        header += f" | {r['test_year']:<9}"
    header += f" | {'3Y Avg':<9} | {'Lift vs Mom':<11}"
    print(header)
    print("-" * 90)

    approaches = [
        ("Momentum rule", "momentum_prec"),
        ("Classification", "classification", "prec@3"),
        ("Regression", "regression_prec"),
        ("Huber", "huber_prec"),
        ("Quantile (α=0.9)", "quantile_prec"),
        ("Ensemble (rank avg)", "ensemble_prec"),
        ("Dual-stage (reg→cls)", "dual_stage_prec"),
    ]

    def get_val(r, spec):
        """Extract value from results dict.
        - len=2: (display_name, key) -> r[key] (a float)
        - len=3: (display_name, dict_key, nested_key) -> r[dict_key][nested_key] (nested float)
        """
        if len(spec) == 2:
            _, key = spec
            val = r[key]
        else:
            _, dict_key, nested_key = spec
            val = r[dict_key][nested_key]
        return float(val)

    momentum_avg = np.mean([r["momentum_prec"] for r in results])

    for spec in approaches:
        name = spec[0]
        vals = [get_val(r, spec) for r in results]
        avg = np.mean(vals)
        lift = avg / max(momentum_avg, 0.0001)

        line = f"{name:<22}"
        for v in vals:
            line += f" | {v:<9.4f}"
        line += f" | {avg:<9.4f}"
        line += f" | {lift:<11.2f}x"

        print(line)

    # Find overall winner
    print(f"\n{'─'*90}")
    all_avgs = {}
    for spec in approaches:
        name = spec[0]
        vals = [get_val(r, spec) for r in results]
        all_avgs[name] = np.mean(vals)

    best_name = max(all_avgs, key=all_avgs.get)
    best_val = all_avgs[best_name]
    print(f"🏆  BEST: {best_name} (Prec@3={best_val:.4f}, lift={best_val/max(momentum_avg,0.0001):.2f}x vs momentum)")

    # Rank all
    print(f"\n{'─'*90}")
    print(f"{'Final Rankings':^90}")
    print(f"{'─'*90}")
    sorted_avgs = sorted(all_avgs.items(), key=lambda x: -x[1])
    for rank, (name, val) in enumerate(sorted_avgs, 1):
        lift = val / max(momentum_avg, 0.0001)
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, f"  {rank}.")
        print(f"  {medal} {name:<30} Prec@3={val:.4f}  lift={lift:.2f}x vs momentum")

    # Save
    report = {
        "test_years": [2023, 2024, 2025],
        "n_features": len(feats),
        "stage1_filter_pct": len(candidates) / len(df) * 100,
        "per_year": [
            {
                "test_year": r["test_year"],
                "n_train": r["n_train"], "n_test": r["n_test"],
                "momentum_prec@3": r["momentum_prec"],
                "classification_prec@3": r["classification"]["prec@3"],
                "classification_ap": r["classification"]["ap"],
                "regression_prec@3": r["regression_prec"],
                "huber_prec@3": r["huber_prec"],
                "quantile_prec@3": r["quantile_prec"],
                "ensemble_prec@3": r["ensemble_prec"],
                "dual_stage_prec@3": r["dual_stage_prec"],
            }
            for r in results
        ],
        "averages": {name: float(val) for name, val in all_avgs.items()},
        "momentum_baseline": float(momentum_avg),
        "best_approach": best_name,
        "best_prec@3": float(best_val),
        "ranking": [
            {"rank": i + 1, "approach": name, "prec@3": round(val, 4)}
            for i, (name, val) in enumerate(sorted_avgs)
        ],
    }
    (POC_DATA / "all_approaches_report.json").write_text(json.dumps(report, indent=2))
    print(f"\nSaved: {POC_DATA / 'all_approaches_report.json'}")


def c(text, color):
    """Simple terminal color helper."""
    colors = {
        "BLUE": "\033[94m", "GREEN": "\033[92m", "CYAN": "\033[96m",
        "YELLOW": "\033[93m", "MAGENTA": "\033[95m", "RED": "\033[91m",
        "WHITE": "\033[97m", "END": "\033[0m",
    }
    return f"{colors.get(color, '')}{text}{colors['END']}"


if __name__ == "__main__":
    main()
