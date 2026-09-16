"""
Step 8: the dashboard for Landslide Susceptibility Mapping for Uttarakhand.

    streamlit run dashboard/app.py

Pages:
    Overview          what the project does, the data behind it, and how the pipeline avoids leakage
    Model Comparison  SVM against Random Forest on the held-out test set
    Predict           set the conditions at one location and score them with both models
    Rudraprayag Map   the Step 9 demo map, once `python -m src.demo_map` has been run

The dashboard trains nothing and recomputes no metric. It reads the Phase 2 exit artifacts
(models/*.pkl, feature_names.json, metadata.json) and the saved figures, so what it shows is exactly
what Steps 4 to 7 produced. Predictions go through src.preprocess.prepare_for_prediction, the same
transform the demo map and Phase 3 use, so a value set here is treated exactly as a raster cell is.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    # Streamlit puts dashboard/ on the import path, not the repo root, so `from src import` needs this.
    sys.path.insert(0, str(ROOT))

import joblib
import numpy as np
import pandas as pd
import streamlit as st

from src import config
from src.preprocess import EXCLUDED_LULC, prepare_for_prediction

PROJECT_NAME = "Landslide Susceptibility Mapping for Uttarakhand"

# Shown on every page while the pipeline runs on the simulated dataset. Faint, fixed behind the
# content and ignoring clicks, so it marks screenshots without getting in the way of reading.
WATERMARK_HTML = """
<style>
.lsm-synthetic-watermark {
  position: fixed; top: 55%; left: 50%;
  transform: translate(-50%, -50%) rotate(-24deg);
  font: 800 clamp(3rem, 9vw, 7rem)/1 system-ui, -apple-system, "Segoe UI", sans-serif;
  letter-spacing: 0.06em; color: rgba(213, 94, 0, 0.08);
  white-space: nowrap; pointer-events: none; user-select: none; z-index: 999;
}
</style>
<div class="lsm-synthetic-watermark" aria-hidden="true">SYNTHETIC DATA</div>
"""

# Display only. Processing detail and licences live in docs/data_sources_log.md.
FACTORS = {
    "slope": ("Slope", "Copernicus GLO-30 DEM, GRASS r.slope.aspect"),
    "aspect": ("Aspect", "Copernicus GLO-30 DEM, GRASS r.slope.aspect"),
    "elevation": ("Elevation", "Copernicus GLO-30 DEM, 30 m"),
    "curvature": ("Curvature", "Copernicus GLO-30 DEM, profile curvature"),
    "twi": ("Topographic wetness index", "Copernicus GLO-30 DEM, GRASS r.watershed (multiple flow direction)"),
    "rainfall": ("Rainfall", "CHIRPS v2.0, mean of 2009 to 2024"),
    "ndvi": ("Vegetation index (NDVI)", "Sentinel-2 L2A, median of Oct to Nov 2023 (Google Earth Engine)"),
    "soil_type": ("Soil type", "SoilGrids WRB, most probable class"),
    "lithology": ("Lithology", "Dropped: Bhukosh unavailable"),
    "lulc": ("Land cover", "ESA WorldCover 2021"),
    "dist_roads": ("Distance to roads", "OpenStreetMap roads"),
    "dist_streams": ("Distance to streams", "stream network derived from the DEM"),
    "dist_faults": ("Distance to faults", "GEM Global Active Faults"),
}
SLIDER_STEPS = {"slope": 0.5, "elevation": 10.0, "curvature": 0.05, "twi": 0.1, "rainfall": 10.0, "ndvi": 0.01,
                "dist_roads": 10.0, "dist_streams": 10.0, "dist_faults": 50.0}
INPUT_GROUPS = {
    "Terrain": ["slope", "elevation", "curvature", "aspect"],
    "Water and access": ["rainfall", "twi", "dist_streams", "dist_roads", "dist_faults"],
    "Ground": ["soil_type", "lithology", "lulc", "ndvi"],
}


# ---------------------------------------------------------------------------
# Loading. Each loader takes the file's modification time, so retraining while the
# dashboard is open shows the new results on the next rerun instead of a stale cache.
# The argument must not start with an underscore: Streamlit leaves such arguments out of
# the cache key, which is exactly what made the cache ignore retraining before.
# ---------------------------------------------------------------------------
def mtime(path: Path) -> float:
    return path.stat().st_mtime if path.exists() else 0.0


@st.cache_data
def load_metadata(stamp: float) -> dict:
    if not config.METADATA_PATH.exists():
        return {}
    return json.loads(config.METADATA_PATH.read_text(encoding="utf-8"))


@st.cache_data
def load_dataset(stamp: float) -> pd.DataFrame | None:
    if not config.DATASET_CSV.exists():
        return None
    return pd.read_csv(config.DATASET_CSV)


@st.cache_resource
def load_models(stamp: float) -> dict:
    return {
        "SVM (RBF)": joblib.load(config.SVM_MODEL_PATH),
        "Random Forest": joblib.load(config.RF_MODEL_PATH),
        "scaler": joblib.load(config.SCALER_PATH),
        "feature_names": json.loads(config.FEATURE_NAMES_PATH.read_text(encoding="utf-8")),
    }


def metadata() -> dict:
    return load_metadata(mtime(config.METADATA_PATH))


def dataset() -> pd.DataFrame:
    df = load_dataset(mtime(config.DATASET_CSV))
    if df is None:
        st.error(f"`{config.DATASET_CSV.relative_to(ROOT)}` not found. "
                 f"Run `python -m src.make_synthetic`, or finish Step 2 for the real dataset.")
        st.stop()
    return df


def models() -> dict:
    paths = [config.SVM_MODEL_PATH, config.RF_MODEL_PATH, config.SCALER_PATH, config.FEATURE_NAMES_PATH]
    missing = [str(p.relative_to(ROOT)) for p in paths if not p.exists()]
    if missing:
        st.error("Model files missing: " + ", ".join(f"`{m}`" for m in missing) + ". Run "
                 "`python -m src.preprocess`, `python -m src.train_svm` and `python -m src.train_rf`.")
        st.stop()
    return load_models(max(mtime(p) for p in paths))


def evaluation_section() -> dict:
    ev = metadata().get("evaluation")
    if not ev:
        st.error("No evaluation results in `models/metadata.json`. Run `python -m src.evaluate`.")
        st.stop()
    return ev


def synthetic_banner() -> None:
    """The first thing an examiner sees on the homepage: these results test the pipeline, they are not findings."""
    st.markdown(
        '<div style="border:2px solid #D55E00;border-left-width:8px;border-radius:6px;padding:14px 18px;'
        'margin:0 0 1.2rem;background:rgba(213,94,0,0.06)">'
        '<div style="font-weight:800;font-size:1.2rem;letter-spacing:0.05em;color:#0b0b0b">'
        'SYNTHETIC DATA: RESULTS ARE NOT FINAL</div>'
        '<div style="margin-top:6px;color:#1a1a1a">Every number, chart, prediction and map in this dashboard '
        'comes from a simulated dataset built to test the pipeline end to end. The real GSI landslide '
        'inventory has not been processed yet, so none of these results describe Uttarakhand. Both models '
        'will be retrained on real data before any result is reported.</div></div>',
        unsafe_allow_html=True)


def show_figure(name: str, caption: str | None = None) -> None:
    path = config.FIGURES_DIR / f"{name}.png"
    if path.exists():
        st.image(str(path), caption=caption)
    else:
        st.info(f"`outputs/figures/{name}.png` not found. Rerun the step that draws it.")


# ---------------------------------------------------------------------------
# Page 1: Overview
# ---------------------------------------------------------------------------
def page_overview() -> None:
    meta, df = metadata(), dataset()
    prep, ev = meta.get("preprocessing", {}), meta.get("evaluation", {})

    st.title(PROJECT_NAME)
    if config.IS_SYNTHETIC:
        synthetic_banner()
    st.markdown(
        "A comparison of a **Support Vector Machine** and a **Random Forest** for **Uttarakhand, India**. "
        "Both models look at the terrain conditions at a location (slope, rainfall, soil, land cover, vegetation, "
        "wetness, distance to roads and streams, and more) and score how likely that ground is to be "
        "landslide-prone.")

    positives = int((df[config.TARGET] == 1).sum())
    cols = st.columns(5)
    cols[0].metric("Sample points", f"{len(df):,}",
                   help=f"{prep.get('rows_used', len(df)):,} used after removing points on water")
    cols[1].metric("Landslide points", f"{positives:,}")
    cols[2].metric("Stable points", f"{len(df) - positives:,}",
                   help=f"{config.NEG_TO_POS_RATIO} per landslide point, at least "
                        f"{config.NEGATIVE_BUFFER_M} m from any mapped landslide")
    cols[3].metric("Model inputs", f"{len(prep.get('kept_features', [])) or '-'}",
                   help="The factors below after aspect becomes sine and cosine and each category "
                        "becomes its own yes/no column")
    if ev:
        winner = ev["winner"]
        cols[4].metric("Best test AUC", f"{ev['models'][winner]['auc']:.3f}", help=winner)

    left, right = st.columns([1.1, 1], gap="large")
    with left:
        st.subheader("Conditioning factors")
        rows = [{"Factor": label,
                 "Unit": config.FEATURE_UNITS.get(col, ""),
                 "Source": source,
                 "In use": "no: " + config.DROPPED_COLUMNS[col] if col in config.DROPPED_COLUMNS else "yes"}
                for col, (label, source) in FACTORS.items()]
        st.dataframe(pd.DataFrame(rows), hide_index=True)
    with right:
        st.subheader("How the pipeline works")
        st.markdown(
            f"1. **Sample points.** Landslide locations are the positives. Stable points are drawn "
            f"{config.NEG_TO_POS_RATIO} per landslide, at least {config.NEGATIVE_BUFFER_M} m from any "
            f"landslide, never on water.\n"
            f"2. **Split first.** A stratified {100 - round(config.TEST_SIZE * 100)}/"
            f"{round(config.TEST_SIZE * 100)} split with seed {config.RANDOM_STATE}. The test set is "
            f"never resampled and never used for tuning.\n"
            f"3. **Encode.** Aspect becomes sine and cosine, because 359° and 1° are neighbours. "
            f"Categories become yes/no columns. A VIF check removes any input above "
            f"{config.VIF_THRESHOLD:g}.\n"
            f"4. **Scale on training rows only**, so nothing about the test set leaks into training.\n"
            f"5. **Balance with SMOTE inside each cross-validation fold**, on training data only.\n"
            f"6. **Tune** with {config.CV_FOLDS}-fold grid search on AUC, then score once on the "
            f"held-out test set.")

    st.subheader("Study area")
    st.markdown(
        "Uttarakhand: 13 districts, about 53,400 km², from the Terai plains near 200 m to peaks above "
        "7,800 m. Every factor sits on one 30 m grid in UTM zone 44N (EPSG:32644). "
        f"The demo susceptibility map covers **{config.DEMO_DISTRICT}** district (about 1,936 km²).")

    with st.expander("Exploratory analysis figures (Step 3)"):
        tabs = st.tabs(["Class balance", "Distributions", "Categories", "Correlations", "Missing values"])
        for tab, name in zip(tabs, ["eda_class_balance", "eda_distributions_by_class",
                                    "eda_categorical_landslide_rate", "eda_correlation_heatmap",
                                    "eda_missing_values"]):
            with tab:
                show_figure(name)

    with st.expander("Limitations to keep in mind"):
        items = [
            "- **Stable means \"no recorded landslide\"**, not \"cannot fail\". Some stable points are "
            "risky ground nobody has mapped, which caps how high any score can go.",
            "- **The train/test split is random**, so nearby points can fall on both sides. Terrain is "
            "spatially correlated, so scores are likely somewhat optimistic for an unseen region.",
            "- **Rainfall is a 16-year annual mean** at about 5.5 km resolution. It describes the climate "
            "of an area, not the short bursts of rain that trigger individual landslides.",
        ]
        if "lithology" in config.DROPPED_COLUMNS:
            items.append(
                "- **Lithology was excluded.** GSI geology data requires Bhukosh portal access, which was "
                "unavailable. Chauhan et al. (2025) used GSI geology via Bhukosh; this study could not access it.")
        if not config.IS_SYNTHETIC and "dist_roads" in df.columns:
            r = df[config.TARGET].corr(df["dist_roads"])
            road = f"- **Road-survey bias.** Distance to roads is the strongest single predictor (r = {r:.2f})"
            near = meta.get("near_road_check", {}).get("subsets", {})
            within = next((v for k, v in near.items() if k.startswith("within")), None)
            if within:
                road += (f". Within {meta['near_road_check']['split_m'] / 1000:g} km of a road, "
                         f"RF AUC = {within['Random Forest']['auc']:.3f} and SVM AUC = {within['SVM (RBF)']['auc']:.3f}. "
                         "AUCs are comparable to Chauhan et al. (2025), with this bias quantified.")
            else:
                road += ". Run `python -m src.near_road_check` to measure its effect on AUC."
            items.append(road)
        st.markdown("\n".join(items))


# ---------------------------------------------------------------------------
# Page 2: Model comparison
# ---------------------------------------------------------------------------
METRIC_ROWS = [
    ("Threshold", "threshold", "{:.2f}"),
    ("Accuracy", "accuracy", "{:.3f}"),
    ("Precision: share of flags that are real", "precision", "{:.3f}"),
    ("Recall: share of landslides caught", "recall", "{:.3f}"),
    ("Specificity: share of stable ground cleared", "specificity", "{:.3f}"),
    ("F1", "f1", "{:.3f}"),
    ("Landslides caught", "true_positives", "{:,}"),
    ("Landslides missed", "false_negatives", "{:,}"),
    ("False alarms", "false_positives", "{:,}"),
    ("Stable ground cleared", "true_negatives", "{:,}"),
]


def page_comparison() -> None:
    meta, ev = metadata(), evaluation_section()
    results, gap = ev["models"], ev["auc_difference_rf_minus_svm"]
    names = list(results)

    st.title("Model comparison")
    st.caption(f"Held-out test set: {ev['test_rows']:,} points, {ev['test_positives']:,} of them landslides. "
               f"Never resampled and never used for tuning.")

    cols = st.columns(len(names) + 1)
    for col, name in zip(cols, names):
        col.metric(f"{name}: test AUC", f"{results[name]['auc']:.3f}",
                   help=f"Average precision {results[name]['average_precision']:.3f}")
    cols[-1].metric("AUC gap, RF minus SVM", f"{gap['mean_difference']:+.3f}",
                    help=f"95% interval {gap['ci_low']:+.3f} to {gap['ci_high']:+.3f}, "
                         f"from {gap['rounds']:,} bootstrap resamples of the test set")

    if gap["separable"]:
        st.info(f"**{ev['winner']} ranks risky ground above stable ground better.** Resampling the test set "
                f"{gap['rounds']:,} times puts the AUC gap between {gap['ci_low']:+.3f} and "
                f"{gap['ci_high']:+.3f}. That range excludes zero, so the difference is bigger than the "
                f"noise in a test set this size.")
    else:
        st.info(f"**The two models cannot be told apart on this test set.** The 95% interval for the AUC gap "
                f"({gap['ci_low']:+.3f} to {gap['ci_high']:+.3f}) includes zero.")

    st.subheader("Metrics at a chosen threshold")
    choice = st.radio("Threshold", ["0.5, the usual default", "Youden's J, tuned per model"],
                      horizontal=True, label_visibility="collapsed")
    key = "default" if choice.startswith("0.5") else "youden"
    table = pd.DataFrame(
        {name: [f"{results[name]['auc']:.3f}", f"{results[name]['average_precision']:.3f}"]
               + [fmt.format(results[name][key][field]) for _, field, fmt in METRIC_ROWS]
         for name in names},
        index=["AUC (no threshold)", "Average precision (no threshold)"] + [r[0] for r in METRIC_ROWS])
    st.table(table)
    baseline = 1 - ev["test_positives"] / ev["test_rows"]
    st.caption(f"AUC is the headline because it does not depend on a threshold. Accuracy is weak here: "
               f"answering \"stable\" every time already scores {baseline:.0%}. Youden's J picks the cut-off "
               f"that maximises recall plus specificity, which usually catches more landslides at the "
               f"cost of more false alarms.")

    st.subheader("Figures")
    notes = {
        "ROC curves": ("roc_comparison",
                       "Each curve shows landslides caught against stable ground wrongly flagged, over every "
                       "possible threshold. The closer a curve hugs the top-left corner, the better the "
                       "model ranks risky ground first. The dashed diagonal is guessing."),
        "Confusion matrices": ("confusion_matrices",
                               "Counts at the 0.5 threshold. The bottom-left cell, landslides predicted as "
                               "stable, is the costly mistake for a hazard map."),
        "Precision and recall": ("precision_recall_comparison",
                                 "Ignores the many correctly cleared stable points, so it shows more "
                                 "plainly how much each extra landslide caught costs in false alarms."),
        "Feature importance": ("rf_feature_importance",
                               "What the Random Forest relied on. Impurity importance comes from training "
                               "and favours continuous inputs; permutation importance measures the AUC lost "
                               "on the test set when one input is shuffled, which is the fairer view."),
    }
    for tab, (title, (figure, note)) in zip(st.tabs(list(notes)), notes.items()):
        with tab:
            left, right = st.columns([3, 2], gap="large")
            with left:
                show_figure(figure)
            with right:
                st.markdown(note)

    st.subheader("Tuning and training")
    svm, rf = meta.get("svm", {}), meta.get("rf", {})
    rows = []
    if svm:
        rows.append({"Model": "SVM, RBF kernel", "Best parameters": params_text(svm["best_params"]),
                     "CV AUC": svm["best_cv_auc"], "Test AUC": results["SVM (RBF)"]["auc"],
                     "Grid search (s)": svm["timing_seconds"]["rbf_grid"]})
        linear = svm.get("linear_comparison")
        if linear:
            rows.append({"Model": "SVM, linear kernel (comparison only)",
                         "Best parameters": params_text(linear["best_params"]),
                         "CV AUC": linear["best_cv_auc"], "Test AUC": linear["test_auc"],
                         "Grid search (s)": svm["timing_seconds"]["linear_grid"]})
    if rf:
        rows.append({"Model": "Random Forest", "Best parameters": params_text(rf["best_params"]),
                     "CV AUC": rf["best_cv_auc"], "Test AUC": results["Random Forest"]["auc"],
                     "Grid search (s)": rf["timing_seconds"]["grid_search"]})
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True,
                     column_config={"CV AUC": st.column_config.NumberColumn(format="%.3f"),
                                    "Test AUC": st.column_config.NumberColumn(format="%.3f"),
                                    "Grid search (s)": st.column_config.NumberColumn(format="%.1f")})
        st.caption("Cross-validation and test AUC agree closely because SMOTE runs inside each fold. "
                   "Resampling before cross-validation was measured earlier at CV 0.92 against test 0.69.")

    report = config.OUTPUTS_DIR / "evaluation_report.txt"
    if report.exists():
        text = report.read_text(encoding="utf-8")
        if "VERDICT" in text:
            with st.expander("Written verdict from `outputs/evaluation_report.txt`"):
                st.markdown(text.split("VERDICT", 1)[1].strip())


def params_text(params: dict) -> str:
    return ", ".join(f"{k}={v}" for k, v in params.items())


# ---------------------------------------------------------------------------
# Page 3: Predict
# ---------------------------------------------------------------------------
def category_options(df: pd.DataFrame, col: str) -> list[str]:
    values = df[col].dropna().astype(str)
    if col == "lulc":
        values = values[~values.isin(EXCLUDED_LULC)]
    return sorted(values.unique())


def slider_bounds(df: pd.DataFrame, col: str) -> tuple[float, float, float]:
    step = SLIDER_STEPS.get(col, 1.0)
    values = df[col].dropna()
    return (float(np.floor(values.min() / step) * step), float(np.ceil(values.max() / step) * step), step)


def typical_row(df: pd.DataFrame) -> dict:
    """Median of each number and most common class, over stable and landslide points together."""
    row = {}
    for col in config.active_numeric_features():
        values = df[col][df[col] >= 0] if col == "aspect" else df[col]
        row[col] = float(values.median())
    for col in config.active_categorical_features():
        row[col] = df[col].dropna().astype(str).mode().iloc[0]
    return row


def set_inputs(row: dict, df: pd.DataFrame) -> None:
    """Write a row into the input widgets, snapped to each slider's range and step."""
    for col in config.active_numeric_features():
        if col == "aspect":
            flat = row[col] < 0
            st.session_state["in_flat"] = bool(flat)
            if not flat:
                st.session_state["in_aspect"] = float(round(row[col]) % 360)
            elif "in_aspect" not in st.session_state:
                st.session_state["in_aspect"] = 180.0
            continue
        lo, hi, step = slider_bounds(df, col)
        value = min(max(float(row[col]), lo), hi)
        st.session_state[f"in_{col}"] = round(round(value / step) * step, 6)
    for col in config.active_categorical_features():
        options = category_options(df, col)
        st.session_state[f"in_{col}"] = row[col] if row[col] in options else options[0]


def load_example(kind: str, df: pd.DataFrame) -> None:
    if kind == "typical":
        set_inputs(typical_row(df), df)
        return
    label = 1 if kind == "landslide" else 0
    pool = df[(df[config.TARGET] == label) & ~df["lulc"].isin(EXCLUDED_LULC)].dropna() \
        if "lulc" in df.columns else df[df[config.TARGET] == label].dropna()
    set_inputs(pool.sample(1).iloc[0].to_dict(), df)


def input_widget(col: str, df: pd.DataFrame) -> None:
    label, _ = FACTORS[col]
    unit = config.FEATURE_UNITS.get(col, "")
    if col == "aspect":
        st.checkbox("Flat ground (no aspect)", key="in_flat")
        st.slider("Aspect, degrees from north", 0.0, 359.0, step=1.0, key="in_aspect",
                  disabled=st.session_state.get("in_flat", False))
    elif col in config.CATEGORICAL_FEATURES:
        st.selectbox(label, category_options(df, col), key=f"in_{col}")
    else:
        lo, hi, step = slider_bounds(df, col)
        st.slider(f"{label}, {unit}", lo, hi, step=step, key=f"in_{col}")


def read_inputs() -> dict:
    row = {}
    for col in config.active_numeric_features():
        if col == "aspect":
            row[col] = -1.0 if st.session_state["in_flat"] else float(st.session_state["in_aspect"])
        else:
            row[col] = float(st.session_state[f"in_{col}"])
    for col in config.active_categorical_features():
        row[col] = st.session_state[f"in_{col}"]
    return row


def page_predict() -> None:
    bundle, df, ev = models(), dataset(), evaluation_section()
    feature_names, scaler = bundle["feature_names"], bundle["scaler"]

    st.title("Predict")
    st.markdown("Set the conditions at one location. Both models score it through exactly the same "
                "preprocessing as training: aspect to sine and cosine, categories to yes/no columns, "
                "then the scaler fitted on the training rows.")

    if "in_slope" not in st.session_state:
        set_inputs(typical_row(df), df)
    buttons = st.columns([1, 1, 1, 3])
    buttons[0].button("Typical values", on_click=load_example, args=("typical", df),
                      help="Median of every number and the most common class")
    buttons[1].button("A landslide point", on_click=load_example, args=("landslide", df),
                      help="A random landslide row from the dataset. Most rows were used in training, "
                           "so expect the models to recognise it.")
    buttons[2].button("A stable point", on_click=load_example, args=("stable", df),
                      help="A random stable row from the dataset, also likely seen in training")

    groups = st.columns(len(INPUT_GROUPS), gap="medium")
    for column, (title, cols) in zip(groups, INPUT_GROUPS.items()):
        with column.container(border=True):
            st.markdown(f"**{title}**")
            for col in cols:
                if col in config.DROPPED_COLUMNS:
                    continue
                input_widget(col, df)

    raw = pd.DataFrame([read_inputs()])
    X = pd.DataFrame(prepare_for_prediction(raw, feature_names, scaler), columns=feature_names)
    scores = {name: float(bundle[name].predict_proba(X)[0, 1]) for name in ["SVM (RBF)", "Random Forest"]}

    st.subheader("Scores")
    result_cols = st.columns(len(scores), gap="medium")
    for column, (name, score) in zip(result_cols, scores.items()):
        threshold = ev["models"][name]["youden"]["threshold"]
        flagged = score >= threshold
        with column.container(border=True):
            st.markdown(f"**{name}**")
            st.metric("Landslide score", f"{score:.2f}", label_visibility="collapsed")
            st.progress(score)
            st.markdown(f"Risk zone: **{config.risk_zone(score)}**")
            st.markdown(("**Flagged as landslide-prone**" if flagged else "Not flagged") +
                        f" at this model's tuned threshold of {threshold:.2f}")

    flags = {name: s >= ev["models"][name]["youden"]["threshold"] for name, s in scores.items()}
    if len(set(flags.values())) == 1:
        st.caption("Both models reach the same decision for this location.")
    else:
        st.caption("**The models disagree on this location**, which usually means it sits near the "
                   "boundary between the classes.")
    st.caption("Scores rank ground from safer to riskier. Both models were trained on classes balanced "
               "by SMOTE, and the SVM's scores come from Platt scaling, so a score is not the literal "
               f"chance that a landslide will happen here. Zones use fixed breaks at "
               f"{', '.join(f'{b:.1f}' for b in config.RISK_ZONE_BREAKS)}.")

    with st.expander("What the models received"):
        before = scaler.inverse_transform(X.to_numpy())[0]
        received = pd.DataFrame({"input": feature_names, "before scaling": before,
                                 "after scaling": X.iloc[0].to_numpy()})
        st.caption(f"{len(feature_names)} inputs in the order stored in `models/feature_names.json`. "
                   "Category columns that are not selected stay at 0 before scaling.")
        st.dataframe(received, hide_index=True,
                     column_config={"before scaling": st.column_config.NumberColumn(format="%.3f"),
                                    "after scaling": st.column_config.NumberColumn(format="%.3f")})


# ---------------------------------------------------------------------------
# Page 4: Rudraprayag demo map (Step 9)
# ---------------------------------------------------------------------------
def page_map() -> None:
    import streamlit.components.v1 as components

    st.title(f"{config.DEMO_DISTRICT} susceptibility map")
    if not config.DEMO_MAP_HTML.exists():
        st.info("The demo map has not been built yet. From the repo root, run `python -m src.demo_map`, "
                "then reload this page.")
        return

    demo = metadata().get("demo_map", {})
    if demo:
        # Four metrics in one row truncated the values ("Rando...", "2,145,..."), so the model name is a
        # line of text and the numbers get three wider columns.
        st.markdown(f"**Model:** {demo.get('model', '-')}")
        cols = st.columns(3)
        cols[0].metric("Cells scored", f"{demo.get('cells_scored', 0):,}", help="30 m cells, water excluded")
        cols[1].metric("Prediction time", f"{demo.get('timing_seconds', {}).get('predict', 0):.0f} s")
        projected = demo.get("projection_full_state", {}).get("predict_minutes")
        if projected is not None:
            cols[2].metric("Whole state, projected", f"{projected:.0f} min",
                           help="Linear projection from this run. Full-state mapping is Phase 3.")
        zones = demo.get("zones")
        if zones:
            st.dataframe(pd.DataFrame(zones), hide_index=True,
                         column_config={"share_percent": st.column_config.NumberColumn("share %", format="%.1f"),
                                        "area_km2": st.column_config.NumberColumn("area km²", format="%.1f")})
    components.html(config.DEMO_MAP_HTML.read_text(encoding="utf-8"), height=640)


# ---------------------------------------------------------------------------
def main() -> None:
    st.set_page_config(page_title=PROJECT_NAME, page_icon="⛰️", layout="wide")

    pages = st.navigation([
        st.Page(page_overview, title="Overview", icon=":material/landscape:", url_path="overview", default=True),
        st.Page(page_comparison, title="Model Comparison", icon=":material/compare_arrows:", url_path="comparison"),
        st.Page(page_predict, title="Predict", icon=":material/tune:", url_path="predict"),
        st.Page(page_map, title=f"{config.DEMO_DISTRICT} Map", icon=":material/map:", url_path="map"),
    ])

    meta = metadata()
    trained_on = meta.get("data_source")
    if config.IS_SYNTHETIC:
        st.markdown(WATERMARK_HTML, unsafe_allow_html=True)
        if pages.title != "Overview":  # the Overview page carries the full banner instead
            st.warning(f"**{config.SYNTHETIC_LABEL}.** Every number, figure and prediction on these pages comes "
                       "from a simulated dataset built to test the pipeline. None of it describes Uttarakhand.",
                       icon=":material/science:")
    elif trained_on and trained_on != config.DATA_SOURCE:
        st.error(f"The saved models were trained on **{trained_on}** data, but the project is set to "
                 f"**{config.DATA_SOURCE}**. Rerun Steps 4 to 7 before trusting anything here.")

    with st.sidebar:
        st.caption(f"Data source: **{config.DATA_SOURCE}** (`{config.DATASET_CSV.name}`)")
        written = meta.get("written", {}).get("evaluation")
        if written:
            st.caption(f"Evaluation written {written[:10]} (date shown in UTC)")

    pages.run()


main()
