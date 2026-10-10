"""Read-only views of existing SHAP/importance figures and their recorded context."""
import json
from pathlib import Path

import pandas as pd
import streamlit as st

from dashboard_v2 import ui
from src import config

GLOSSARY = {
    "slope": "Slope steepness, in degrees.",
    "elevation": "Height above sea level, in metres.",
    "curvature": "Profile shape of the terrain; the project's negative values indicate concave profiles.",
    "aspect": "Direction the slope faces, measured clockwise from north; −1 marks flat ground.",
    "aspect_sin": "Sine encoding of slope direction; paired with cosine to represent the circular angle.",
    "aspect_cos": "Cosine encoding of slope direction; paired with sine to represent the circular angle.",
    "twi": "Topographic wetness index: terrain-based tendency for water accumulation, not measured soil moisture.",
    "ndvi": "Vegetation greenness index derived from satellite imagery; not a direct measure of root strength.",
    "rainfall": "Long-term mean annual rainfall, not the rainfall of a particular storm.",
    "dist_roads": "Distance to the nearest mapped road, in metres.",
    "dist_streams": "Distance to the terrain-derived stream network, in metres.",
    "dist_faults": "Distance to mapped faults; excluded from the current benchmark inputs.",
    "soil_type": "Mapped soil classification; categories are encoded before prediction.",
    "lulc": "Mapped land-cover category, such as cropland or grassland.",
    "lithology": "Rock/geology category; excluded from the current benchmark inputs.",
}
FIGURES = {
    "shap_beeswarm": ("SHAP · All features and sample locations", "Random Forest",
        "Each dot represents a saved test location. Horizontal position is the feature's contribution to the RF score; "
        "colour indicates the plotted feature value. One-hot categories are indicators, not a continuous environmental quantity."),
    "shap_bar": ("SHAP · Average contribution magnitude", "Random Forest",
        "Mean absolute SHAP values summarize contribution size across the saved sample. They do not show whether a feature increases or decreases a particular score."),
    "shap_dependence_1_dist_roads": ("SHAP · Distance to roads", "Random Forest",
        "Distance to mapped roads versus its saved RF SHAP contribution. The pattern reflects model associations and sampling, not proof that roads caused the recorded landslides."),
    "shap_dependence_2_elevation": ("SHAP · Elevation", "Random Forest",
        "Elevation versus its saved RF SHAP contribution. The colour shows the interacting feature named on the saved plot; this is not a measured causal effect."),
    "shap_dependence_3_slope": ("SHAP · Slope steepness", "Random Forest",
        "Slope steepness versus its saved RF SHAP contribution. This describes the fitted model's associations in the recorded sample."),
    "shap_force_high_risk": ("SHAP · Recorded high-score example", "Random Forest",
        "Starting at the model baseline, red contributions increase and blue contributions decrease the saved RF score. Their sum reconstructs that example's output within the saved numerical tolerance."),
    "rf_feature_importance": ("Feature importance · Random Forest", "Random Forest",
        "Saved Random Forest feature importance, not new SHAP values. Impurity importance comes from training; "
        "permutation importance measures lost AUC on the original random held-out test set. Neither is a causal measurement."),
    "xgb_feature_importance": ("Feature importance · XGBoost", "XGBoost",
        "Saved XGBoost feature importance, not new SHAP values. Gain shares come from training; permutation importance "
        "measures lost AUC on the original random held-out test set. These have different units, and neither is a saved XGBoost SHAP explanation."),
}


def feature_description(name: str) -> str:
    for prefix, label in (("lulc_", "land-cover"), ("soil_type_", "soil")):
        if name.startswith(prefix):
            return f"Encoded {label} category: {name[len(prefix):]}. Category indicators follow the saved encoding and scaling."
    return GLOSSARY.get(name, "Saved model feature; retain the original feature name when consulting the plot.")


def figure_path(key: str) -> Path:
    # Fixed known files, never an arbitrary path supplied by figure metadata.
    if key not in FIGURES:
        raise KeyError("Unknown saved figure")
    return config.FIGURES_DIR / ("shap" if key.startswith("shap_") else "") / (key + ".png")


def page(helpers) -> None:
    ui.page_header("Explainability", "Explore existing Random Forest SHAP explanations and saved model importance figures.")
    st.markdown("SHAP describes model-associated contributions. These associations do not establish causes of landslides. "
                "No explanations are calculated for the conditions entered on Location Assessment.")
    summary_path = config.FIGURES_DIR / "shap/shap_summary.json"
    if not summary_path.is_file():
        ui.availability("Explanations unavailable.", "No saved SHAP summary is available. Explanations are not computed here.")
        return
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        sample = summary["sample"]
    except (OSError, ValueError, KeyError):
        ui.availability("Explanations unavailable.", "The saved SHAP summary could not be read.", warning=True)
        return
    if config.RF_MODEL_PATH.is_file() and summary.get("rf_model_mtime", 0) < config.RF_MODEL_PATH.stat().st_mtime:
        ui.availability("SHAP timestamp warning.", "The model file has a newer modification time. Timestamp order alone "
                        "does not establish model identity; verify provenance before interpretation.", warning=True)
    columns = st.columns(4)
    ui.metric_card(columns[0], "shap-count", "Locations explained", f"{sample['rows']:,}",
                   help=f"{sample['landslide']} landslide and {sample['stable']} stable, from the held-out test set")
    ui.metric_card(columns[1], "shap-baseline", "Model baseline (expected output)", f"{summary['base_value']:.3f}",
                   help="TreeExplainer expected RF output; not real-world landslide prevalence or the mean of the displayed sample")
    ui.metric_card(columns[2], "shap-error", "Largest additivity error", f"{summary['additivity_max_error']:.1e}")
    ui.metric_card(columns[3], "shap-time", "Saved computation time", f"{summary['timing_seconds']['explain']:.0f} s")
    ui.caption(f"Saved RF SHAP sample: {sample['rows']} {sample['from']} locations, {sample['landslide']} landslide and "
               f"{sample['stable']} stable; seed {sample['seed']}. Original random held-out benchmark, not spatial validation.")
    ui.caption(f"Source model recorded by the saved summary: {Path(summary['model']).name}. "
               f"Computed {summary['written'][:10]} with SHAP {summary['shap_version']}; {summary['explainer']}.")

    with ui.panel("explanation-selected-figure"):
        chosen = st.selectbox("Saved figure", list(FIGURES), format_func=lambda key: FIGURES[key][0], key="himshield-saved-figure")
        title, model, note = FIGURES[chosen]
        st.subheader(title)
        ui.caption(f"Figure model: {model}. " + ("Saved RF SHAP test sample described above." if chosen.startswith("shap_")
                   else "Original saved feature-importance analysis; the 500-location SHAP sample above does not describe this figure."))
        ui.figure(figure_path(chosen), caption=note)
        ui.caption(note)
        if chosen == "shap_force_high_risk":
            point = summary.get("force_plot_point", {})
            if point:
                st.markdown(f"Recorded held-out example, test index **{point['test_index']}**, label "
                            f"**{'recorded landslide' if point['landslide'] else 'sampled stable point'}**; "
                            f"RF susceptibility score **{ui.percent(point['rf_score'])}**. This is a saved example, not your submitted assessment.")

    with ui.panel("explanation-reading-guide"):
        st.subheader("How to read the RF explanations")
        st.markdown(f"The saved baseline is **{summary['base_value']:.6f}** on the 0–1 model-score scale. "
                    "Tree-path-dependent SHAP uses training-path frequencies as its reference distribution; no separate background sample was supplied. "
                    "The baseline is not a measured landslide rate.")
        st.markdown("For each saved RF example: **baseline + all feature contributions ≈ model output**. "
                    "A positive contribution raises the score relative to the baseline; a negative contribution lowers it. "
                    "A contribution of +0.10 represents 10 percentage points of model score, not a 10% real-world event risk.")
        ui.caption(ui.SCORE_NOTE + " Saved figures retain their original units and labels.")
    permutation = list(helpers.metadata().get("rf", {}).get("feature_importance_permutation", {}))
    ranking = pd.DataFrame([{"SHAP rank": i, "Feature": feature, "Plain-English meaning": feature_description(feature),
        "Mean |SHAP|": value, "Permutation rank (original benchmark)": permutation.index(feature) + 1 if feature in permutation else None}
        for i, (feature, value) in enumerate(summary["mean_abs_shap"].items(), start=1)])
    with st.expander("Saved Random Forest feature ranking"):
        st.dataframe(ranking, hide_index=True, use_container_width=True,
                     column_config={"Mean |SHAP|": st.column_config.NumberColumn(format="%.6f")})
        ui.caption("All saved RF SHAP importance values are retained. Agreement with permutation ranking does not prove robustness or causality. "
                   "Permutation importance measures lost AUC; SHAP measures movement of model output.")
    with st.expander("Feature glossary", expanded=False):
        # Explain every encoded feature used in the saved SHAP analysis, not only its top three.
        st.dataframe(ranking[["Feature", "Plain-English meaning"]], hide_index=True, use_container_width=True)
