"""
Phase 3 extension: XGBoost as a third model.

    python -m src.train_xgboost

Gradient-boosted trees: each new tree fits the errors the trees before it still make, so the ensemble
improves step by step instead of averaging independent trees as a Random Forest does. It is the strongest
model in Chauhan et al. (2025) (test AUC 91.36% against their Random Forest's 90.94%), which is why it is
worth adding here, on this project's own protocol.

Same protocol as SVM and Random Forest, so the three AUCs are comparable: the saved split in
data/processed/prepared.joblib, scaled training rows without resampling, SMOTE inside each CV fold,
stratified 5-fold grid search on ROC AUC, seed 42. The grid (config.XGB_PARAM_GRID) was fixed before any
XGBoost run.

Outputs:
    models/xgb_model.pkl                          best estimator
    models/metadata.json                          xgb section: grid, best parameters, CV and test AUC
    outputs/figures/xgb_feature_importance.png    gain and permutation importance
"""
import sys
import time

import joblib
import pandas as pd

from src import artifacts, config, viz
from src.train_rf import load_prepared


def plot_importance(gain: pd.Series, permutation: pd.Series, top_n: int = 15):
    """Gain importance (from training) next to permutation importance (on the test set), as for the forest."""
    import matplotlib.pyplot as plt

    gain = gain.sort_values(ascending=False).head(top_n)[::-1]
    permutation = permutation.reindex(gain.index)
    fig, axes = plt.subplots(1, 2, figsize=(11, 0.36 * len(gain) + 2), sharey=True)
    axes[0].barh(gain.index, gain.to_numpy(), color=viz.STABLE, height=0.6)
    axes[0].set_title("Gain importance (from training)")
    axes[0].set_xlabel("share of total gain")
    axes[1].barh(permutation.index, permutation.to_numpy(), color=viz.LANDSLIDE, height=0.6)
    axes[1].set_title("Permutation importance (on the test set)")
    axes[1].set_xlabel("drop in AUC when the feature is shuffled")
    for ax in axes:
        ax.grid(axis="y", visible=False)
    fig.suptitle(f"What XGBoost relies on (top {top_n})", x=0.01, ha="left", fontsize=12, fontweight="semibold")
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    return fig


def main() -> int:
    from imblearn.over_sampling import SMOTE
    from imblearn.pipeline import Pipeline
    from sklearn.inspection import permutation_importance
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import GridSearchCV, StratifiedKFold
    from xgboost import XGBClassifier, __version__ as xgb_version

    print(config.data_source_banner())
    viz.apply_style()
    bundle = load_prepared()
    # Scaled but not resampled: SMOTE runs inside each CV fold, exactly as for SVM and Random Forest.
    X_train, y_train = bundle["X_train_unresampled"], bundle["y_train_unresampled"]
    X_test, y_test = bundle["X_test"], bundle["y_test"]
    features = bundle["feature_names"]

    combinations = 1
    for values in config.XGB_PARAM_GRID.values():
        combinations *= len(values)
    print(f"XGBoost {xgb_version}")
    print(f"Training set: {len(X_train):,} rows x {len(features)} features")
    print(f"Grid search: {combinations * config.CV_FOLDS} fits ({combinations} combinations x {config.CV_FOLDS} folds)")

    cv = StratifiedKFold(n_splits=config.CV_FOLDS, shuffle=True, random_state=config.RANDOM_STATE)
    pipeline = Pipeline([
        ("smote", SMOTE(sampling_strategy=config.SMOTE_SAMPLING_STRATEGY,
                        k_neighbors=config.SMOTE_K_NEIGHBORS, random_state=config.RANDOM_STATE)),
        # One thread per fit: the grid search already runs config.N_JOBS fits side by side, and letting each
        # XGBoost fit use every core as well would oversubscribe the 4-thread laptop.
        ("xgb", XGBClassifier(objective="binary:logistic", eval_metric="logloss", tree_method="hist",
                              random_state=config.RANDOM_STATE, n_jobs=1)),
    ])
    search = GridSearchCV(
        pipeline, param_grid={f"xgb__{k}": v for k, v in config.XGB_PARAM_GRID.items()},
        scoring=config.PRIMARY_CV_METRIC, cv=cv, n_jobs=config.N_JOBS, refit=True)
    started = time.perf_counter()
    search.fit(X_train, y_train)
    elapsed = time.perf_counter() - started
    best = search.best_estimator_.named_steps["xgb"]
    best_params = {k.replace("xgb__", ""): v for k, v in search.best_params_.items()}
    print(f"\nBest {config.PRIMARY_CV_METRIC} {search.best_score_:.4f} with {best_params} in {elapsed:.1f}s")

    test_auc = roc_auc_score(y_test, best.predict_proba(X_test)[:, 1])
    print(f"Test AUC {test_auc:.4f}   (CV {search.best_score_:.4f}; a wide gap would mean leakage)")
    edges = [k for k, v in best_params.items() if v in (config.XGB_PARAM_GRID[k][0], config.XGB_PARAM_GRID[k][-1])
             and len(config.XGB_PARAM_GRID[k]) > 2]
    if edges:
        print(f"  On the edge of the grid: {', '.join(f'{k}={best_params[k]}' for k in edges)}. "
              f"State it as a limitation; the grid is not widened after seeing results.")

    print("\nFeature importance")
    gain = pd.Series(best.get_booster().get_score(importance_type="gain"), dtype=float).reindex(features).fillna(0.0)
    gain = gain / gain.sum()
    perm = permutation_importance(best, X_test, y_test, n_repeats=10, random_state=config.RANDOM_STATE,
                                  scoring="roc_auc", n_jobs=config.N_JOBS)
    permutation = pd.Series(perm.importances_mean, index=features)
    for name, value in permutation.sort_values(ascending=False).head(5).items():
        print(f"  {name:<28} permutation {value:+.4f}   gain share {gain[name]:.4f}")
    figure_path = viz.save_fig(plot_importance(gain, permutation), "xgb_feature_importance")
    print(f"  {figure_path.relative_to(config.ROOT)}")

    config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(best, config.XGB_MODEL_PATH)
    artifacts.update_metadata("xgb", {
        "library": f"xgboost {xgb_version}",
        "best_params": {k: v for k, v in best_params.items()},
        "fixed_params": {"objective": "binary:logistic", "eval_metric": "logloss", "tree_method": "hist",
                         "random_state": config.RANDOM_STATE},
        "smote_inside_cv": True,
        "cv_folds": config.CV_FOLDS,
        "cv_metric": config.PRIMARY_CV_METRIC,
        "best_cv_auc": round(float(search.best_score_), 4),
        "test_auc": round(float(test_auc), 4),
        "grid": {k: [str(v) for v in vals] for k, vals in config.XGB_PARAM_GRID.items()},
        "grid_edges_hit": edges,
        "timing_seconds": {"grid_search": round(elapsed, 1)},
        "feature_importance_gain_share": {k: round(float(v), 5) for k, v in gain.sort_values(ascending=False).items()},
        "feature_importance_permutation": {k: round(float(v), 5) for k, v in
                                           permutation.sort_values(ascending=False).items()},
    })
    print(f"\nSaved {config.XGB_MODEL_PATH.relative_to(config.ROOT)}")
    print("Next: python -m src.evaluate")
    return 0


if __name__ == "__main__":
    # Required on Windows: n_jobs=-1 spawns workers that re-import this module.
    sys.exit(main())
