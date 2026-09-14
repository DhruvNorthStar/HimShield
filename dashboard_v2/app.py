"""
Phase 3 dashboard: the Phase 2 dashboard extended to six pages.

    streamlit run dashboard_v2/app.py

Pages:
    1 Overview          Phase 2, unchanged (its own function)
    2 Model Comparison  Phase 2, unchanged (its own function)
    3 Predict           upgraded: Random Forest and SVM side by side, scores as bars on one axis with the
                        risk-zone bands and each model's tuned threshold
    4 Rudraprayag Map   Phase 2 page when online; a static copy of the map when offline
    5 Explainability    SHAP figures from src/explain_shap.py
    6 Full State Map    outputs/susceptibility_map_uk.html from src/map_generator_full.py, with the
                        Rudraprayag fallback until the state raster exists; a static copy when offline

Reuse, not copies: dashboard/app.py ends with a bare `main()` call, so importing it would launch the whole
Phase 2 app. load_phase2_dashboard() reads that file, leaves out only that final call, and runs the rest
as a module, so every Phase 2 page, loader and widget helper is used as it is, including its
@st.cache_resource model loading. dashboard/app.py itself is not changed.

Offline (college wifi): everything is local except the interactive web maps, which load Leaflet from CDNs
and draw basemap tiles from the internet. A quick connection test decides; offline, both map pages show a
static map drawn locally from the same rasters, boundaries and landslide points instead of an empty frame.
Force offline mode to test it with LSM_OFFLINE=1, or by adding ?offline=1 to the page address.
"""
import ast
import io
import json
import os
import socket
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    # Streamlit puts dashboard_v2/ on the import path, not the repo root, so `from src import` needs this.
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from src import config  # noqa: E402
from src.demo_map import ZONE_COLOURS  # noqa: E402

PHASE2_APP = ROOT / "dashboard" / "app.py"
SHAP_DIR = config.FIGURES_DIR / "shap"
SHAP_SUMMARY = SHAP_DIR / "shap_summary.json"
STATE_MAP_HTML = config.OUTPUTS_DIR / "susceptibility_map_uk.html"
DEMO_SLUG = config.DEMO_DISTRICT.lower().replace(" ", "_")
STATE_ZONES = config.PROCESSED_DIR / "susceptibility_uk_zones.tif"
DEMO_ZONES = config.PROCESSED_DIR / f"susceptibility_{DEMO_SLUG}_zones.tif"
DEMO_PROBABILITY_PHASE2 = config.PROCESSED_DIR / f"susceptibility_{DEMO_SLUG}_rf.tif"
ONLINE_HOSTS = ("cdn.jsdelivr.net", "tile.openstreetmap.org")
MODEL_NAMES = ["Random Forest", "SVM (RBF)"]


# ---------------------------------------------------------------------------
# Phase 2 reuse
# ---------------------------------------------------------------------------
def load_phase2_dashboard() -> types.ModuleType:
    """dashboard/app.py as a module, without the bare main() call at its end."""
    stamp = PHASE2_APP.stat().st_mtime
    cached = sys.modules.get("lsm_phase2_dashboard")
    if cached is not None and getattr(cached, "_lsm_stamp", None) == stamp:
        return cached
    tree = ast.parse(PHASE2_APP.read_text(encoding="utf-8"), filename=str(PHASE2_APP))
    tree.body = [node for node in tree.body
                 if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
                         and isinstance(node.value.func, ast.Name) and node.value.func.id == "main")]
    module = types.ModuleType("lsm_phase2_dashboard")
    module.__file__ = str(PHASE2_APP)
    exec(compile(tree, str(PHASE2_APP), "exec"), module.__dict__)  # noqa: S102 - our own repository file
    module._lsm_stamp = stamp
    sys.modules["lsm_phase2_dashboard"] = module
    return module


p2 = load_phase2_dashboard()


def file_stamp(path: Path) -> float:
    return path.stat().st_mtime if path.exists() else 0.0


# ---------------------------------------------------------------------------
# Online or offline
# ---------------------------------------------------------------------------
@st.cache_data(ttl=60, show_spinner=False)
def internet_reachable() -> bool:
    """Can this machine reach the map CDN and the tile server? Checked at most once a minute."""
    for host in ONLINE_HOSTS:
        try:
            with socket.create_connection((host, 443), timeout=1.5):
                pass
        except OSError:
            return False
    return True


def is_offline() -> bool:
    forced = os.environ.get("LSM_OFFLINE") == "1" or st.query_params.get("offline") == "1"
    return forced or not internet_reachable()


def offline_notice(what: str) -> None:
    st.info(f"**Offline:** the interactive {what} needs internet for its map library and basemap tiles, so "
            "this is a static copy drawn on this computer from the same rasters, boundaries and landslide "
            "points. It shows no basemap and cannot be clicked.", icon=":material/wifi_off:")


@st.cache_data(show_spinner="Drawing a static copy of the map (works offline)...")
def static_map_png(zones_path: str, kind: str, focus: str, stamp: float) -> bytes:
    """A matplotlib rendering of zones, district and state boundaries, and landslide points."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.patheffects as pe
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    from rasterio.transform import array_bounds

    from src import map_generator_full as mg

    districts, state, labels, state_exact = mg.load_boundaries()
    landslides = mg.load_landslides(state_exact)
    districts, state, labels = (g.to_crs(config.PROJECT_CRS) for g in (districts, state, labels))
    fig, ax = plt.subplots(figsize=(9, 7.6), dpi=130)
    handles = []
    shares = None
    if zones_path:
        zones = mg.read_zones({"path": Path(zones_path), "kind": kind}, max_pixels=1600)
        grid = zones["grid"]
        rgba = np.zeros(grid.shape + (4,))
        for i, colour in enumerate(ZONE_COLOURS, start=1):
            rgba[grid == i] = [int(colour[j:j + 2], 16) / 255 for j in (1, 3, 5)] + [0.9]
        left, bottom, right, top = array_bounds(*grid.shape, zones["transform"])
        ax.imshow(rgba, extent=(left, right, bottom, top), interpolation="nearest", zorder=1)
        shares = zones["shares"]
        edges = [0.0, *config.RISK_ZONE_BREAKS, 1.0]
        handles += [Patch(facecolor=c, edgecolor="white", label=f"{n} ({edges[i]:.1f} to {edges[i + 1]:.1f}): {s:.1f}%")
                    for i, (n, c, s) in enumerate(zip(config.RISK_ZONES, ZONE_COLOURS, shares))]
    districts.boundary.plot(ax=ax, color="#3a3a38", linewidth=0.7, zorder=2)
    state.boundary.plot(ax=ax, color="#0b0b0b", linewidth=1.6, zorder=3)
    if landslides["points"] is not None and len(landslides["points"]):
        pts = landslides["points"].to_crs(config.PROJECT_CRS)
        ax.scatter(pts.geometry.x, pts.geometry.y, s=14, c="#1a1a1a", edgecolors="white", linewidths=0.7, zorder=4)
        handles.append(Line2D([], [], marker="o", linestyle="", markerfacecolor="#1a1a1a", markeredgecolor="white",
                              label=f"{landslides['label']}: {len(pts)}"))

    if focus == "state":
        xmin, ymin, xmax, ymax = state.total_bounds
    else:
        match = districts[districts["district"] == focus]
        xmin, ymin, xmax, ymax = match.total_bounds
    pad = 0.04 * max(xmax - xmin, ymax - ymin)
    ax.set_xlim(xmin - pad, xmax + pad)
    ax.set_ylim(ymin - pad, ymax + pad)
    for _, row in labels.iterrows():
        x, y = row.geometry.x, row.geometry.y
        if xmin - pad <= x <= xmax + pad and ymin - pad <= y <= ymax + pad:
            ax.text(x, y, row["district"], fontsize=8 if focus == "state" else 10, ha="center", va="center",
                    color="#0b0b0b", zorder=5, path_effects=[pe.withStroke(linewidth=3, foreground="white")])
    ax.set_aspect("equal")
    ax.set_axis_off()
    if handles:
        # Outside the map, to the right: inside, it covered the southern districts.
        ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(1.01, 1.0), fontsize=7.5, frameon=False,
                  borderaxespad=0)
    title = "Landslide susceptibility, Random Forest: " + ("Uttarakhand" if focus == "state" else focus)
    ax.set_title(title, loc="left", fontsize=11, fontweight="semibold")
    footer = "Static offline copy: no basemap. "
    if config.IS_SYNTHETIC:
        fig.text(0.5, 0.5, config.SYNTHETIC_LABEL, fontsize=30, color="#D55E00", alpha=0.10, ha="center",
                 va="center", rotation=24, fontweight="bold")
        footer += f"{config.SYNTHETIC_LABEL}."
    fig.text(0.01, 0.01, footer, fontsize=7, color="#52514e")
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", bbox_inches="tight")
    plt.close(fig)
    return buffer.getvalue()


def raster_summary(path: Path) -> dict:
    """The run summary predict_raster_full.py stores in a zones GeoTIFF's tags."""
    if not path.exists():
        return {}
    import rasterio

    with rasterio.open(path) as src:
        tags = src.tags()
    return json.loads(tags["PHASE3_SUMMARY"]) if "PHASE3_SUMMARY" in tags else {}


# ---------------------------------------------------------------------------
# Page 3: Predict, upgraded
# ---------------------------------------------------------------------------
def probability_chart(scores: dict, thresholds: dict):
    """Both scores on one 0 to 1 axis, over the five zone bands, with each model's tuned threshold."""
    import altair as alt

    edges = [0.0, *config.RISK_ZONE_BREAKS, 1.0]
    bands = pd.DataFrame({"zone": config.RISK_ZONES, "start": edges[:-1], "end": edges[1:],
                          "middle": [(a + b) / 2 for a, b in zip(edges[:-1], edges[1:])]})
    bars = pd.DataFrame({"model": list(scores), "score": list(scores.values()),
                         "threshold": [thresholds[m] for m in scores],
                         "zone": [config.risk_zone(s) for s in scores.values()],
                         "decision": ["flagged" if scores[m] >= thresholds[m] else "not flagged" for m in scores]})
    x = alt.X("score:Q", scale=alt.Scale(domain=[0, 1]), title="Landslide score (0 safer, 1 riskier)",
              axis=alt.Axis(values=edges, format=".1f", grid=False))
    y = alt.Y("model:N", sort=list(scores), title=None, axis=alt.Axis(labelFontSize=13, labelPadding=8))
    band_layer = alt.Chart(bands).mark_rect(opacity=0.45).encode(
        x=alt.X("start:Q", scale=alt.Scale(domain=[0, 1])), x2="end:Q",
        color=alt.Color("zone:N", scale=alt.Scale(domain=config.RISK_ZONES, range=ZONE_COLOURS), legend=None),
        tooltip=[alt.Tooltip("zone:N", title="Risk zone"), alt.Tooltip("start:Q", title="from", format=".1f"),
                 alt.Tooltip("end:Q", title="to", format=".1f")])
    band_labels = alt.Chart(bands).mark_text(fontSize=11, color="#52514e", baseline="bottom").encode(
        x=alt.X("middle:Q", scale=alt.Scale(domain=[0, 1])), y=alt.value(-6), text="zone:N")
    tooltip = [alt.Tooltip("model:N", title="Model"), alt.Tooltip("score:Q", title="Score", format=".3f"),
               alt.Tooltip("zone:N", title="Zone"), alt.Tooltip("threshold:Q", title="Tuned threshold", format=".2f"),
               alt.Tooltip("decision:N", title="Decision")]
    bar_layer = alt.Chart(bars).mark_bar(size=26, color="#2b2b29", cornerRadiusEnd=4).encode(x=x, y=y, tooltip=tooltip)
    value_layer = alt.Chart(bars).mark_text(align="left", dx=6, fontSize=13, fontWeight="bold", color="#0b0b0b").encode(
        x="score:Q", y=y, text=alt.Text("score:Q", format=".2f"))
    threshold_layer = alt.Chart(bars).mark_tick(color="#ffffff", thickness=3, size=40).encode(
        x="threshold:Q", y=y, tooltip=[alt.Tooltip("model:N", title="Model"),
                                        alt.Tooltip("threshold:Q", title="Tuned threshold", format=".2f")])
    return (band_layer + band_labels + bar_layer + threshold_layer + value_layer).properties(
        height=150, padding={"top": 22, "left": 5, "right": 30, "bottom": 5}).configure_view(strokeWidth=0)


def page_predict_v2() -> None:
    bundle, df, ev = p2.models(), p2.dataset(), p2.evaluation_section()
    feature_names, scaler = bundle["feature_names"], bundle["scaler"]

    st.title("Predict: Random Forest and SVM side by side")
    st.markdown("Set the conditions at one location. Both models score it through the same preprocessing as "
                "training, and the chart puts both scores on one scale, over the five risk zones.")

    if "in_slope" not in st.session_state:
        p2.set_inputs(p2.typical_row(df), df)
    buttons = st.columns([1, 1, 1, 3])
    buttons[0].button("Typical values", on_click=p2.load_example, args=("typical", df),
                      help="Median of every number and the most common class")
    buttons[1].button("A landslide point", on_click=p2.load_example, args=("landslide", df),
                      help="A random landslide row from the dataset (most were used in training)")
    buttons[2].button("A stable point", on_click=p2.load_example, args=("stable", df),
                      help="A random stable row from the dataset (most were used in training)")

    groups = st.columns(len(p2.INPUT_GROUPS), gap="medium")
    for column, (title, cols) in zip(groups, p2.INPUT_GROUPS.items()):
        with column.container(border=True):
            st.markdown(f"**{title}**")
            for col in cols:
                if col not in config.DROPPED_COLUMNS:
                    p2.input_widget(col, df)

    raw = pd.DataFrame([p2.read_inputs()])
    X = pd.DataFrame(p2.prepare_for_prediction(raw, feature_names, scaler), columns=feature_names)
    scores = {name: float(bundle[name].predict_proba(X)[0, 1]) for name in MODEL_NAMES}
    thresholds = {name: ev["models"][name]["youden"]["threshold"] for name in MODEL_NAMES}

    st.subheader("Scores")
    st.altair_chart(probability_chart(scores, thresholds), use_container_width=True)
    st.caption("Bars: each model's landslide score. White tick: that model's tuned (Youden) threshold; a bar that "
               "passes its tick is flagged as landslide-prone. Coloured bands: the five risk zones.")

    cards = st.columns(len(MODEL_NAMES), gap="medium")
    for column, name in zip(cards, MODEL_NAMES):
        score, threshold = scores[name], thresholds[name]
        with column.container(border=True):
            st.markdown(f"**{name}**")
            st.metric("Landslide score", f"{score:.3f}", label_visibility="collapsed")
            st.markdown(f"Risk zone: **{config.risk_zone(score)}**  \n"
                        + ("**Flagged as landslide-prone**" if score >= threshold else "Not flagged")
                        + f" at its tuned threshold of {threshold:.2f}  \n"
                        + f"Test AUC {ev['models'][name]['auc']:.3f}")

    difference = scores["Random Forest"] - scores["SVM (RBF)"]
    same = (scores["Random Forest"] >= thresholds["Random Forest"]) == (scores["SVM (RBF)"] >= thresholds["SVM (RBF)"])
    st.markdown(f"Random Forest minus SVM: **{difference:+.3f}**. " +
                ("Both models reach the same decision." if same else
                 "**The models disagree on this location**, which usually means it sits near the boundary "
                 "between the classes."))
    st.caption("Scores rank ground from safer to riskier. Both models were trained on classes balanced by SMOTE, "
               "and the SVM's scores come from Platt scaling, so a score is not the literal chance that a "
               "landslide will happen here.")


# ---------------------------------------------------------------------------
# Page 4: Rudraprayag map
# ---------------------------------------------------------------------------
def page_rudraprayag_v2() -> None:
    if not is_offline():
        p2.page_map()
        return
    st.title(f"{config.DEMO_DISTRICT} susceptibility map")
    offline_notice("Rudraprayag map")
    source = (DEMO_PROBABILITY_PHASE2, "probability") if DEMO_PROBABILITY_PHASE2.exists() else (
        (DEMO_ZONES, "zones") if DEMO_ZONES.exists() else (None, None))
    if source[0] is None:
        st.info("The demo map has not been built yet. Run `python -m src.demo_map`.")
        return
    zones = p2.metadata().get("demo_map", {}).get("zones")
    if zones:
        st.dataframe(pd.DataFrame(zones), hide_index=True)
    st.image(static_map_png(str(source[0]), source[1], config.DEMO_DISTRICT, file_stamp(source[0])))


# ---------------------------------------------------------------------------
# Page 5: Explainability
# ---------------------------------------------------------------------------
SHAP_NOTES = {
    "shap_beeswarm": ("Every factor, every location",
                      "Each dot is one held-out test location. Its position shows how far that factor pushed the "
                      "landslide score up (right) or down (left); its colour shows whether the factor's value was "
                      "high or low there. Factors are ordered by average effect."),
    "shap_bar": ("Average effect",
                 "Mean absolute SHAP value: how much each factor moves the score on average, whichever direction. "
                 "It is the closest SHAP equivalent of feature importance."),
    "shap_force_high_risk": ("One high-risk location",
                             "How a single landslide location got its high score: starting from the average score, "
                             "red factors push it up and blue ones push it down, and together they add up exactly "
                             "to the model's score for that location."),
}


def page_explainability() -> None:
    st.title("Explainability: what drives the Random Forest")
    st.markdown("SHAP splits each prediction into one contribution per factor. The contributions add up exactly "
                "to the model's score, so the explanation is checked against the prediction itself.")
    if not SHAP_SUMMARY.exists():
        st.info("No SHAP results yet. From the repo root run `python src/explain_shap.py` (about 30 seconds), "
                "then reload this page.")
        return
    summary = json.loads(SHAP_SUMMARY.read_text(encoding="utf-8"))
    if config.RF_MODEL_PATH.exists() and summary.get("rf_model_mtime", 0) < config.RF_MODEL_PATH.stat().st_mtime:
        st.warning("These SHAP results were computed for an older Random Forest. Rerun `python src/explain_shap.py`.")

    sample = summary["sample"]
    cols = st.columns(4)
    cols[0].metric("Locations explained", f"{sample['rows']:,}",
                   help=f"{sample['landslide']} landslide and {sample['stable']} stable, from the held-out test set")
    cols[1].metric("Average score", f"{summary['base_value']:.3f}",
                   help="The starting point every explanation adds contributions to")
    cols[2].metric("Largest additivity error", f"{summary['additivity_max_error']:.1e}",
                   help="How far contributions plus the average score differ from the model's own score")
    cols[3].metric("Computation time", f"{summary['timing_seconds']['explain']:.0f} s")

    permutation = list(p2.metadata().get("rf", {}).get("feature_importance_permutation", {}))
    ranking = pd.DataFrame([{"SHAP rank": i, "Factor": factor, "Mean |SHAP|": value,
                             "Permutation rank (Step 6)": permutation.index(factor) + 1 if factor in permutation else None}
                            for i, (factor, value) in enumerate(summary["mean_abs_shap"].items(), start=1)]).head(12)

    figures = {Path(f).stem: ROOT / f for f in summary["figures"]}
    tab_names = [SHAP_NOTES["shap_beeswarm"][0], SHAP_NOTES["shap_bar"][0], "Dependence (top 3)",
                 SHAP_NOTES["shap_force_high_risk"][0], "Ranking table"]
    tabs = st.tabs(tab_names)
    for tab, key in zip(tabs[:2], ["shap_beeswarm", "shap_bar"]):
        with tab:
            left, right = st.columns([3, 2], gap="large")
            with left:
                if key in figures and figures[key].exists():
                    st.image(str(figures[key]))
            with right:
                st.markdown(SHAP_NOTES[key][1])
    with tabs[2]:
        st.markdown("How the score changes across each of the three strongest factors. The shape shows where "
                    "risk rises or falls, for example a peak at a middle range of slope.")
        dependence = [p for k, p in figures.items() if k.startswith("shap_dependence_")]
        for column, path in zip(st.columns(max(1, len(dependence))), dependence):
            with column:
                st.image(str(path))
    with tabs[3]:
        point = summary.get("force_plot_point", {})
        if "shap_force_high_risk" in figures and figures["shap_force_high_risk"].exists():
            st.image(str(figures["shap_force_high_risk"]))
        st.markdown(SHAP_NOTES["shap_force_high_risk"][1] +
                    (f" This location scored {point['rf_score']:.3f}." if point else ""))
    with tabs[4]:
        st.dataframe(ranking, hide_index=True,
                     column_config={"Mean |SHAP|": st.column_config.NumberColumn(format="%.4f")})
        st.caption("Two independent ways of ranking factors. Where they agree, the ranking is robust; where they "
                   "differ, remember permutation importance measures lost AUC while SHAP measures score movement.")
    st.caption(f"Random Forest only: TreeExplainer gives exact values for tree models in seconds, while the RBF SVM "
               f"would need an approximate method taking hours. SHAP {summary['shap_version']}, "
               f"{summary['explainer']}.")


# ---------------------------------------------------------------------------
# Page 6: Full state map
# ---------------------------------------------------------------------------
def page_state_map() -> None:
    import streamlit.components.v1 as components

    st.title("Full state susceptibility map")
    state_ready = STATE_ZONES.exists()
    if state_ready:
        summary = raster_summary(STATE_ZONES)
    else:
        summary = raster_summary(DEMO_ZONES)
        st.warning("**Full state map pending: showing Rudraprayag demo only.** Build the state raster (about 8 "
                   "minutes; close other programs first), then the web map:", icon=":material/pending:")
        st.code("python src/predict_raster_full.py --state --yes\npython src/map_generator_full.py", language="bash")

    if summary:
        cols = st.columns(4)
        cols[0].metric("Area", summary.get("area", "-"))
        cols[1].metric("Cells scored", f"{summary.get('cells_scored', 0):,}", help="30 m cells, water excluded")
        cols[2].metric("Scoring time", f"{summary.get('timing_seconds', {}).get('predict', 0):.0f} s")
        peak = summary.get("memory_bytes", {}).get("peak")
        cols[3].metric("Peak memory", f"{peak / 1e9:.2f} GB" if peak else "-")
        if summary.get("zones"):
            st.dataframe(pd.DataFrame(summary["zones"]), hide_index=True,
                         column_config={"share_percent": st.column_config.NumberColumn("share %", format="%.1f"),
                                        "area_km2": st.column_config.NumberColumn("area km²", format="%.1f")})

    if is_offline():
        offline_notice("state map")
        if state_ready:
            st.image(static_map_png(str(STATE_ZONES), "zones", "state", file_stamp(STATE_ZONES)))
        elif DEMO_ZONES.exists():
            st.image(static_map_png(str(DEMO_ZONES), "zones", "state", file_stamp(DEMO_ZONES)))
        else:
            st.image(static_map_png("", "", "state", 0.0))
        return

    if not STATE_MAP_HTML.exists():
        st.info("The web map has not been built yet. Run `python src/map_generator_full.py`, then reload.")
        return
    if state_ready and file_stamp(STATE_MAP_HTML) < file_stamp(STATE_ZONES):
        st.warning("The web map is older than the state raster. Rerun `python src/map_generator_full.py`.")
    st.caption(f"`outputs/susceptibility_map_uk.html`, {STATE_MAP_HTML.stat().st_size / 1e6:.2f} MB. Click anywhere "
               "for the district and risk zone; use the layer control to switch layers and basemaps.")
    components.html(STATE_MAP_HTML.read_text(encoding="utf-8"), height=700)


# ---------------------------------------------------------------------------
def main() -> None:
    st.set_page_config(page_title=f"{p2.PROJECT_NAME} (Phase 3)", page_icon="⛰️", layout="wide")
    pages = st.navigation([
        st.Page(p2.page_overview, title="Overview", icon=":material/landscape:", url_path="overview", default=True),
        st.Page(p2.page_comparison, title="Model Comparison", icon=":material/compare_arrows:", url_path="comparison"),
        st.Page(page_predict_v2, title="Predict", icon=":material/tune:", url_path="predict"),
        st.Page(page_rudraprayag_v2, title=f"{config.DEMO_DISTRICT} Map", icon=":material/map:", url_path="map"),
        st.Page(page_explainability, title="Explainability", icon=":material/insights:", url_path="explainability"),
        st.Page(page_state_map, title="Full State Map", icon=":material/public:", url_path="state-map"),
    ])

    meta = p2.metadata()
    trained_on = meta.get("data_source")
    if config.IS_SYNTHETIC:
        st.markdown(p2.WATERMARK_HTML, unsafe_allow_html=True)
        if pages.title != "Overview":  # the Overview page carries the full banner instead
            st.warning(f"**{config.SYNTHETIC_LABEL}.** Every number, figure, prediction and map on these pages "
                       "comes from a simulated dataset built to test the pipeline. None of it describes Uttarakhand.",
                       icon=":material/science:")
    elif trained_on and trained_on != config.DATA_SOURCE:
        st.error(f"The saved models were trained on **{trained_on}** data, but the project is set to "
                 f"**{config.DATA_SOURCE}**. Rerun Steps 4 to 7 before trusting anything here.")

    with st.sidebar:
        st.caption("Phase 3 preview (phase3-preparation branch)")
        st.caption(f"Data source: **{config.DATA_SOURCE}** (`{config.DATASET_CSV.name}`)")
        st.caption("Connection: **offline**, maps shown as static copies" if is_offline()
                   else "Connection: **online**, interactive maps")

    pages.run()


main()
