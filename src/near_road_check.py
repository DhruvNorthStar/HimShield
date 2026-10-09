"""
How much of the test AUC comes from GSI's road-corridor survey pattern?

    python -m src.near_road_check            (after src.evaluate)

Why: at the real points the median distance to a road is 30 m for landslides and 1,154 m for stable
points, and dist_roads is Random Forest's strongest feature. A model can then score well partly by
answering "is this near a road?". This splits the held-out test set by distance to the nearest road and
measures AUC in each part separately. Inside one part that shortcut is much weaker, so the AUC there is
closer to how well the models rank terrain. Nothing is retrained; the models and test rows are exactly
the ones src.evaluate scored. Results go to models/metadata.json under near_road_check.
"""
import sys

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from src import artifacts, config
from src.evaluate import bootstrap_auc_difference, risk_scores

ROAD_SPLIT_M = 1000
BOOTSTRAP_ROUNDS = 1000


def auc_interval(y: np.ndarray, s: np.ndarray, rounds: int = BOOTSTRAP_ROUNDS) -> tuple[float, float]:
    """95% bootstrap interval for one model's AUC on one subset."""
    rng = np.random.default_rng(config.RANDOM_STATE)
    values = []
    for _ in range(rounds):
        idx = rng.integers(0, len(y), len(y))
        if len(np.unique(y[idx])) == 2:
            values.append(roc_auc_score(y[idx], s[idx]))
    return float(np.percentile(values, 2.5)), float(np.percentile(values, 97.5))


def main() -> int:
    print(config.data_source_banner())
    bundle = joblib.load(config.PROCESSED_DIR / "prepared.joblib")
    X_test, y_test = bundle["X_test"], bundle["y_test"]
    models = {"SVM (RBF)": joblib.load(config.SVM_MODEL_PATH), "Random Forest": joblib.load(config.RF_MODEL_PATH)}
    if config.XGB_MODEL_PATH.exists():  # Phase 3 extension; absent on the Phase 2 branch
        models["XGBoost"] = joblib.load(config.XGB_MODEL_PATH)

    # The test rows keep their row numbers from dataset.csv (preprocess only drops rows, never renumbers),
    # so the unscaled distance comes straight from the CSV.
    raw = pd.read_csv(config.DATASET_CSV)
    dist = raw.loc[X_test.index, "dist_roads"].to_numpy()
    scaler = joblib.load(config.SCALER_PATH)
    col = list(bundle["feature_names"]).index("dist_roads")
    rebuilt = X_test["dist_roads"].to_numpy() * scaler.scale_[col] + scaler.mean_[col]
    if not np.allclose(rebuilt, dist, atol=0.05):
        raise SystemExit("Test rows do not line up with dataset.csv; rerun src.preprocess first.")

    y = y_test.to_numpy()
    scores = {name: risk_scores(model, X_test) for name, model in models.items()}
    subsets = {
        "all test points": np.ones(len(y), dtype=bool),
        f"within {ROAD_SPLIT_M} m of a road": dist <= ROAD_SPLIT_M,
        f"beyond {ROAD_SPLIT_M} m": dist > ROAD_SPLIT_M,
    }
    results = {}
    print(f"\nTest set split at {ROAD_SPLIT_M} m from the nearest OSM road\n")
    print(f"  {'subset':<26}{'rows':>6}{'landslide':>10}{'stable':>8}   {'SVM AUC (95%)':<24}{'RF AUC (95%)':<24}RF - SVM (95%)")
    for label, mask in subsets.items():
        yy = y[mask]
        row = {"rows": int(mask.sum()), "landslide": int(yy.sum()), "stable": int((yy == 0).sum())}
        cells = []
        for name in models:
            auc = float(roc_auc_score(yy, scores[name][mask]))
            low, high = auc_interval(yy, scores[name][mask])
            row[name] = {"auc": round(auc, 4), "ci_low": round(low, 4), "ci_high": round(high, 4)}
            cells.append(f"{auc:.4f} ({low:.3f}-{high:.3f})")
        diff = bootstrap_auc_difference(yy, scores["SVM (RBF)"][mask], scores["Random Forest"][mask])
        row["rf_minus_svm"] = diff
        if "XGBoost" in models:
            row["xgb_minus_rf"] = bootstrap_auc_difference(yy, scores["Random Forest"][mask], scores["XGBoost"][mask])
        results[label] = row
        print(f"  {label:<26}{row['rows']:>6,}{row['landslide']:>10,}{row['stable']:>8,}   {cells[0]:<24}{cells[1]:<24}"
              f"{diff['mean_difference']:+.4f} ({diff['ci_low']:+.4f} to {diff['ci_high']:+.4f})")
        if "XGBoost" in models:
            x = row["xgb_minus_rf"]
            print(f"  {'':<26}{'':>6}{'':>10}{'':>8}   XGBoost AUC {cells[2]}   XGB - RF {x['mean_difference']:+.4f} "
                  f"({x['ci_low']:+.4f} to {x['ci_high']:+.4f})")

    artifacts.update_metadata("near_road_check", {
        "split_m": ROAD_SPLIT_M, "road_source": "OpenStreetMap, dist_roads.tif",
        "bootstrap_rounds": BOOTSTRAP_ROUNDS, "subsets": results,
    })
    print("\nSaved to models/metadata.json (near_road_check)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
