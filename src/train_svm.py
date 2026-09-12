"""
Step 5: Support Vector Machine.

    python -m src.train_svm

RBF kernel as the primary model, with a linear kernel fitted alongside for comparison.

Why RBF: the relationship between terrain and failure is not a straight line. Landslide risk
rises with slope up to roughly 30 to 40 degrees and then falls again on cliffs, where there is
no loose material left to fail. Risk also peaks in a middle elevation band rather than rising
forever. A linear kernel can only draw one flat boundary through the feature space, so it cannot
represent "high in the middle, low at both ends". The RBF kernel can. Fitting both is what turns
that claim into evidence.

Outputs:
    models/svm_model.pkl      best RBF estimator, refitted with probability estimates
    models/metadata.json      svm section: both grids, best parameters, CV scores, timings
"""
import sys
import time

import joblib
import numpy as np

from src import artifacts, config


def load_prepared():
    path = config.PROCESSED_DIR / "prepared.joblib"
    if not path.exists():
        raise SystemExit(f"{path} not found. Run `python -m src.preprocess` first.")
    return joblib.load(path)


def warn_about_size(n_train: int, n_features: int) -> dict:
    """Say what training will cost before it is paid, not after.

    An SVM solves a problem whose cost grows between the square and the cube of the number of
    training rows, because it works on pairwise distances. Doubling the data therefore multiplies
    the fitting time by roughly four, not two. Grid search multiplies that again by the number of
    combinations times the number of folds.
    """
    n_fits = len(config.SVM_RBF_PARAM_GRID["C"]) * len(config.SVM_RBF_PARAM_GRID["gamma"]) * config.CV_FOLDS
    print(f"Training set: {n_train:,} rows x {n_features} features")
    print(f"RBF grid search: {n_fits} fits ({n_fits // config.CV_FOLDS} combinations x {config.CV_FOLDS} folds)")
    note = ""
    if n_train > 20_000:
        note = ("Above about 20,000 training rows an RBF grid search can run for hours. "
                "Mitigations, in order: raise cache_size (2000), cut the grid to C=[1,10] and "
                "gamma=[0.1,0.01], use a stratified subsample for the search and refit the winner "
                "on everything, or switch the linear model to LinearSVC which scales linearly.")
        print(f"WARNING: {note}")
    elif n_train > 8_000:
        note = "Expect several minutes. Raise cache_size if it drags."
        print(f"Note: {note}")
    else:
        print("At this size the search takes well under a minute.")
    return {"n_train": int(n_train), "n_fits": int(n_fits), "scaling_note": note}


def build_pipeline(kernel: str, **svc_kwargs):
    """SMOTE and the classifier as one estimator, so resampling happens inside each CV fold.

    This detail decides whether the CV score means anything. SMOTE creates minority rows by
    interpolating between near neighbours. Resample the whole training set first and those
    synthetic rows get split across folds, so a validation fold holds points derived from rows
    the model just trained on. The CV score then measures memorisation.

    Measured on this project: resampling first gave CV 0.92 and test 0.69, and the search chose
    gamma=1, the most overfit setting in the grid. Inside the folds, CV and test agree.

    The saved artifact is still trained on the SMOTE-balanced training set, and the test set is
    never resampled, so the rule from the project plan holds exactly as written.
    """
    from imblearn.over_sampling import SMOTE
    from imblearn.pipeline import Pipeline
    from sklearn.svm import SVC

    return Pipeline([
        ("smote", SMOTE(sampling_strategy=config.SMOTE_SAMPLING_STRATEGY,
                        k_neighbors=config.SMOTE_K_NEIGHBORS, random_state=config.RANDOM_STATE)),
        ("svc", SVC(kernel=kernel, random_state=config.RANDOM_STATE, cache_size=1000, **svc_kwargs)),
    ])


def run_grid(kernel: str, grid: dict, X, y):
    from sklearn.model_selection import GridSearchCV, StratifiedKFold

    cv = StratifiedKFold(n_splits=config.CV_FOLDS, shuffle=True, random_state=config.RANDOM_STATE)
    search = GridSearchCV(
        build_pipeline(kernel),
        param_grid={f"svc__{k}": v for k, v in grid.items()},
        scoring=config.PRIMARY_CV_METRIC, cv=cv, n_jobs=config.N_JOBS, refit=True)
    started = time.perf_counter()
    search.fit(X, y)
    elapsed = time.perf_counter() - started
    best = {k.replace("svc__", ""): v for k, v in search.best_params_.items()}
    print(f"  {kernel}: best {config.PRIMARY_CV_METRIC} {search.best_score_:.4f} "
          f"with {best} in {elapsed:.1f}s")
    return search, best, elapsed


def top_results(search, n: int = 5) -> list[dict]:
    order = np.argsort(-search.cv_results_["mean_test_score"])[:n]
    return [{"params": {k.replace("svc__", ""): v for k, v in search.cv_results_["params"][i].items()},
             "mean_cv_auc": round(float(search.cv_results_["mean_test_score"][i]), 4),
             "std_cv_auc": round(float(search.cv_results_["std_test_score"][i]), 4)} for i in order]


def main() -> int:
    from sklearn.metrics import roc_auc_score
    from sklearn.svm import SVC

    print(config.data_source_banner())
    bundle = load_prepared()
    # Scaled but NOT resampled: SMOTE runs inside each fold, via the pipeline.
    X_train, y_train = bundle["X_train_unresampled"], bundle["y_train_unresampled"]
    X_test, y_test = bundle["X_test"], bundle["y_test"]          # scaled, never resampled
    size_note = warn_about_size(len(X_train), X_train.shape[1])

    print("\nGrid search (SMOTE applied inside every fold)")
    rbf_search, rbf_params, rbf_time = run_grid("rbf", config.SVM_RBF_PARAM_GRID, X_train, y_train)
    linear_search, linear_params, linear_time = run_grid("linear", config.SVM_LINEAR_PARAM_GRID,
                                                         X_train, y_train)

    # Held-out comparison. decision_function is enough for AUC and avoids the cost of probabilities.
    rbf_test_auc = roc_auc_score(y_test, rbf_search.best_estimator_.decision_function(X_test))
    linear_test_auc = roc_auc_score(y_test, linear_search.best_estimator_.decision_function(X_test))
    print(f"  CV vs test for RBF: {rbf_search.best_score_:.4f} vs {rbf_test_auc:.4f}. "
          f"A large gap here would mean leakage, not bad luck.")
    gain = rbf_test_auc - linear_test_auc
    print(f"\nTest AUC: RBF {rbf_test_auc:.4f} vs linear {linear_test_auc:.4f} ({gain:+.4f})")
    if gain > 0.01:
        print("  The RBF kernel earns its place: the terrain relationships are not straight lines.")
    else:
        print("  The RBF kernel adds little here. Report that honestly rather than assuming it wins;")
        print("  it means the factors separate the classes in a close to linear way in this dataset.")

    # Refit the winner with probability estimates, which the dashboard and the risk map need.
    # SVC does this with internal cross-validation (Platt scaling), so it costs a few extra fits;
    # that is why it is done once here rather than during the search.
    print("\nRefitting the best RBF model with probability estimates")
    started = time.perf_counter()
    final_pipeline = build_pipeline("rbf", probability=True, **rbf_params).fit(X_train, y_train)
    # Save the classifier itself, not the pipeline: it is already trained on the SMOTE-balanced
    # training set, and Phase 2 promises a plain estimator that takes scaled features.
    final = final_pipeline.named_steps["svc"]
    refit_time = time.perf_counter() - started
    print(f"  done in {refit_time:.1f}s")

    config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(final, config.SVM_MODEL_PATH)
    artifacts.update_metadata("svm", {
        "kernel": "rbf",
        "best_params": rbf_params,
        "smote_inside_cv": True,
        "cv_folds": config.CV_FOLDS,
        "cv_metric": config.PRIMARY_CV_METRIC,
        "best_cv_auc": round(float(rbf_search.best_score_), 4),
        "test_auc": round(float(rbf_test_auc), 4),
        "top_rbf_results": top_results(rbf_search),
        "linear_comparison": {
            "best_params": linear_params,
            "best_cv_auc": round(float(linear_search.best_score_), 4),
            "test_auc": round(float(linear_test_auc), 4),
            "rbf_minus_linear_test_auc": round(float(gain), 4),
        },
        "timing_seconds": {"rbf_grid": round(rbf_time, 1), "linear_grid": round(linear_time, 1),
                           "probability_refit": round(refit_time, 1)},
        "training_size": size_note,
        "probability_estimates": True,
    })
    print(f"\nSaved {config.SVM_MODEL_PATH.relative_to(config.ROOT)}")
    print("Next: python -m src.train_rf")
    return 0


if __name__ == "__main__":
    # The main guard is required on Windows: n_jobs=-1 starts worker processes that re-import
    # this file, and without the guard each worker would start its own grid search.
    sys.exit(main())
