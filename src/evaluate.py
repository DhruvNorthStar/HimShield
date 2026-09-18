"""
Step 7: evaluation and the SVM versus Random Forest comparison.

    python -m src.evaluate

Everything here is computed on the held-out test set, which was never resampled and never
seen during training or tuning.

Outputs:
    outputs/figures/roc_comparison.png            the headline figure: both curves, one plot
    outputs/figures/confusion_matrices.png        both models, side by side
    outputs/figures/precision_recall_comparison.png
    outputs/evaluation_report.txt                 classification reports and the written verdict
    models/metadata.json                          evaluation section with every metric

A note on which metric decides. Accuracy is close to useless here: with a 1:2 class balance,
answering "stable" every time already scores about 67 percent. AUC is threshold-free, so it
measures how well a model ranks risky ground above safe ground, which is exactly what a
susceptibility map needs. Recall matters next, because a missed landslide costs more than a
false alarm.
"""
import json
import sys

import joblib
import numpy as np
import pandas as pd

from src import artifacts, config, viz

BOOTSTRAP_ROUNDS = 1000


def load_everything():
    bundle_path = config.PROCESSED_DIR / "prepared.joblib"
    for path in (bundle_path, config.SVM_MODEL_PATH, config.RF_MODEL_PATH):
        if not path.exists():
            raise SystemExit(f"{path} not found. Run preprocess, train_svm and train_rf first.")
    bundle = joblib.load(bundle_path)
    models = {"SVM (RBF)": joblib.load(config.SVM_MODEL_PATH),
              "Random Forest": joblib.load(config.RF_MODEL_PATH)}
    # Phase 3 extension: XGBoost joins the comparison when its model exists. Without it (Phase 2, main branch)
    # everything below runs exactly as the two-model comparison.
    if config.XGB_MODEL_PATH.exists():
        models["XGBoost"] = joblib.load(config.XGB_MODEL_PATH)
    return bundle, models


def risk_scores(model, X) -> np.ndarray:
    """Probability of a landslide, or the decision score if the model has no probabilities."""
    if hasattr(model, "predict_proba"):
        return model.predict_proba(X)[:, 1]
    return model.decision_function(X)


def metrics_at(y_true, scores, threshold: float) -> dict:
    from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score, precision_score,
                                 recall_score)

    pred = (scores >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, pred, labels=[0, 1]).ravel()
    return {
        "threshold": round(float(threshold), 4),
        "accuracy": round(float(accuracy_score(y_true, pred)), 4),
        "precision": round(float(precision_score(y_true, pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_true, pred, zero_division=0)), 4),
        "f1": round(float(f1_score(y_true, pred, zero_division=0)), 4),
        "specificity": round(float(tn / (tn + fp)) if (tn + fp) else 0.0, 4),
        "true_negatives": int(tn), "false_positives": int(fp),
        "false_negatives": int(fn), "true_positives": int(tp),
    }


def youden_threshold(y_true, scores) -> float:
    """The cut-off that maximises recall plus specificity minus one.

    The default 0.5 is an arbitrary place to cut a probability. For hazard mapping the balance
    that matters is catching real landslides without flagging the whole state, and Youden's J
    is the standard way to pick that point from the ROC curve.
    """
    from sklearn.metrics import roc_curve

    fpr, tpr, thresholds = roc_curve(y_true, scores)
    return float(thresholds[int(np.argmax(tpr - fpr))])


def bootstrap_auc_difference(y_true, scores_a, scores_b, rounds: int = BOOTSTRAP_ROUNDS) -> dict:
    """Is the gap between the two models bigger than the noise in one test set?

    Resample the test set with replacement, recompute both AUCs, and look at the spread of the
    difference. If the 95 percent interval includes zero, the two models are not separable on
    this much data, and saying one is better would be overclaiming.
    """
    from sklearn.metrics import roc_auc_score

    rng = np.random.default_rng(config.RANDOM_STATE)
    y_true = np.asarray(y_true)
    differences = []
    for _ in range(rounds):
        idx = rng.integers(0, len(y_true), len(y_true))
        if len(np.unique(y_true[idx])) < 2:
            continue
        differences.append(roc_auc_score(y_true[idx], scores_b[idx]) -
                           roc_auc_score(y_true[idx], scores_a[idx]))
    low, high = np.percentile(differences, [2.5, 97.5])
    return {"mean_difference": round(float(np.mean(differences)), 4),
            "ci_low": round(float(low), 4), "ci_high": round(float(high), 4),
            "separable": bool(low > 0 or high < 0), "rounds": len(differences)}


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------
def plot_roc(y_true, scored: dict):
    """The headline figure: both models on one axis, so the comparison is direct."""
    import matplotlib.pyplot as plt
    from sklearn.metrics import roc_auc_score, roc_curve

    colours = viz.MODEL_COLORS
    fig, ax = plt.subplots(figsize=(6.4, 6))
    for name, scores in scored.items():
        fpr, tpr, _ = roc_curve(y_true, scores)
        auc = roc_auc_score(y_true, scores)
        ax.plot(fpr, tpr, color=colours[name], linestyle=viz.MODEL_LINESTYLES[name], linewidth=2.2,
                label=f"{name}, AUC {auc:.3f}")
    ax.plot([0, 1], [0, 1], color=viz.MUTED, linewidth=1, linestyle=(0, (4, 4)),
            label="random guessing, AUC 0.500")
    ax.set_xlabel("False positive rate (stable ground flagged as risky)")
    ax.set_ylabel("True positive rate (landslides caught)")
    ax.set_title(" vs ".join(n.replace(" (RBF)", "") for n in scored) + " on held-out data")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1.005)
    ax.set_aspect("equal")
    ax.legend(loc="lower right")
    return fig


def plot_confusion(y_true, scored: dict, thresholds: dict):
    import matplotlib.pyplot as plt
    from sklearn.metrics import confusion_matrix

    fig, axes = plt.subplots(1, len(scored), figsize=(4.75 * len(scored), 4.4))
    for ax, (name, scores) in zip(axes, scored.items()):
        pred = (scores >= thresholds[name]).astype(int)
        cm = confusion_matrix(y_true, pred, labels=[0, 1])
        ax.imshow(cm / cm.sum(axis=1, keepdims=True), cmap="Blues", vmin=0, vmax=1)
        for i in range(2):
            for j in range(2):
                share = cm[i, j] / cm[i].sum()
                ax.text(j, i, f"{cm[i, j]:,}\n{share:.0%}", ha="center", va="center", fontsize=11,
                        color=viz.SURFACE if share > 0.55 else viz.INK)
        ax.set_xticks([0, 1], ["predicted\nstable", "predicted\nlandslide"])
        ax.set_yticks([0, 1], ["actually\nstable", "actually\nlandslide"])
        ax.set_title(f"{name} (threshold {thresholds[name]:.2f})")
        ax.grid(visible=False)
        ax.tick_params(length=0)
    fig.suptitle("Confusion matrices, held-out test set", x=0.01, ha="left", fontsize=12,
                 fontweight="semibold")
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    return fig


def plot_precision_recall(y_true, scored: dict):
    """Worth showing alongside ROC when classes are imbalanced: it ignores true negatives."""
    import matplotlib.pyplot as plt
    from sklearn.metrics import average_precision_score, precision_recall_curve

    colours = viz.MODEL_COLORS
    base = float(np.mean(y_true))
    fig, ax = plt.subplots(figsize=(6.4, 5))
    for name, scores in scored.items():
        precision, recall, _ = precision_recall_curve(y_true, scores)
        ap = average_precision_score(y_true, scores)
        ax.plot(recall, precision, color=colours[name], linestyle=viz.MODEL_LINESTYLES[name], linewidth=2.2,
                label=f"{name}, AP {ap:.3f}")
    ax.axhline(base, color=viz.MUTED, linewidth=1, linestyle=(0, (4, 4)),
               label=f"always predict landslide, {base:.3f}")
    ax.set_xlabel("Recall (share of real landslides caught)")
    ax.set_ylabel("Precision (share of flags that are real)")
    ax.set_title("Precision against recall")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1.02)
    ax.legend(loc="lower left")
    return fig


# ---------------------------------------------------------------------------
def write_verdict(results: dict, comparison: dict, y_test) -> list[str]:
    """State which model wins, on what, and how confident that claim can be.

    This is the Phase 2 question, SVM against Random Forest; a third model, if present, gets its own section
    from xgb_verdict so the faculty comparison stays the headline.
    """
    names = [n for n in ("SVM (RBF)", "Random Forest") if n in results]
    aucs = {n: results[n]["auc"] for n in names}
    winner = max(aucs, key=aucs.get)
    loser = min(aucs, key=aucs.get)
    gap = aucs[winner] - aucs[loser]

    lines = [f"{winner} is the better model on this data.", ""]
    lines.append(f"On AUC, the metric that does not depend on a threshold, {winner} scores "
                 f"{aucs[winner]:.4f} against {aucs[loser]:.4f}, a gap of {gap:.4f}.")

    if comparison["separable"]:
        lines.append(f"Resampling the test set 1,000 times puts that gap between "
                     f"{comparison['ci_low']:+.4f} and {comparison['ci_high']:+.4f}, which excludes zero. "
                     f"The difference is larger than the noise in a test set this size.")
    else:
        lines.append(f"Resampling the test set 1,000 times puts the gap between "
                     f"{comparison['ci_low']:+.4f} and {comparison['ci_high']:+.4f}, which includes zero. "
                     f"On this much test data the two models cannot be told apart with confidence, so "
                     f"the honest claim is that they perform similarly, not that one is better.")
    lines.append("")

    for name in names:
        r = results[name]
        d = r["default"]
        lines.append(f"{name}: at the usual 0.5 cut-off it catches {d['recall']:.0%} of real landslides "
                     f"({d['true_positives']} of {d['true_positives'] + d['false_negatives']}), and "
                     f"{d['precision']:.0%} of the places it flags are real. It misses "
                     f"{d['false_negatives']} landslides and raises {d['false_positives']} false alarms.")
    lines.append("")

    best_recall = max(names, key=lambda n: results[n]["default"]["recall"])
    if best_recall != winner:
        lines.append(f"Note the split decision: {winner} ranks better overall, but {best_recall} catches "
                     f"more landslides at the default threshold. For a hazard map, missing a real "
                     f"landslide is worse than sending someone to check a safe slope, so that matters.")
        lines.append("")

    # Only measured results from here on. An earlier version explained the ranking with fixed sentences
    # (thresholds suit terrain, one-hot rock columns) that were never tested on this data.
    lines.append("What the measurements show:")
    meta = json.loads(config.METADATA_PATH.read_text(encoding="utf-8")) if config.METADATA_PATH.exists() else {}
    permutation = meta.get("rf", {}).get("feature_importance_permutation", {})
    if permutation:
        top = sorted(permutation.items(), key=lambda kv: -kv[1])[:5]
        lines.append("- Random Forest's strongest inputs by permutation importance (drop in test AUC when "
                     "the column is shuffled): " + ", ".join(f"{f} {v:+.3f}" for f, v in top) + ".")
    svm_gap = results["SVM (RBF)"].get("linear_gap")
    if svm_gap is not None:
        if svm_gap > 0.01:
            lines.append(f"- Inside the SVM, the RBF kernel beats a linear one by {svm_gap:+.4f} AUC on the "
                         f"test set: a curved boundary separates these inputs better than a straight one.")
        else:
            lines.append(f"- Inside the SVM, the RBF kernel beats a linear one by only {svm_gap:+.4f} AUC. "
                         f"The non-linearity argument is weak on this dataset, and saying so is more "
                         f"defensible than assuming the fancier kernel must be better.")

    # The near-road check runs after this script, so its saved numbers count only if they came from the
    # same models: its all-test-points AUCs must equal the ones measured above.
    near = meta.get("near_road_check", {}).get("subsets", {})
    everything = near.get("all test points", {})
    same_models = everything and all(
        abs(everything.get(n, {}).get("auc", -1) - results[n]["auc"]) < 1e-4 for n in names)
    if same_models:
        split_km = meta["near_road_check"]["split_m"] / 1000
        for label, subset in near.items():
            if label == "all test points":
                continue
            diff = subset["rf_minus_svm"]
            small = " Few landslides, so read these intervals as wide." if subset["landslide"] < 200 else ""
            xgb_part = f", XGBoost {subset['XGBoost']['auc']:.3f}" if "XGBoost" in subset else ""
            lines.append(f"- Test points {label.replace('1000 m', f'{split_km:g} km')} "
                         f"({subset['rows']:,} rows, {subset['landslide']:,} landslides): "
                         f"SVM AUC {subset['SVM (RBF)']['auc']:.3f}, Random Forest {subset['Random Forest']['auc']:.3f}{xgb_part}, "
                         f"RF minus SVM {diff['mean_difference']:+.3f} ({diff['ci_low']:+.3f} to {diff['ci_high']:+.3f}).{small}")
        lines.append("  Within the road corridor, where distance to roads separates the classes far less, "
                     "both models score lower than on the whole test set. The size of that drop is an "
                     "estimate of how much of the headline AUC comes from where the inventory was surveyed; "
                     "some road effect remains even within the corridor.")
    elif not config.IS_SYNTHETIC:
        lines.append("- Near-road AUCs: run `python -m src.near_road_check` after this script, then rerun "
                     "this script to include them.")

    lines.append("")
    lines.append("Limitations to state alongside these numbers:")
    lines.append("- The stable points are places with no recorded landslide, which is not the same as "
                 "places where none can happen. Some of them are risky ground that has never been "
                 "mapped, which caps how high any score here can go.")
    lines.append("- Train and test rows were split at random, so points near each other in the "
                 "landscape can land on both sides. Terrain is spatially correlated, so these scores "
                 "are likely a little optimistic compared with predicting a region never seen.")
    if not config.IS_SYNTHETIC:
        lines.append("- The GSI inventory follows roads, so part of each headline AUC reflects where "
                     "landslides were recorded rather than terrain alone; the near-road AUCs above "
                     "measure how much.")
    if config.IS_SYNTHETIC:
        lines.append(f"- {config.SYNTHETIC_LABEL}: every number above comes from simulated data and "
                     f"describes nothing about Uttarakhand.")
    return lines


def xgb_verdict(results: dict, pairwise: dict) -> list[str]:
    """Phase 3 extension: where XGBoost stands against the two Phase 2 models, with bootstrap intervals."""
    x = results["XGBoost"]
    lines = ["", "Phase 3 extension: XGBoost as a third model (same split, SMOTE inside folds, 5-fold CV on AUC):",
             f"- XGBoost test AUC {x['auc']:.4f}, average precision {x['average_precision']:.4f}; at 0.5 it catches "
             f"{x['default']['recall']:.0%} of landslides with precision {x['default']['precision']:.0%} "
             f"({x['default']['false_negatives']} missed, {x['default']['false_positives']} false alarms)."]
    for label, d in pairwise.items():
        verdict = ("excludes zero: a real difference" if d["separable"]
                   else "includes zero: not separable on this test set")
        lines.append(f"- {label}: {d['mean_difference']:+.4f}, 95% interval {d['ci_low']:+.4f} to "
                     f"{d['ci_high']:+.4f}, which {verdict}.")
    best = max(results, key=lambda n: results[n]["auc"])
    lines.append(f"- Highest test AUC of the three: {best} ({results[best]['auc']:.4f}).")
    return lines


def main() -> int:
    from sklearn.metrics import average_precision_score, classification_report, roc_auc_score

    print(config.data_source_banner())
    viz.apply_style()
    bundle, models = load_everything()
    X_test, y_test = bundle["X_test"], bundle["y_test"]
    print(f"Test set: {len(y_test):,} rows, {int(np.sum(y_test)):,} landslide, "
          f"{int(len(y_test) - np.sum(y_test)):,} stable\n")

    scored = {name: risk_scores(model, X_test) for name, model in models.items()}
    results, reports = {}, {}
    for name, scores in scored.items():
        best_threshold = youden_threshold(y_test, scores)
        results[name] = {
            "auc": round(float(roc_auc_score(y_test, scores)), 4),
            "average_precision": round(float(average_precision_score(y_test, scores)), 4),
            "default": metrics_at(y_test, scores, 0.5),
            "youden": metrics_at(y_test, scores, best_threshold),
        }
        reports[name] = classification_report(y_test, (scores >= 0.5).astype(int),
                                              target_names=["stable", "landslide"], digits=3)
        r = results[name]
        print(f"{name}: AUC {r['auc']:.4f}  AP {r['average_precision']:.4f}  "
              f"accuracy {r['default']['accuracy']:.3f}  precision {r['default']['precision']:.3f}  "
              f"recall {r['default']['recall']:.3f}  F1 {r['default']['f1']:.3f}")
        print(f"  best threshold by Youden J: {r['youden']['threshold']:.2f} -> "
              f"recall {r['youden']['recall']:.3f}, precision {r['youden']['precision']:.3f}")

    # Carry the linear-kernel comparison through from Step 5, if it ran.
    if config.METADATA_PATH.exists():
        meta = json.loads(config.METADATA_PATH.read_text(encoding="utf-8"))
        gap = meta.get("svm", {}).get("linear_comparison", {}).get("rbf_minus_linear_test_auc")
        if gap is not None:
            results["SVM (RBF)"]["linear_gap"] = gap

    comparison = bootstrap_auc_difference(y_test, scored["SVM (RBF)"], scored["Random Forest"])
    print(f"\nAUC difference (RF minus SVM): {comparison['mean_difference']:+.4f}, "
          f"95% interval {comparison['ci_low']:+.4f} to {comparison['ci_high']:+.4f}")

    pairwise = {}
    if "XGBoost" in scored:
        pairwise["XGBoost minus Random Forest"] = bootstrap_auc_difference(
            y_test, scored["Random Forest"], scored["XGBoost"])
        pairwise["XGBoost minus SVM (RBF)"] = bootstrap_auc_difference(y_test, scored["SVM (RBF)"], scored["XGBoost"])
        for label, d in pairwise.items():
            print(f"AUC difference ({label}): {d['mean_difference']:+.4f}, "
                  f"95% interval {d['ci_low']:+.4f} to {d['ci_high']:+.4f}")

    thresholds = {name: 0.5 for name in scored}
    figures = {
        "roc_comparison": plot_roc(y_test, scored),
        "confusion_matrices": plot_confusion(y_test, scored, thresholds),
        "precision_recall_comparison": plot_precision_recall(y_test, scored),
    }
    print("\nFigures")
    for name, fig in figures.items():
        print(f"  {viz.save_fig(fig, name).relative_to(config.ROOT)}")

    verdict = write_verdict(results, comparison, y_test)
    if "XGBoost" in results:
        verdict += xgb_verdict(results, pairwise)
    print("\n" + "=" * 78)
    for line in verdict:
        print(line)
    print("=" * 78)

    report_path = config.OUTPUTS_DIR / "evaluation_report.txt"
    with report_path.open("w", encoding="utf-8") as fh:
        fh.write(f"{config.data_source_banner()}\n\nHELD-OUT TEST SET: {len(y_test):,} rows\n\n")
        for name, text in reports.items():
            fh.write(f"--- {name} (threshold 0.5) ---\n{text}\n")
        fh.write("\nSUMMARY\n")
        fh.write(pd.DataFrame({n: {"AUC": r["auc"], "average precision": r["average_precision"],
                                   **{k: v for k, v in r["default"].items() if k in
                                      ("accuracy", "precision", "recall", "f1", "specificity")}}
                               for n, r in results.items()}).to_string())
        fh.write("\n\nVERDICT\n" + "\n".join(verdict) + "\n")
    print(f"\n{report_path.relative_to(config.ROOT)}")

    artifacts.update_metadata("evaluation", {
        "test_rows": int(len(y_test)),
        "test_positives": int(np.sum(y_test)),
        "models": results,
        "auc_difference_rf_minus_svm": comparison,
        "pairwise_auc_differences": {"Random Forest minus SVM (RBF)": comparison, **pairwise},
        "winner": max(results, key=lambda n: results[n]["auc"]),
        "phase2_winner": max(("SVM (RBF)", "Random Forest"), key=lambda n: results[n]["auc"]),
        "figures": [f"outputs/figures/{n}.png" for n in figures],
    })
    print("Next: Step 8, the dashboard")
    return 0


if __name__ == "__main__":
    sys.exit(main())
