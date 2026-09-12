"""
Step 6: Random Forest.

    python -m src.train_rf

A forest of decision trees, each grown on a bootstrap sample of the rows and choosing splits
from a random subset of the features. Averaging many decorrelated trees cancels out the
overfitting a single deep tree would suffer.

Why it suits this problem: it handles non-linear thresholds naturally (a split at "slope > 32"
is exactly the shape terrain failure takes), it needs no scaling, it copes with features on wildly
different units (degrees, metres, mm), and it reports which factors it relied on, which is what
the report needs.

Outputs:
    models/rf_model.pkl                          best estimator
    models/metadata.json                         rf section: grid, best parameters, CV scores
    outputs/figures/rf_feature_importance.png    what the forest used, two ways of measuring
"""
import sys
import time

import joblib
import numpy as np
import pandas as pd

from src import artifacts, config, viz


def load_prepared():
    path = config.PROCESSED_DIR / "prepared.joblib"
    if not path.exists():
        raise SystemExit(f"{path} not found. Run `python -m src.preprocess` first.")
    return joblib.load(path)


def plot_importance(impurity: pd.Series, permutation: pd.Series, top_n: int = 15):
    """Two honest views of importance, side by side.

    Impurity importance counts how much each feature reduced impurity while the trees were built.
    It is free but biased: it favours features with many possible split points, so continuous
    columns look stronger than one-hot dummies simply because there are more places to cut.

    Permutation importance shuffles one feature in the held-out test set and measures how much
    the score falls. It is slower but asks the question we actually care about: how much does the
    model need this feature to work on data it has never seen?
    """
    import matplotlib.pyplot as plt

    impurity = impurity.sort_values(ascending=False).head(top_n)[::-1]
    permutation = permutation.reindex(impurity.index)

    fig, axes = plt.subplots(1, 2, figsize=(11, 0.36 * len(impurity) + 2), sharey=True)
    axes[0].barh(impurity.index, impurity.to_numpy(), color=viz.STABLE, height=0.6)
    axes[0].set_title("Impurity importance (from training)")
    axes[0].set_xlabel("mean decrease in impurity")
    axes[1].barh(permutation.index, permutation.to_numpy(), color=viz.LANDSLIDE, height=0.6)
    axes[1].set_title("Permutation importance (on the test set)")
    axes[1].set_xlabel("drop in AUC when the feature is shuffled")
    for ax in axes:
        ax.grid(axis="y", visible=False)
    fig.suptitle(f"What the Random Forest relies on (top {top_n})", x=0.01, ha="left",
                 fontsize=12, fontweight="semibold")
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    return fig


def main() -> int:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.inspection import permutation_importance
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import GridSearchCV, StratifiedKFold

    print(config.data_source_banner())
    viz.apply_style()
    bundle = load_prepared()
    # Scaled but NOT resampled: SMOTE runs inside each CV fold, through the pipeline below.
    # Resampling before the search lets synthetic rows built from one fold land in another, so
    # the CV score measures memorisation. Measured on the SVM here: 0.92 CV against 0.69 test.
    X_train, y_train = bundle["X_train_unresampled"], bundle["y_train_unresampled"]
    X_test, y_test = bundle["X_test"], bundle["y_test"]
    features = bundle["feature_names"]

    combinations = (len(config.RF_PARAM_GRID["n_estimators"]) * len(config.RF_PARAM_GRID["max_depth"])
                    * len(config.RF_PARAM_GRID["min_samples_split"]))
    print(f"Training set: {len(X_train):,} rows x {len(features)} features")
    print(f"Grid search: {combinations * config.CV_FOLDS} fits "
          f"({combinations} combinations x {config.CV_FOLDS} folds)")

    from imblearn.over_sampling import SMOTE
    from imblearn.pipeline import Pipeline

    cv = StratifiedKFold(n_splits=config.CV_FOLDS, shuffle=True, random_state=config.RANDOM_STATE)
    pipeline = Pipeline([
        ("smote", SMOTE(sampling_strategy=config.SMOTE_SAMPLING_STRATEGY,
                        k_neighbors=config.SMOTE_K_NEIGHBORS, random_state=config.RANDOM_STATE)),
        ("rf", RandomForestClassifier(random_state=config.RANDOM_STATE, n_jobs=1)),
    ])
    search = GridSearchCV(
        pipeline, param_grid={f"rf__{k}": v for k, v in config.RF_PARAM_GRID.items()},
        scoring=config.PRIMARY_CV_METRIC, cv=cv, n_jobs=config.N_JOBS, refit=True)
    started = time.perf_counter()
    search.fit(X_train, y_train)
    elapsed = time.perf_counter() - started
    best = search.best_estimator_.named_steps["rf"]
    best_params = {k.replace("rf__", ""): v for k, v in search.best_params_.items()}
    print(f"\nBest {config.PRIMARY_CV_METRIC} {search.best_score_:.4f} with {best_params} "
          f"in {elapsed:.1f}s")

    test_auc = roc_auc_score(y_test, best.predict_proba(X_test)[:, 1])
    print(f"Test AUC {test_auc:.4f}   (CV {search.best_score_:.4f}; a wide gap would mean leakage)")
    if best_params["max_depth"] is None:
        print("  Best depth is unlimited, so trees grow until the leaves are pure. That is normal for a")
        print("  forest: bagging plus random feature choice keeps the average from overfitting.")

    print("\nFeature importance")
    impurity = pd.Series(best.feature_importances_, index=features)
    perm = permutation_importance(best, X_test, y_test, n_repeats=10,
                                  random_state=config.RANDOM_STATE, scoring="roc_auc", n_jobs=config.N_JOBS)
    permutation = pd.Series(perm.importances_mean, index=features)
    top = impurity.sort_values(ascending=False).head(5)
    for name, value in top.items():
        print(f"  {name:<28} impurity {value:.4f}   permutation {permutation[name]:+.4f}")

    figure_path = viz.save_fig(plot_importance(impurity, permutation), "rf_feature_importance")
    print(f"  {figure_path.relative_to(config.ROOT)}")

    config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(best, config.RF_MODEL_PATH)
    artifacts.update_metadata("rf", {
        "best_params": {k: (v if v is not None else "None") for k, v in best_params.items()},
        "smote_inside_cv": True,
        "cv_folds": config.CV_FOLDS,
        "cv_metric": config.PRIMARY_CV_METRIC,
        "best_cv_auc": round(float(search.best_score_), 4),
        "test_auc": round(float(test_auc), 4),
        "grid": {k: [str(v) for v in vals] for k, vals in config.RF_PARAM_GRID.items()},
        "timing_seconds": {"grid_search": round(elapsed, 1)},
        "feature_importance_impurity": {k: round(float(v), 5) for k, v in
                                        impurity.sort_values(ascending=False).items()},
        "feature_importance_permutation": {k: round(float(v), 5) for k, v in
                                           permutation.sort_values(ascending=False).items()},
    })
    print(f"\nSaved {config.RF_MODEL_PATH.relative_to(config.ROOT)}")
    print("Next: python -m src.evaluate")
    return 0


if __name__ == "__main__":
    # Required on Windows: n_jobs=-1 spawns workers that re-import this module.
    sys.exit(main())
