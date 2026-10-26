"""Phase 3 presentation of existing benchmark data; Phase 2 pages stay unchanged."""
import pandas as pd
import streamlit as st

from dashboard_v2 import explorer, spatial_results, ui
from src import config


def overview(p2, explorer_page, methodology_page) -> None:
    meta, df = p2.metadata(), p2.dataset()
    prep, ev = meta.get("preprocessing", {}), meta.get("evaluation", {})
    ui.page_header("HimShield", "Landslide susceptibility analytics for Uttarakhand, India.")
    if config.IS_SYNTHETIC:
        p2.synthetic_banner()
    st.markdown("Explore terrain conditions, compare three saved models and inspect susceptibility coverage. "
                "HimShield supports research and screening; it does not replace a site investigation or forecast a landslide event.")
    positives = int((df[config.TARGET] == 1).sum())
    with st.container(key="himshield-overview-stats"):
        cols = st.columns(4)
        for col, key, label, value, help_text in zip(cols,
                ("samples", "positive", "negative", "features"),
                ("Sample points", "Landslide points", "Stable points", "Model inputs"),
                (f"{len(df):,}", f"{positives:,}", f"{len(df) - positives:,}", str(len(prep.get("kept_features", [])) or "—")),
                ("Input dataset, before water exclusions", "Recorded landslide samples",
                 "Sampled points with no recorded landslide; not proof of safety", "Stored encoded benchmark feature schema")):
            ui.metric_card(col, key, label, value, help=help_text)
    ui.caption(f"Retained modelling samples: {prep.get('rows_used', len(df)):,}. "
               "Sample counts above describe the input dataset; water exclusions reduce the modelling count.")
    with ui.panel("overview-benchmark"):
        st.subheader("Three-model benchmark")
        ui.caption(ui.BENCHMARK_NOTE)
        results = ev.get("models", {})
        if results:
            for i, (col, (name, result)) in enumerate(zip(st.columns(len(results)), results.items())):
                ui.metric_card(col, f"overview-model-{i}", name + ": ROC-AUC (%)", ui.percent(result["auc"]),
                               model=name,
                               help=f"Average precision {ui.percent(result['average_precision'])}; original random held-out split. ROC-AUC is not accuracy.")
            ui.caption("Highest observed AUC does not establish conclusive superiority. See Model Comparison for the saved intervals and threshold context.")
        else:
            ui.availability("Benchmark unavailable.", "No saved evaluation is available; no model is fitted here.")
    with st.container(key="himshield-overview-links"):
        left, right = st.columns([1.4, 1], gap="medium")
    with left, ui.panel("overview-explore"):
        st.subheader("Explore susceptibility")
        coverage_names, coverage_badge = explorer.statewide_coverage()
        st.markdown(
            '<div class="himshield-coverage-title">Uttarakhand</div>'
            '<div class="himshield-badges" aria-label="Statewide map coverage">'
            f'<span class="himshield-badge">{coverage_badge}</span>'
            '<span class="himshield-badge">Interactive / offline</span></div>',
            unsafe_allow_html=True,
        )
        if coverage_names:
            st.markdown("Explore saved susceptibility maps from " + ", ".join(coverage_names)
                        + " across the state. Blank areas are unscored.")
        else:
            st.markdown("Saved statewide map coverage is currently unavailable.")
        unavailable = explorer.statewide_unavailable(dict.fromkeys(coverage_names))
        if unavailable:
            ui.caption(unavailable)
        st.markdown(
            '<div class="himshield-coverage-secondary">'
            '<strong>Rudraprayag · dedicated RF &amp; SVM maps</strong>'
            '<p>Separate saved district products, distinct from statewide RF coverage.</p></div>',
            unsafe_allow_html=True,
        )
        ui.caption("Optional local views cover all 13 districts using statewide RF classes. "
                   "Coverage is partial; private reference files are required.")
        with st.container(key="himshield-explorer-cta"):
            st.page_link(explorer_page, label="Open Susceptibility Explorer", icon=":material/map:",
                         use_container_width=True)
    with right, ui.panel("overview-validation"):
        st.subheader("Understand the evidence")
        st.markdown("The original benchmark uses a random split. The separately verified nested spatial/control "
                    "experiment is reported in Methodology & Validation when available, with fold variability and sampling limitations.")
        st.page_link(methodology_page, label="Read Methodology & Validation", icon=":material/science:")
    ui.caption(ui.SCORE_NOTE)


def methodology(p2) -> None:
    meta, df = p2.metadata(), p2.dataset()
    ui.page_header("Methodology & Validation", "Data provenance, original preprocessing and the limits of the existing benchmark.")
    spatial_results.render()
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
                   "introduce leakage. The separately reported nested experiment contains learned preprocessing within folds; "
                   "it does not retrospectively change this original benchmark.")

    with ui.panel("study-area"):
        st.subheader("Study area")
        st.markdown("Uttarakhand: 13 districts, about 53,400 km², from the Terai plains to the high Himalaya. "
                    "Factors are aligned to a 30 m grid in UTM zone 44N (EPSG:32644); alignment does not "
                    "give coarse source data a native 30 m resolution. "
                    f"Both the statewide and **{config.DEMO_DISTRICT}** maps remain available in Susceptibility Explorer.")
    with st.expander("Exploratory analysis figures"):
        tabs = st.tabs(["Class balance", "Distributions", "Categories", "Correlations", "Missing values"])
        for tab, name in zip(tabs, ["eda_class_balance", "eda_distributions_by_class",
                                    "eda_categorical_landslide_rate", "eda_correlation_heatmap", "eda_missing_values"]):
            with tab:
                ui.figure(config.FIGURES_DIR / f"{name}.png")
    with st.expander("Scientific limitations and validation status"):
        items = [
            '- **Stable means "no recorded landslide"**, not that a location cannot fail.',
            "- **Random train/test split:** nearby samples can appear on both sides; the original benchmark is not geographically independent.",
            "- **Preprocessing:** imputation, category handling and VIF decisions precede the benchmark split; scaling is not refitted inside its CV.",
            "- **Retrospective thresholds:** test-selected Youden metrics are descriptive, not an independent threshold validation.",
            "- **Rainfall:** the 2009–2024 annual mean describes climate, not real-time triggering rainfall.",
            "- **Spatial validation:** separate five-fold results use 10 km blocks, 2 km spatial outer buffers and three buffered spatial inner folds. Random-group control has no outer buffer; new-region/future-time generalization remains unmeasured.",
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
                         f"RF ROC-AUC = {ui.percent(within['Random Forest']['auc'])} and SVM ROC-AUC = {ui.percent(within['SVM (RBF)']['auc'])}. "
                         "This subgroup diagnostic does not remove survey bias or establish regional independence.")
            else:
                road += " No saved near-road subgroup diagnostic is available."
            items.append(road)
        st.markdown("\n".join(items))
    with ui.panel("methodology-interpretation"):
        st.subheader("Scores, uncertainty and use")
        st.markdown(ui.SCORE_NOTE)
        ui.caption("Model disagreement and the saved bootstrap intervals describe uncertainty within this benchmark. "
                   "They do not account for every inventory omission, sampling bias or change in geography. "
                   "A terrain-condition assessment is manual input analysis; it is neither a GPS feature extraction "
                   "nor a real-time rainfall warning. New-region and future-time generalization remain unmeasured.")


def comparison(p2) -> None:
    meta, ev = p2.metadata(), p2.evaluation_section()
    results, gap = ev["models"], ev["auc_difference_rf_minus_svm"]
    names = list(results)
    ui.page_header("Model Comparison", "Compare the existing saved benchmark results; no model is fitted here.")
    ui.caption(f"Random held-out test set: {ev['test_rows']:,} points, {ev['test_positives']:,} recorded landslides. "
               "Not resampled or used for hyperparameter search. Retrospective threshold selection does use test labels.")
    cols = st.columns(len(names))
    for i, (col, name) in enumerate(zip(cols, names)):
        ui.metric_card(col, f"model-{i}", f"{name}: ROC-AUC (%)", ui.percent(results[name]["auc"]),
                       model=name,
                       help=f"Average precision {ui.percent(results[name]['average_precision'])}; ROC-AUC measures ranking, not accuracy")
    if gap["separable"]:
        pair_winner = ev.get("phase2_winner", ev["winner"])
        st.info(f"**{pair_winner} has the higher AUC in the RF/SVM comparison.** The existing 95% bootstrap "
                f"interval for RF minus SVM is {ui.percentage_points(gap['ci_low'])} to {ui.percentage_points(gap['ci_high'])}. "
                "This comparison is conditional on the random test set and its sampling limitations.")
    else:
        st.info(f"**RF and SVM are not distinguishable by this bootstrap comparison.** "
                f"The interval {ui.percentage_points(gap['ci_low'])} to {ui.percentage_points(gap['ci_high'])} includes zero.")
    pairwise = ev.get("pairwise_auc_differences", {})
    close = [label for label, d in pairwise.items() if "XGBoost" in label and "Random Forest" in label and not d["separable"]]
    if close:
        d = pairwise[close[0]]
        st.info(f"XGBoost versus Random Forest: saved mean ROC-AUC gap {ui.percentage_points(d['mean_difference'])}, "
                f"95% bootstrap interval {ui.percentage_points(d['ci_low'])} to {ui.percentage_points(d['ci_high'])}. It includes zero. "
                "This does not establish equivalence or conclusive superiority.")
    if pairwise:
        with st.expander("All saved pairwise AUC intervals"):
            ui.caption("Bootstrap comparisons conditional on this random test set, not spatial validation. "
                       "Gaps and intervals use percentage points (pp); they are not relative percentage improvements.")
            for label, d in pairwise.items():
                st.markdown(f"**{label}:** {ui.percentage_points(d['mean_difference'])}; 95% interval "
                            f"{ui.percentage_points(d['ci_low'])} to {ui.percentage_points(d['ci_high'])}; {d['rounds']:,} bootstrap resamples.")
    with ui.panel("threshold-metrics"):
        st.subheader("Metrics at a chosen threshold")
        choice = st.radio("Threshold", ["0.5, the usual default", "Youden's J, retrospective benchmark threshold"],
                          horizontal=True)
        key = "default" if choice.startswith("0.5") else "youden"
        percent_fields = {"accuracy", "precision", "recall", "specificity", "f1"}
        table = pd.DataFrame(
            {name: [ui.percent(results[name]["auc"]), ui.percent(results[name]["average_precision"])]
                   + [ui.percent(results[name][key][field]) if field in percent_fields
                      else fmt.format(results[name][key][field]) for _, field, fmt in p2.METRIC_ROWS] for name in names},
            index=["ROC-AUC (%) — threshold independent", "Average precision (%) — threshold independent"]
                  + [label + " (%)" if field in percent_fields else
                     "Threshold (score, 0–1)" if field == "threshold" else label for label, field, _ in p2.METRIC_ROWS])
        st.table(table)
        baseline = 1 - ev["test_positives"] / ev["test_rows"]
        ui.caption(f"Always predicting the sampled stable class gives {baseline:.0%} accuracy. "
                   "ROC-AUC (%) measures ranking; Accuracy (%) measures correct decisions at the selected threshold. "
                   "ROC-AUC and average precision do not depend on the threshold. Scores and thresholds remain on 0–1. " + ui.THRESHOLD_NOTE)
    st.subheader("Saved evaluation figures")
    ui.caption("Saved figures retain their original axes and annotations: 0.90 on a 0–1 metric axis equals 90%. "
               "Confusion matrices show integer counts.")
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
            ui.figure(config.FIGURES_DIR / f"{figure}.png")
            ui.caption(note)
    with st.expander("Saved tuning and training details"):
        st.subheader("Saved tuning and training details")
        svm, rf = meta.get("svm", {}), meta.get("rf", {})
        rows = []
        if svm:
            rows.append({"Model": "SVM, RBF kernel", "Best parameters": p2.params_text(svm["best_params"]),
                         "CV ROC-AUC (%)": ui.percent(svm["best_cv_auc"]), "Test ROC-AUC (%)": ui.percent(results["SVM (RBF)"]["auc"]),
                         "Grid search (s)": svm["timing_seconds"]["rbf_grid"]})
            linear = svm.get("linear_comparison")
            if linear:
                rows.append({"Model": "SVM, linear kernel (comparison only)",
                             "Best parameters": p2.params_text(linear["best_params"]), "CV ROC-AUC (%)": ui.percent(linear["best_cv_auc"]),
                             "Test ROC-AUC (%)": ui.percent(linear["test_auc"]), "Grid search (s)": svm["timing_seconds"]["linear_grid"]})
        if rf:
            rows.append({"Model": "Random Forest", "Best parameters": p2.params_text(rf["best_params"]),
                         "CV ROC-AUC (%)": ui.percent(rf["best_cv_auc"]), "Test ROC-AUC (%)": ui.percent(results["Random Forest"]["auc"]),
                         "Grid search (s)": rf["timing_seconds"]["grid_search"]})
        xgb = meta.get("xgb", {})
        if xgb and "XGBoost" in results:
            rows.append({"Model": "XGBoost", "Best parameters": p2.params_text(xgb["best_params"]),
                         "CV ROC-AUC (%)": ui.percent(xgb["best_cv_auc"]), "Test ROC-AUC (%)": ui.percent(results["XGBoost"]["auc"]),
                         "Grid search (s)": xgb["timing_seconds"]["grid_search"]})
        if rows:
            st.dataframe(pd.DataFrame(rows), hide_index=True,
                         column_config={"Grid search (s)": st.column_config.NumberColumn(format="%.1f")})
            ui.caption("Original CV uses training-fold SMOTE, but preprocessing decisions and the outer-training "
                       "scaler are reused. Agreement with test AUC does not establish absence of leakage or spatial independence.")
    report = config.OUTPUTS_DIR / "evaluation_report.txt"
    if report.exists():
        text = report.read_text(encoding="utf-8")
        if "VERDICT" in text:
            with st.expander("Original saved evaluation report"):
                ui.caption("Historical report, preserved verbatim. Phase labels and interpretive wording below "
                           "belong to the original report; apply the benchmark limitations stated above. "
                           "Original 0–1 metric values in this report correspond to percentages in the dashboard (0.90 = 90%).")
                st.text(text.split("VERDICT", 1)[1].strip())
