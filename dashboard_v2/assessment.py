"""Submitted manual assessments using the unchanged Phase 2 transformation."""
import json
import math
from numbers import Real

import pandas as pd
import streamlit as st

from dashboard_v2 import ui
from src import config

INPUT_GROUPS = {
    "Terrain": ["slope", "elevation", "curvature", "aspect", "twi"],
    "Vegetation & Rainfall": ["ndvi", "rainfall"],
    "Roads & Drainage": ["dist_roads", "dist_streams", "dist_faults"],
    "Land Cover & Soil": ["lulc", "soil_type", "lithology"],
}
MODEL_PATHS = {"Random Forest": "RF_MODEL_PATH", "SVM (RBF)": "SVM_MODEL_PATH", "XGBoost": "XGB_MODEL_PATH"}
RESULT_KEY = "himshield-assessment-result"


@st.cache_resource
def saved_object(path: str, stamp: float):
    import joblib

    return joblib.load(path)


def input_errors(raw: dict, df: pd.DataFrame, helpers) -> list[str]:
    """Reject incomplete/invalid conditions before the original transform runs."""
    errors = []
    for feature in config.active_numeric_features():
        value = raw.get(feature)
        label = helpers.FACTORS[feature][0]
        if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
            errors.append(f"{label}: enter a finite numeric value.")
            continue
        if feature == "aspect":
            valid = value == -1 or 0 <= value <= 359
        else:
            low, high, _ = helpers.slider_bounds(df, feature)
            valid = low <= value <= high
        if not valid:
            errors.append(f"{label}: use the range shown in the input control.")
    for feature in config.active_categorical_features():
        if raw.get(feature) not in helpers.category_options(df, feature):
            errors.append(f"{helpers.FACTORS[feature][0]}: choose an available category.")
    return errors


def score_conditions(raw: dict, feature_names: list[str], scaler, models: dict, transform) -> dict:
    """Same frame, feature order and predict_proba call as the original page."""
    frame = pd.DataFrame([raw])
    X = pd.DataFrame(transform(frame, feature_names, scaler), columns=feature_names)
    if not all(math.isfinite(float(v)) for v in X.to_numpy().ravel()):
        raise ValueError("The saved transformation could not produce finite model inputs.")
    scores = {name: float(model.predict_proba(X)[0, 1]) for name, model in models.items()}
    if not all(math.isfinite(score) and 0 <= score <= 1 for score in scores.values()):
        raise ValueError("A saved model returned an invalid susceptibility score.")
    return scores


def agreement(scores: dict, thresholds: dict) -> tuple[str, str]:
    """Compare real score classes and explicitly retrospective decision rules."""
    if len(scores) < 2:
        return "Model agreement unavailable: fewer than two models produced scores.", ""
    classes = {name: config.risk_zone(score) for name, score in scores.items()}
    if len(set(classes.values())) == 1:
        class_note = f"All {len(scores)} assessed models assign the same susceptibility class: **{next(iter(classes.values()))}**."
    else:
        class_note = "**Susceptibility classes differ:** " + "; ".join(f"{name}: {zone}" for name, zone in classes.items()) + "."
    decisions = {name: scores[name] >= thresholds[name] for name in scores if name in thresholds}
    if len(decisions) < 2:
        return class_note, "Benchmark decision agreement unavailable: fewer than two saved thresholds are available."
    flagged = sum(decisions.values())
    decision_note = f"{flagged} of {len(decisions)} models meet their retrospective benchmark threshold. "
    decision_note += ("The benchmark decisions agree." if len(set(decisions.values())) == 1 else "**The benchmark decisions differ.**")
    return class_note, decision_note


def load_example(kind: str, df: pd.DataFrame, helpers) -> None:
    # Keep the existing sampling, category handling and slider snapping exactly.
    helpers.load_example(kind, df)


def page(helpers, chart, file_stamp) -> None:
    ui.page_header("Location Assessment", "Compare saved-model outputs for manually entered terrain conditions.")
    st.markdown("This interface does not extract terrain features from GPS coordinates. "
                "Set the conditions and select **Assess Conditions** to update the results.")
    ui.caption(ui.SCORE_NOTE + " Percentages below express the model's 0–1 score, not the chance of an event.")
    ui.caption(ui.THRESHOLD_NOTE)

    df = helpers.load_dataset(helpers.mtime(config.DATASET_CSV))
    if df is None or df.empty:
        ui.availability("Assessment inputs unavailable.", "The saved development dataset is missing or empty.")
        return
    required = config.active_numeric_features() + config.active_categorical_features()
    if any(feature not in df for feature in required):
        ui.availability("Assessment inputs incomplete.", "The saved dataset does not contain every required feature.")
        return
    if not all(p.is_file() for p in (config.SCALER_PATH, config.FEATURE_NAMES_PATH)):
        ui.availability("Preprocessing unavailable.", "The saved scaler or feature contract is missing. Assessment is unavailable.")
        return
    try:
        feature_names = json.loads(config.FEATURE_NAMES_PATH.read_text(encoding="utf-8"))
        scaler = saved_object(str(config.SCALER_PATH), file_stamp(config.SCALER_PATH))
    except Exception:
        ui.availability("Preprocessing unavailable.", "The saved scaler or feature contract could not be loaded.", warning=True)
        return
    models, unavailable = {}, []
    for name, attribute in MODEL_PATHS.items():
        path = getattr(config, attribute)
        if not path.is_file():
            unavailable.append(name)
            continue
        try:
            models[name] = saved_object(str(path), file_stamp(path))
        except Exception:
            unavailable.append(name)
    if unavailable:
        ui.availability("Some model results are unavailable.", ", ".join(unavailable) +
                        ". Assessments use only models that can load; no model is rebuilt.", warning=True)
    if not models:
        ui.availability("Assessment unavailable.", "No saved model could be loaded.")
        return
    ev = helpers.metadata().get("evaluation", {}).get("models", {})
    thresholds = {}
    for name in models:
        threshold = ev.get(name, {}).get("youden", {}).get("threshold")
        if not isinstance(threshold, bool) and isinstance(threshold, Real) and math.isfinite(threshold) and 0 <= threshold <= 1:
            thresholds[name] = threshold
    # A previous submission belongs to the exact file versions used at that time.
    sources = tuple((str(p), p.stat().st_mtime_ns, p.stat().st_size) for p in
                    (config.SCALER_PATH, config.FEATURE_NAMES_PATH, config.METADATA_PATH,
                     *(getattr(config, MODEL_PATHS[name]) for name in models)) if p.is_file())
    previous = st.session_state.get(RESULT_KEY)
    if previous and previous["sources"] != sources:
        st.session_state.pop(RESULT_KEY)
        ui.availability("Submit a new assessment.", "Saved model availability or supporting files changed since the last assessment.")

    if "in_slope" not in st.session_state:
        helpers.set_inputs(helpers.typical_row(df), df)
    st.subheader("1. Choose a starting point")
    columns = st.columns(3)
    for column, label, kind in zip(columns, ("Typical values", "A landslide point", "A stable point"),
                                   ("typical", "landslide", "stable")):
        column.button(label, on_click=load_example, args=(kind, df, helpers),
                      help="Load the existing preset into the form; submit it to assess the conditions.")
    ui.caption("Presets retain the original sampled examples and input rounding. They are demonstrations, not independent validation cases.")

    st.subheader("2. Enter terrain conditions")
    with st.form("himshield-assessment", clear_on_submit=False):
        for title, features in INPUT_GROUPS.items():
            with ui.panel("assessment-" + title.lower().replace(" & ", "-").replace(" ", "-")):
                st.markdown(f"**{title}**")
                for feature in features:
                    if feature in config.DROPPED_COLUMNS:
                        continue
                    if feature == "aspect":
                        # Form widgets reach the server together. Keep direction editable
                        # so leaving flat-ground mode does not require a second submit.
                        st.checkbox("Flat ground (no aspect)", key="in_flat")
                        st.slider("Aspect, degrees from north", 0.0, 359.0, step=1.0, key="in_aspect",
                                  help="Direction is ignored when Flat ground is selected.")
                    else:
                        helpers.input_widget(feature, df)
        submitted = st.form_submit_button("Assess Conditions", type="primary", width="stretch")

    if submitted:
        try:
            raw = helpers.read_inputs()
            errors = input_errors(raw, df, helpers)
        except (KeyError, TypeError, ValueError):
            errors = ["Complete every terrain input before submitting an assessment."]
        if errors:
            for error in errors:
                st.error(error)
        else:
            try:
                scores = score_conditions(raw, feature_names, scaler, models, helpers.prepare_for_prediction)
                st.session_state[RESULT_KEY] = {"raw": dict(raw), "scores": scores,
                    "thresholds": dict(thresholds), "sources": sources}
            except Exception:
                st.error("Assessment could not be completed with the saved models. No new result was recorded.")

    result = st.session_state.get(RESULT_KEY)
    if result is None:
        ui.availability("Ready to assess.", "Review the conditions above, then select Assess Conditions. No assessment has been submitted yet.")
        return
    st.subheader("3. Latest successful assessment")
    ui.caption("These results belong to the submitted conditions shown below. Editing the form or loading a preset does not update them until you submit.")
    with st.expander("Submitted terrain conditions", expanded=True):
        rows = [{"Condition": helpers.FACTORS[name][0], "Submitted value":
                 "Flat ground (−1)" if name == "aspect" and value == -1 else str(value),
                 "Unit": config.FEATURE_UNITS.get(name, "")} for name, value in result["raw"].items()]
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    scores, thresholds = result["scores"], result["thresholds"]
    st.altair_chart(chart(scores, thresholds), use_container_width=True)
    ui.caption("Bars: relative susceptibility scores shown as percentages. Bands: unchanged susceptibility classes. "
               "White ticks, when available, mark retrospective test-selected Youden thresholds.")
    columns = st.columns(len(MODEL_PATHS), gap="medium")
    for i, (column, name) in enumerate(zip(columns, MODEL_PATHS)):
        with column, ui.panel("prediction-" + str(i)):
            st.markdown(f"**{name}**")
            score = scores.get(name)
            st.metric("Susceptibility score (%)", ui.percent(score) if score is not None else "—")
            if score is None:
                st.caption("Saved model unavailable; no score was produced.")
                continue
            st.markdown(f"Susceptibility class: **{config.risk_zone(score)}**")
            if name in thresholds:
                threshold = thresholds[name]
                st.caption(("Meets" if score >= threshold else "Below") +
                           f" retrospective benchmark threshold: {ui.percent(threshold)} of the model score.")
            else:
                st.caption("Retrospective benchmark threshold unavailable.")
            if "auc" in ev.get(name, {}):
                st.caption(f"Benchmark ROC-AUC (%) {ui.percent(ev[name]['auc'])}")
    class_note, decision_note = agreement(scores, thresholds)
    with ui.panel("assessment-agreement"):
        st.markdown(class_note)
        if decision_note:
            st.markdown(decision_note)
        if "Random Forest" in scores and "SVM (RBF)" in scores:
            st.caption("Random Forest minus SVM score: " +
                       ui.percentage_points(scores["Random Forest"] - scores["SVM (RBF)"]) + " (score percentage points).")
    ui.caption("All three saved models used SMOTE-balanced training data; the SVM uses Platt scaling. " + ui.SCORE_NOTE)
