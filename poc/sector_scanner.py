"""Sector Rotation Scanner — test if sector-awareness improves top-gainer selection.

Strategies tested:
  1. Naive momentum (baseline): top 3 by ret_30m from full universe
  2. Meta-label momentum: Stage 1 filter + top 3 by ret_30m (best so far)
  3. Sector momentum: top 3 stocks from the single strongest sector
  4. Sector diversification: 1 stock from each of top 3 leading sectors
  5. Sector combo: top 3 by combined score (momentum + sector rank)
  6. ML with sector features: Stage 1 filter + LightGBM (including sector features)
"""

from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score
try:
    import lightgbm as lgb
except ImportError:
    lgb = None

PROJECT_ROOT = Path(__file__).resolve().parent.parent
POC_DATA = PROJECT_ROOT / "poc" / "data"
LABELS_PATH = POC_DATA / "labels.parquet"

# Load both feature sets
FEATURES_PATHS = {
    "full": POC_DATA / "features.parquet",
    "sector": POC_DATA / "features_with_sector.parquet",
}

SECTOR_FEATURES = [
    "ret_30m", "range_30m", "rvol", "vol_surge", "obv_delta",
    "gap_up_pct", "rsi_14", "mom_5d", "mom_10d", "mom_20d",
    "rel_strength_30m", "rel_strength_5d",
    "rank_ret_30m", "rank_gap_up", "rank_rvol",
    "rank_rel_strength", "rank_range", "rank_mom_5d",
    "avg_vol_30m", "vol_10d", "vol_20d", "atr_ratio",
    "nifty_ret_30m", "nifty_mom_5d", "nifty_mom_10d",
    "prev_day_direction", "daily_vol_ratio", "vol_trend",
    "avg_range_10d", "prev_day_ret",
    "sector_mom_30m", "sector_rvol", "sector_beats_nifty_pct",
    "sector_mom_5d", "sector_rank_mom", "sector_rank_vol",
    "sector_rank_combined", "is_leading_sector",
    "ret_deviation_from_sector",
]


def load_data(features_path: str = "full") -> pd.DataFrame:
    path = FEATURES_PATHS[features_path]
    df = pd.read_parquet(path)
    labels = pd.read_parquet(LABELS_PATH)
    df["date"] = pd.to_datetime(df["date"])
    labels["date"] = pd.to_datetime(labels["date"])
    df = df.merge(labels[["symbol", "date", "return_pct"]], on=["symbol", "date"], how="inner")
    df["is_top_gainer"] = 0
    for date, day_df in df.groupby("date"):
        if len(day_df) < 3:
            continue
        df.loc[day_df.nlargest(3, "return_pct").index, "is_top_gainer"] = 1
    df["year"] = df["date"].dt.year
    return df


def precision_at_3(df: pd.DataFrame, score_col: str) -> float:
    """Average Precision@3 across all days."""
    precisions = []
    for _, day_df in df.groupby("date"):
        if len(day_df) < 3:
            continue
        picks = day_df.nlargest(3, score_col)
        precisions.append(picks["is_top_gainer"].sum() / 3.0)
    return float(np.mean(precisions)) if precisions else 0.0


def run_strategies(df_full: pd.DataFrame, df_sector: pd.DataFrame, test_year: int) -> dict:
    """Run all strategies and compare them on the same test period."""
    full_test = df_full[df_full["year"] == test_year]
    sec_test = df_sector[df_sector["year"] == test_year]

    results = {"test_year": test_year, "dates": int(full_test["date"].nunique())}

    # ── Strategy 1: Naive momentum (full universe, no filter) ──
    results["naive_momentum_prec3"] = precision_at_3(full_test, score_col="ret_30m")

    # ── Strategy 2: Meta-label momentum (Stage 1 filter + ret_30m) ──
    candidates = full_test[
        (full_test["ret_30m"] > 1.0) &
        (full_test["rvol"] > 1.5) &
        (full_test["beats_nifty_30m"] == 1)
    ]
    results["meta_momentum_prec3"] = precision_at_3(candidates, score_col="ret_30m")

    # Random baseline on candidates
    random_vals = []
    for _, day_df in candidates.groupby("date"):
        if len(day_df) < 3:
            continue
        picks = day_df.sample(min(3, len(day_df)))
        random_vals.append(picks["is_top_gainer"].sum() / 3.0)
    results["random_prec3"] = float(np.mean(random_vals)) if random_vals else 0

    # ── Strategy 3: Sector top-3 (pick 3 from strongest sector) ──
    results["sector_top3_prec3"] = _strategy_sector_top3(sec_test)

    # ── Strategy 4: Sector diversify (1 from each top-3 sector) ──
    results["sector_diversify_prec3"] = _strategy_sector_diversify(sec_test)

    # ── Strategy 5: Sector combo (momentum + sector rank) ──
    results["sector_combo_prec3"] = _strategy_sector_combo(sec_test)

    # ── Strategy 6: ML on candidates with sector features ──
    results.update(_run_ml_with_sector(df_sector, test_year))

    return results


def _strategy_sector_top3(df: pd.DataFrame) -> float:
    """Pick top 3 stocks from the single strongest sector (by avg ret_30m)."""
    precisions = []
    for date, day_df in df.groupby("date"):
        if len(day_df) < 3:
            continue
        known = day_df[day_df["sector"] != "Unknown"]
        if known.empty:
            continue
        sector_mom = known.groupby("sector")["ret_30m"].mean()
        if sector_mom.empty:
            continue
        best_sector = sector_mom.idxmax()
        sector_stocks = known[known["sector"] == best_sector]
        if len(sector_stocks) < 1:
            continue
        # Pick up to 3, pad if needed by taking from the full known set
        picks = sector_stocks.nlargest(min(3, len(sector_stocks)), "ret_30m")
        if len(picks) < 3:
            # Fill remaining from other stocks with best ret_30m
            remaining = known.drop(picks.index)
            if not remaining.empty:
                extra = remaining.nlargest(3 - len(picks), "ret_30m")
                picks = pd.concat([picks, extra])
        precisions.append(picks["is_top_gainer"].sum() / 3.0)
    return float(np.mean(precisions)) if precisions else 0.0


def _strategy_sector_diversify(df: pd.DataFrame) -> float:
    """Pick 1 stock from each of top 3 sectors by avg morning momentum."""
    precisions = []
    for date, day_df in df.groupby("date"):
        if len(day_df) < 3:
            continue
        known = day_df[day_df["sector"] != "Unknown"]
        if len(known) < 3:
            continue
        sector_mom = known.groupby("sector")["ret_30m"].mean()
        if len(sector_mom) < 3:
            continue
        top3_sectors = sector_mom.nlargest(3).index.tolist()
        picks = []
        used_indices = set()
        for sec in top3_sectors:
            sec_stocks = known[known["sector"] == sec]
            if not sec_stocks.empty:
                best = sec_stocks.nlargest(1, "ret_30m")
                picks.append(best.iloc[0])
                used_indices.add(best.index[0])
        if len(picks) < 3:
            # Fill from remaining known stocks
            remaining = known.drop(list(used_indices)).nlargest(3 - len(picks), "ret_30m")
            picks.extend([row for _, row in remaining.iterrows()])
        picks_df = pd.DataFrame(picks)
        precisions.append(picks_df["is_top_gainer"].sum() / 3.0)
    return float(np.mean(precisions)) if precisions else 0.0


def _strategy_sector_combo(df: pd.DataFrame) -> float:
    """Combined score = stock momentum (60%) + sector leadership (40%)."""
    precisions = []
    for date, day_df in df.groupby("date"):
        if len(day_df) < 3:
            continue
        known = day_df[day_df["sector"] != "Unknown"].copy()
        if len(known) < 3:
            continue

        # Sector leadership: how well is this stock's sector doing?
        # Use sector_rank_combined (lower=better), invert to 0-1 score
        max_rank = known["sector_rank_combined"].max()
        if max_rank > 0:
            known["sector_leadership"] = 1.0 - (known["sector_rank_combined"] / max_rank)
        else:
            known["sector_leadership"] = 0.0

        # Stock momentum rank (0-1)
        known["mom_rank"] = known["ret_30m"].rank(pct=True)

        # Combined: 60% stock momentum, 40% sector leadership
        known["combo_score"] = known["mom_rank"] * 0.6 + known["sector_leadership"] * 0.4

        picks = known.nlargest(3, "combo_score")
        precisions.append(picks["is_top_gainer"].sum() / 3.0)
    return float(np.mean(precisions)) if precisions else 0.0


def _run_ml_with_sector(df: pd.DataFrame, test_year: int) -> dict:
    """Meta-label Stage 1 + LightGBM with sector features."""
    if lgb is None:
        return {"ml_prec3": 0, "ml_ap": 0}

    candidates = df[
        (df["ret_30m"] > 1.0) &
        (df["rvol"] > 1.5) &
        (df["beats_nifty_30m"] == 1)
    ]

    train = candidates[candidates["year"].between(test_year - 2, test_year - 1)]
    test = candidates[candidates["year"] == test_year]

    if len(train) < 100 or len(test) < 30:
        return {"ml_prec3": 0, "ml_ap": 0, "ml_top_features": []}

    feats = [f for f in SECTOR_FEATURES if f in candidates.columns]
    train = train.dropna(subset=feats)
    test = test.dropna(subset=feats)

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
    test_ml = test.copy()
    test_ml["ml_score"] = preds

    importance = pd.DataFrame({
        "feature": feats,
        "gain": model.feature_importance(importance_type="gain"),
    }).sort_values("gain", ascending=False)

    return {
        "ml_prec3": precision_at_3(test_ml, score_col="ml_score"),
        "ml_ap": float(average_precision_score(y_test, preds)),
        "ml_top_features": [
            {"feature": r["feature"], "gain": float(r["gain"])}
            for _, r in importance.head(10).iterrows()
        ],
    }


def main() -> None:
    print("Loading full features...")
    df_full = load_data("full")
    print(f"Full: {len(df_full):,} rows, {df_full['date'].nunique()} days")

    print("\nLoading sector features...")
    df_sector = load_data("sector")
    print(f"Sector: {len(df_sector):,} rows, sector coverage: {(df_sector['sector'] != 'Unknown').mean()*100:.1f}%")

    print(f"\nTarget rate: {df_full['is_top_gainer'].mean()*100:.2f}%")
    print()

    all_results = []
    for test_year in [2023, 2024, 2025]:
        result = run_strategies(df_full, df_sector, test_year)
        all_results.append(result)

        print(f"  ── {test_year} ({result['dates']} days) ──")
        print(f"    Random:                 {result['random_prec3']:.4f}")
        print(f"    Naive momentum:         {result['naive_momentum_prec3']:.4f}  (full universe)")
        print(f"    Meta-label momentum:    {result['meta_momentum_prec3']:.4f}  (Stage 1 + ret_30m)")
        print(f"    Sector top-3:           {result['sector_top3_prec3']:.4f}  (from strongest sector)")
        print(f"    Sector diversify:       {result['sector_diversify_prec3']:.4f}  (1 per top-3 sectors)")
        print(f"    Sector combo:           {result['sector_combo_prec3']:.4f}  (mom + sector rank)")
        print(f"    ML with sectors:        {result['ml_prec3']:.4f}  (AP: {result['ml_ap']:.4f})")

    # Summary
    print(f"\n{'='*70}")
    print(f"  SECTOR ROTATION SCANNER — SUMMARY (avg 2023-2025)")
    print(f"{'='*70}")
    metrics = [
        ("random_prec3", "Random"),
        ("naive_momentum_prec3", "Naive momentum"),
        ("meta_momentum_prec3", "Meta-label momentum"),
        ("sector_top3_prec3", "Sector top-3"),
        ("sector_diversify_prec3", "Sector diversify"),
        ("sector_combo_prec3", "Sector combo"),
        ("ml_prec3", "ML with sectors"),
    ]
    best_name, best_val = "", 0
    for metric, name in metrics:
        vals = [r.get(metric, 0) for r in all_results if r.get(metric) is not None]
        avg = float(np.mean(vals)) if vals else 0
        if avg > best_val:
            best_val, best_name = avg, name
        print(f"  {name:25s}: {avg:.4f}")

    # Lift vs naive momentum
    naive_avg = float(np.mean([r["naive_momentum_prec3"] for r in all_results]))
    print(f"\n  Lift vs naive momentum:")
    for metric, name in [
        ("meta_momentum_prec3", "Meta-label momentum"),
        ("sector_top3_prec3", "Sector top-3"),
        ("sector_diversify_prec3", "Sector diversify"),
        ("sector_combo_prec3", "Sector combo"),
        ("ml_prec3", "ML with sectors"),
    ]:
        vals = [r.get(metric, 0) for r in all_results if r.get(metric) is not None]
        avg = float(np.mean(vals)) if vals else 0
        if naive_avg > 0:
            lift = avg / naive_avg
            print(f"    {name:25s}: {avg:.4f} ({lift:.2f}x naive)")

    print(f"\n  🏆 Best: {best_name} ({best_val:.4f})")

    # Show top ML features
    print(f"\n  Top sector ML features (all years):")
    feature_scores = {}
    for r in all_results:
        for feat in r.get("ml_top_features", []):
            feature_scores[feat["feature"]] = feature_scores.get(feat["feature"], 0) + feat["gain"]
    sorted_feats = sorted(feature_scores.items(), key=lambda x: -x[1])
    for feat, gain in sorted_feats[:10]:
        print(f"    {feat:30s}: {gain:.1f}")

    report = {"method": "sector_rotation_scanner", "results": all_results}
    report_path = POC_DATA / "sector_scanner_report.json"
    report_path.write_text(json.dumps(report, indent=2))
    print(f"\nSaved: {report_path}")


if __name__ == "__main__":
    main()
