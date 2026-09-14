"""
Phase 3: explain the Random Forest with SHAP.

    python -m src.explain_shap                     up to 500 held-out test points (default)
    python -m src.explain_shap --max-samples 200   a smaller sample
    python -m src.explain_shap --yes               continue even if the estimate is over 5 minutes

Why SHAP, and why these choices (the questions a viva will ask):
- Feature importance says which factors the forest leans on overall. SHAP says, for each location, how far
  each factor pushed its landslide score up or down from the average score. The contributions add up
  exactly to the model's own score, and this script checks that they do.
- Random Forest only. TreeExplainer computes exact SHAP values for tree models quickly. The RBF SVM would
  need KernelExplainer, which is approximate and would take hours at this size.
- Exact tree-path mode with no background sample: the explainer uses how many training rows went down each
  branch, so there is no background-set choice to defend.
- The held-out test set, never the SMOTE-balanced training rows, so explanations describe the real class
  mix rather than interpolated points. At most 500 points, stratified by class, seed 42.
- SHAP values are computed on the scaled inputs the model actually sees, but every plot shows real units
  (degrees, mm, metres) by pairing those values with the unscaled inputs.

Outputs (outputs/figures/shap/, ignored by git on the phase3-preparation branch):
    shap_beeswarm.png                  every sampled point, every top factor
    shap_bar.png                       mean absolute SHAP per factor
    shap_dependence_<n>_<feature>.png  the three strongest factors
    shap_force_high_risk.png           one high-risk landslide point, factor by factor
    shap_summary.json                  ranking, timings, additivity check, data source
"""
import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    # Lets `python src/explain_shap.py` work as well as `python -m src.explain_shap`.
    sys.path.insert(0, str(ROOT))

import joblib  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from src import artifacts, config, viz  # noqa: E402

SHAP_DIR = config.FIGURES_DIR / "shap"
SUMMARY_PATH = SHAP_DIR / "shap_summary.json"
MAX_SAMPLES = 500
PROBE_ROWS = 10            # rows timed first, to estimate the full run
LONG_STEP_SECONDS = 300    # project rule: warn before anything over 5 minutes
TOP_DEPENDENCE = 3
MAX_DISPLAY = 15
ADDITIVITY_TOLERANCE = 1e-6


def load_inputs():
    prepared = config.PROCESSED_DIR / "prepared.joblib"
    for path in (config.RF_MODEL_PATH, config.SCALER_PATH, config.FEATURE_NAMES_PATH, prepared):
        if not path.exists():
            raise SystemExit(f"{path} not found. Run Phase 2 Steps 4 to 6, then python src/verify_phase2.py.")
    rf = joblib.load(config.RF_MODEL_PATH)
    scaler = joblib.load(config.SCALER_PATH)
    names = artifacts.load_feature_names()
    bundle = joblib.load(prepared)
    X_test, y_test = bundle["X_test"], pd.Series(np.asarray(bundle["y_test"]), index=bundle["X_test"].index)
    if list(X_test.columns) != names or list(rf.feature_names_in_) != names:
        raise SystemExit("prepared.joblib, the RF model and feature_names.json disagree. "
                         "Run python src/verify_phase2.py to see where.")
    return rf, scaler, names, X_test, y_test


def stratified_sample(X: pd.DataFrame, y: pd.Series, n: int) -> tuple[pd.DataFrame, pd.Series]:
    if n >= len(X):
        return X, y
    from sklearn.model_selection import train_test_split

    X_sample, _, y_sample, _ = train_test_split(X, y, train_size=n, stratify=y, random_state=config.RANDOM_STATE)
    return X_sample, y_sample


def explain(explainer, X: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """SHAP values and base values for the landslide class (a classifier gets one slice per class)."""
    result = explainer(X, check_additivity=True)
    values, base = np.asarray(result.values), np.asarray(result.base_values)
    if values.ndim == 3:          # (rows, features, classes)
        values = values[:, :, 1]
    if base.ndim == 2:            # (rows, classes)
        base = base[:, 1]
    return values, base


def estimate_seconds(explainer, X: pd.DataFrame, n: int) -> tuple[float, float]:
    rows = X.iloc[:min(PROBE_ROWS, len(X))]
    started = time.perf_counter()
    explain(explainer, rows)
    probe = time.perf_counter() - started
    return probe, probe / len(rows) * n


def label_for(feature: str) -> str:
    unit = config.FEATURE_UNITS.get(feature)
    return f"{feature} ({unit})" if unit else feature


def save(fig, name: str, note: str) -> Path:
    return viz.save_fig(fig, f"shap/{name}", note=note)


def main() -> int:
    parser = argparse.ArgumentParser(description="SHAP explanations for the Random Forest")
    parser.add_argument("--max-samples", type=int, default=MAX_SAMPLES,
                        help=f"held-out test points to explain (default and maximum {MAX_SAMPLES})")
    parser.add_argument("--yes", action="store_true", help="continue even if the estimate exceeds 5 minutes")
    args = parser.parse_args()
    n_requested = max(1, min(args.max_samples, MAX_SAMPLES))

    import matplotlib
    matplotlib.use("Agg")  # files only, no window
    import matplotlib.pyplot as plt
    import shap

    print(config.data_source_banner())
    print(f"SHAP {shap.__version__}, TreeExplainer on the Random Forest\n")

    rf, scaler, names, X_test, y_test = load_inputs()
    X_sample, y_sample = stratified_sample(X_test, y_test, n_requested)
    print(f"[1] Sample: {len(X_sample):,} of {len(X_test):,} held-out test points "
          f"({int(y_sample.sum()):,} landslide, {int((y_sample == 0).sum()):,} stable), seed {config.RANDOM_STATE}")

    explainer = shap.TreeExplainer(rf, feature_perturbation="tree_path_dependent")
    probe, projected = estimate_seconds(explainer, X_sample, len(X_sample))
    print(f"[2] Time estimate: {probe:.1f} s for {min(PROBE_ROWS, len(X_sample))} rows, "
          f"about {projected:.0f} s for all {len(X_sample):,}")
    if projected > LONG_STEP_SECONDS and not args.yes:
        print(f"\nWARNING: this would take about {projected:.0f} s ({projected / 60:.1f} min), "
              f"over the {LONG_STEP_SECONDS // 60}-minute limit.")
        print("Rerun with --yes to continue, or with a smaller --max-samples.")
        return 2

    started = time.perf_counter()
    values, base = explain(explainer, X_sample)
    explain_seconds = time.perf_counter() - started
    proba = rf.predict_proba(X_sample)[:, 1]
    additivity_error = float(np.max(np.abs(base + values.sum(axis=1) - proba)))
    print(f"[3] SHAP values: {values.shape[0]:,} points x {values.shape[1]} factors in {explain_seconds:.1f} s")
    print(f"    base value (average landslide score) {base[0]:.4f}; largest additivity error "
          f"{additivity_error:.2e} ({'OK' if additivity_error < ADDITIVITY_TOLERANCE else 'CHECK'})")

    unscaled = pd.DataFrame(scaler.inverse_transform(X_sample.to_numpy()), columns=names, index=X_sample.index)
    explanation = shap.Explanation(values=values, base_values=base, data=unscaled.to_numpy(), feature_names=names)

    mean_abs = pd.Series(np.abs(values).mean(axis=0), index=names).sort_values(ascending=False)
    meta = json.loads(config.METADATA_PATH.read_text(encoding="utf-8")) if config.METADATA_PATH.exists() else {}
    permutation_order = list(meta.get("rf", {}).get("feature_importance_permutation", {}))
    print("\n    Rank  Factor                        mean |SHAP|   permutation rank (Step 6)")
    for rank, (feature, value) in enumerate(mean_abs.head(10).items(), start=1):
        perm = permutation_order.index(feature) + 1 if feature in permutation_order else "-"
        print(f"    {rank:>4}  {feature:<28}  {value:10.4f}   {perm}")

    SHAP_DIR.mkdir(parents=True, exist_ok=True)
    note = f"Random Forest, {len(X_sample):,} held-out test points, SHAP {shap.__version__}"
    files = []
    print("\n[4] Figures")

    plt.figure()
    shap.plots.beeswarm(explanation, max_display=MAX_DISPLAY, show=False)
    plt.title("How each factor moves the landslide score (each dot is one location)", loc="left", fontsize=11)
    files.append(save(plt.gcf(), "shap_beeswarm", note))
    plt.close("all")

    plt.figure()
    shap.plots.bar(explanation, max_display=MAX_DISPLAY, show=False)
    plt.title("Average size of each factor's effect (mean |SHAP|)", loc="left", fontsize=11)
    files.append(save(plt.gcf(), "shap_bar", note))
    plt.close("all")

    top = list(mean_abs.index[:TOP_DEPENDENCE])
    for rank, feature in enumerate(top, start=1):
        plt.figure()
        shap.plots.scatter(explanation[:, feature], show=False)
        axis = plt.gca()
        axis.set_xlabel(label_for(feature))
        axis.set_ylabel(f"SHAP value for {feature}\n(change in landslide score)")
        axis.set_title(f"Dependence: {feature}, rank {rank} by mean |SHAP|", loc="left", fontsize=11)
        files.append(save(plt.gcf(), f"shap_dependence_{rank}_{feature}", note))
        plt.close("all")

    landslides = np.flatnonzero(y_sample.to_numpy() == 1)
    pick = landslides[np.argmax(proba[landslides])] if len(landslides) else int(np.argmax(proba))
    shap.plots.force(float(base[pick]), values[pick], features=np.round(unscaled.iloc[pick].to_numpy(), 2),
                     feature_names=names, matplotlib=True, show=False, figsize=(20, 3.6), text_rotation=12)
    force_fig = plt.gcf()
    force_fig.suptitle(f"One high-risk landslide point: score {proba[pick]:.3f} against an average of "
                       f"{base[pick]:.3f}", x=0.01, ha="left", fontsize=11, y=1.08)
    files.append(save(force_fig, "shap_force_high_risk", note))
    plt.close("all")
    for path in files:
        print(f"    {path.relative_to(config.ROOT)}")

    summary = {
        "written": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "data_source": config.DATA_SOURCE,
        "shap_version": shap.__version__,
        "explainer": "TreeExplainer, tree_path_dependent, no background sample",
        "model": str(config.RF_MODEL_PATH.relative_to(config.ROOT)),
        "rf_model_mtime": config.RF_MODEL_PATH.stat().st_mtime,  # run_phase3 reruns when the model is newer
        "sample": {"rows": int(len(X_sample)), "landslide": int(y_sample.sum()),
                   "stable": int((y_sample == 0).sum()), "from": "held-out test set", "seed": config.RANDOM_STATE},
        "base_value": round(float(base[0]), 6),
        "additivity_max_error": additivity_error,
        "timing_seconds": {"probe": round(probe, 2), "projected": round(projected, 1),
                           "explain": round(explain_seconds, 1)},
        "mean_abs_shap": {k: round(float(v), 6) for k, v in mean_abs.items()},
        "dependence_features": top,
        "force_plot_point": {"test_index": int(X_sample.index[pick]), "landslide": int(y_sample.iloc[pick]),
                             "rf_score": round(float(proba[pick]), 4)},
        "figures": [str(p.relative_to(config.ROOT)) for p in files],
    }
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"    {SUMMARY_PATH.relative_to(config.ROOT)}")
    if config.IS_SYNTHETIC:
        print(f"\n{config.SYNTHETIC_LABEL}: these explanations describe the simulated data, not Uttarakhand.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
