"""Phase 3 presentation of existing benchmark data; Phase 2 pages stay unchanged."""
import pandas as pd
import streamlit as st

from dashboard_v2 import ui
from src import config


def overview(p2) -> None:
    meta, df = p2.metadata(), p2.dataset()
    prep, ev = meta.get("preprocessing", {}), meta.get("evaluation", {})
    ui.page_header("HimShield", "Landslide susceptibility mapping and model comparison for Uttarakhand, India.")
    if config.IS_SYNTHETIC:
        p2.synthetic_banner()
    names = ", ".join(ev.get("models", {})) or "the saved models"
    st.markdown(f"Explore **{names}**, terrain conditions and saved susceptibility maps. "
                "The original results use a stratified random split; they do not measure performance "
                "in a geographically independent region.")
    positives = int((df[config.TARGET] == 1).sum())
    cols = st.columns(5)
    ui.metric_card(cols[0], "samples", "Sample points", f"{len(df):,}",
                   help=f"{prep.get('rows_used', len(df)):,} retained after excluding water points")
    ui.metric_card(cols[1], "positive", "Landslide points", f"{positives:,}")
    ui.metric_card(cols[2], "negative", "Stable points", f"{len(df) - positives:,}",
                   help="Sampled locations with no recorded landslide, not proof of safety")
    ui.metric_card(cols[3], "features", "Model inputs", f"{len(prep.get('kept_features', [])) or '-'}",
                   help="The stored encoded feature schema used by the benchmark models")
    if ev:
        winner = ev["winner"]
        ui.metric_card(cols[4], "auc", "Highest benchmark AUC", f"{ev['models'][winner]['auc']:.3f}",
                       help=f"{winner}; highest observed AUC does not establish superiority. See the saved pairwise intervals.")
    ui.caption(f"Dataset rows: {len(df):,}. Retained modelling samples: {prep.get('rows_used', len(df)):,}. "
               "The cards above describe the input dataset; exclusions are reflected in the modelling sample count.")
    ui.caption(ui.SCORE_NOTE)

    left, right = st.columns([1.1, 1], gap="large")
    with left, ui.panel("factors"):
        st.subheader("Conditioning factors")
        rows = [{"Factor": label, "Unit": config.FEATURE_UNITS.get(col, ""), "Source": source,
                 "In use": "no: " + config.DROPPED_COLUMNS[col] if col in config.DROPPED_COLUMNS else "yes"}
                for col, (label, source) in p2.FACTORS.items()]
        st.dataframe(pd.DataFrame(rows), hide_index=True)
    with right, ui.panel("workflow"):
        st.subheader("Original benchmark workflow")
        st.markdown(
            f"1. **Sample points.** Recorded landslides are positives. Sample {config.NEG_TO_POS_RATIO} "
            f"stable points per landslide, at least {config.NEGATIVE_BUFFER_M} m from mapped landslides, excluding water.\n"
            f"2. **Before splitting:** exclude water rows, fill missing values, merge categories with fewer than "
            f"{config.RARE_CLASS_MIN_ROWS} rows, encode aspect and categories, and apply VIF filtering "
            f"at {config.VIF_THRESHOLD:g}. These decisions use the whole eligible dataset.\n"
            f"3. **Random split:** stratified {100 - round(config.TEST_SIZE * 100)}/"
            f"{round(config.TEST_SIZE * 100)}, seed {config.RANDOM_STATE}.\n"
            "4. **Scaling:** fit the scaler on the outer training set and reuse it in the original CV.\n"
            f"5. **Hyperparameter search:** {config.CV_FOLDS}-fold random CV on AUC, with SMOTE confined "
            "to each CV training fold. The held-out test set is not resampled or used for hyperparameter search.\n"
            "6. **Evaluation:** score the held-out test set; select retrospective Youden thresholds on that same test set."
        )
        ui.caption("Whole-dataset preprocessing and reuse of the outer-training scaler in inner CV can "
                   "introduce leakage. The new spatial framework contains learned preprocessing within folds, "
                   "but it has no measured performance results yet.")

    with ui.panel("study-area"):
        st.subheader("Study area")
        st.markdown("Uttarakhand: 13 districts, about 53,400 km², from the Terai plains to the high Himalaya. "
                    "Factors are aligned to a 30 m grid in UTM zone 44N (EPSG:32644); alignment does not "
                    "give coarse source data a native 30 m resolution. "
                    f"Both the statewide and **{config.DEMO_DISTRICT}** maps remain available in the navigation.")
    with st.expander("Exploratory analysis figures"):
        tabs = st.tabs(["Class balance", "Distributions", "Categories", "Correlations", "Missing values"])
        for tab, name in zip(tabs, ["eda_class_balance", "eda_distributions_by_class",
                                    "eda_categorical_landslide_rate", "eda_correlation_heatmap", "eda_missing_values"]):
            with tab:
                ui.figure(config.FIGURES_DIR / f"{name}.png")
    with st.expander("Scientific limitations and validation status"):
        items = [
            '- **Stable means "no recorded landslide"**, not that a location cannot fail.',
            "- **Random train/test split:** nearby samples can appear on both sides; geographically independent performance is unmeasured.",
            "- **Preprocessing:** imputation, category handling and VIF decisions precede the benchmark split; scaling is not refitted inside its CV.",
            "- **Retrospective thresholds:** test-selected Youden metrics are descriptive, not an independent threshold validation.",
            "- **Rainfall:** the 2009–2024 annual mean describes climate, not real-time triggering rainfall.",
            "- **Spatial validation:** five outer folds, 10 km blocks, 2 km exclusion buffers and three inner spatial folds are implemented; performance results are pending.",
        ]
        if "lithology" in config.DROPPED_COLUMNS:
            items.append("- **Lithology excluded:** Bhukosh geology data was unavailable for this benchmark.")
        if not config.IS_SYNTHETIC and "dist_roads" in df.columns:
            r = df[config.TARGET].corr(df["dist_roads"])
            road = f"- **Road-survey bias:** the existing distance-to-roads/label correlation is r = {r:.2f}."
            near = meta.get("near_road_check", {}).get("subsets", {})
            within = next((v for k, v in near.items() if k.startswith("within")), None)
            if within:
                road += (f" Within {meta['near_road_check']['split_m'] / 1000:g} km of a road, "
                         f"RF AUC = {within['Random Forest']['auc']:.3f} and SVM AUC = {within['SVM (RBF)']['auc']:.3f}. "
                         "This subgroup diagnostic does not remove survey bias or establish regional independence.")
            else:
                road += " No saved near-road subgroup diagnostic is available."
            items.append(road)
        st.markdown("\n".join(items))


def comparison(p2) -> None:
    meta, ev = p2.metadata(), p2.evaluation_section()
    results, gap = ev["models"], ev["auc_difference_rf_minus_svm"]
    names = list(results)
    ui.page_header("Model comparison", "Compare the existing saved benchmark results; no model is fitted here.")
    ui.caption(f"Random held-out test set: {ev['test_rows']:,} points, {ev['test_positives']:,} recorded landslides. "
               "Not resampled or used for hyperparameter search. Retrospective threshold selection does use test labels.")
    cols = st.columns(len(names) + 1)
    for i, (col, name) in enumerate(zip(cols, names)):
        ui.metric_card(col, f"model-{i}", f"{name}: test AUC", f"{results[name]['auc']:.3f}",
                       help=f"Average precision {results[name]['average_precision']:.3f}")
    ui.metric_card(cols[-1], "gap", "AUC gap, RF minus SVM", f"{gap['mean_difference']:+.3f}",
                   help=f"95% interval {gap['ci_low']:+.3f} to {gap['ci_high']:+.3f}; {gap['rounds']:,} bootstrap resamples")
    if gap["separable"]:
        pair_winner = ev.get("phase2_winner", ev["winner"])
        st.info(f"**{pair_winner} has the higher AUC in the RF/SVM comparison.** The existing 95% bootstrap "
                f"interval for RF minus SVM is {gap['ci_low']:+.3f} to {gap['ci_high']:+.3f}. "
                "This comparison is conditional on the random test set and its sampling limitations.")
    else:
        st.info(f"**RF and SVM are not distinguishable by this bootstrap comparison.** "
                f"The interval {gap['ci_low']:+.3f} to {gap['ci_high']:+.3f} includes zero.")
    with ui.panel("threshold-metrics"):
        st.subheader("Metrics at a chosen threshold")
        choice = st.radio("Threshold", ["0.5, the usual default", "Youden's J, retrospective benchmark threshold"],
                          horizontal=True)
        key = "default" if choice.startswith("0.5") else "youden"
        table = pd.DataFrame(
            {name: [f"{results[name]['auc']:.3f}", f"{results[name]['average_precision']:.3f}"]
                   + [fmt.format(results[name][key][field]) for _, field, fmt in p2.METRIC_ROWS] for name in names},
            index=["AUC (no threshold)", "Average precision (no threshold)"] + [r[0] for r in p2.METRIC_ROWS])
        st.table(table)
        baseline = 1 - ev["test_positives"] / ev["test_rows"]
        ui.caption(f"Always predicting the sampled stable class gives {baseline:.0%} accuracy. "
                   "AUC and average precision do not depend on the selected threshold. " + ui.THRESHOLD_NOTE)
    st.subheader("Saved evaluation figures")
    notes = {
        "ROC curves": ("roc_comparison", "True-positive against false-positive rate across thresholds. "
                       "Model colours and line styles are preserved."),
        "Confusion matrices": ("confusion_matrices", "Saved counts at threshold 0.5, irrespective of the "
                               "metrics-table selection above. The bottom-left cell contains missed landslides."),
        "Precision and recall": ("precision_recall_comparison", "Precision versus recall across thresholds; "
                                 "this view complements ROC for the imbalanced test set."),
        "Feature importance": ("rf_feature_importance", "Random Forest only. Impurity importance is derived "
                               "from training; permutation importance measures changes in test AUC. Neither proves causality."),
    }
    for tab, (figure, note) in zip(st.tabs(list(notes)), notes.values()):
        with tab, ui.panel("figure-" + figure):
            left, right = st.columns([3, 2], gap="large")
            with left:
                ui.figure(config.FIGURES_DIR / f"{figure}.png")
            with right:
                st.markdown(note)
    st.subheader("Saved tuning and training details")
    svm, rf = meta.get("svm", {}), meta.get("rf", {})
    rows = []
    if svm:
        rows.append({"Model": "SVM, RBF kernel", "Best parameters": p2.params_text(svm["best_params"]),
                     "CV AUC": svm["best_cv_auc"], "Test AUC": results["SVM (RBF)"]["auc"],
                     "Grid search (s)": svm["timing_seconds"]["rbf_grid"]})
        linear = svm.get("linear_comparison")
        if linear:
            rows.append({"Model": "SVM, linear kernel (comparison only)",
                         "Best parameters": p2.params_text(linear["best_params"]), "CV AUC": linear["best_cv_auc"],
                         "Test AUC": linear["test_auc"], "Grid search (s)": svm["timing_seconds"]["linear_grid"]})
    if rf:
        rows.append({"Model": "Random Forest", "Best parameters": p2.params_text(rf["best_params"]),
                     "CV AUC": rf["best_cv_auc"], "Test AUC": results["Random Forest"]["auc"],
                     "Grid search (s)": rf["timing_seconds"]["grid_search"]})
    xgb = meta.get("xgb", {})
    if xgb and "XGBoost" in results:
        rows.append({"Model": "XGBoost", "Best parameters": p2.params_text(xgb["best_params"]),
                     "CV AUC": xgb["best_cv_auc"], "Test AUC": results["XGBoost"]["auc"],
                     "Grid search (s)": xgb["timing_seconds"]["grid_search"]})
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True,
                     column_config={"CV AUC": st.column_config.NumberColumn(format="%.3f"),
                                    "Test AUC": st.column_config.NumberColumn(format="%.3f"),
                                    "Grid search (s)": st.column_config.NumberColumn(format="%.1f")})
        ui.caption("Original CV uses training-fold SMOTE, but preprocessing decisions and the outer-training "
                   "scaler are reused. Agreement with test AUC does not establish absence of leakage or spatial independence.")
    report = config.OUTPUTS_DIR / "evaluation_report.txt"
    if report.exists():
        text = report.read_text(encoding="utf-8")
        if "VERDICT" in text:
            with st.expander("Original saved evaluation report"):
                ui.caption("Historical report, preserved verbatim. Phase labels and interpretive wording below "
                           "belong to the original report; apply the benchmark limitations stated above.")
                st.text(text.split("VERDICT", 1)[1].strip())
