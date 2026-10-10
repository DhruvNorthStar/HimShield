"""
HimShield: six-page dashboard of the preserved landslide susceptibility benchmark.

    streamlit run dashboard_v2/app.py

Pages: Overview, Susceptibility Explorer, Model Comparison, Location Assessment,
Explainability, Methodology & Validation. Legacy /map and /state-map routes open
this same explorer in the district and statewide scopes, respectively.

Reuse, not copies: dashboard/app.py ends with a bare `main()` call, so importing it would launch the whole
Phase 2 app. load_phase2_dashboard() reads that file, leaves out only that final call, and runs the rest
as a module. Its loaders, prediction transformation and widget helpers are reused unchanged;
HimShield owns its presentation labels. dashboard/app.py itself is not changed.

Offline (college wifi): everything is local except the interactive web maps, which load Leaflet from CDNs
and draw basemap tiles from the internet. A quick connection test decides; offline, the explorer shows a
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
from src import viz  # noqa: E402
from src.demo_map import ZONE_COLOURS  # noqa: E402
from src.map_generator_full import POINT_FILL  # noqa: E402
from dashboard_v2 import assessment, benchmark_pages, explainability, explorer, ui  # noqa: E402

# Presentation colours; saved figures and scientific zone/model colours remain unchanged.
INK = ui.TEXT
MUTED = ui.SECONDARY

PHASE2_APP = ROOT / "dashboard" / "app.py"
ONLINE_HOSTS = ("cdn.jsdelivr.net", "tile.openstreetmap.org")


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


@st.cache_data(show_spinner="Drawing a static copy of the map (works offline)...")
def static_map_png(zones_path: str, kind: str, focus: str, stamp: float, model: str) -> bytes:
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
    state.boundary.plot(ax=ax, color=INK, linewidth=1.6, zorder=3)
    if landslides["points"] is not None and len(landslides["points"]):
        pts = landslides["points"].to_crs(config.PROJECT_CRS)
        ax.scatter(pts.geometry.x, pts.geometry.y, s=14, c=POINT_FILL, edgecolors="white", linewidths=0.7, zorder=4)
        handles.append(Line2D([], [], marker="o", linestyle="", markerfacecolor=POINT_FILL, markeredgecolor="white",
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
                    color=INK, zorder=5, path_effects=[pe.withStroke(linewidth=3, foreground="white")])
    ax.set_aspect("equal")
    ax.set_axis_off()
    if handles:
        # Outside the map, to the right: inside, it covered the southern districts.
        ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(1.01, 1.0), fontsize=7.5, frameon=False,
                  borderaxespad=0)
    title = f"Landslide susceptibility, {model}: " + ("Uttarakhand" if focus == "state" else focus)
    ax.set_title(title, loc="left", fontsize=11, fontweight="semibold")
    footer = "Static offline copy: no basemap. "
    if config.IS_SYNTHETIC:
        fig.text(0.5, 0.5, config.SYNTHETIC_LABEL, fontsize=30, color="#e31a1c", alpha=0.10, ha="center",
                 va="center", rotation=24, fontweight="bold")
        footer += f"{config.SYNTHETIC_LABEL}."
    fig.text(0.01, 0.01, footer, fontsize=7, color=MUTED)
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
    """Saved-model scores, unchanged class breaks and retrospective threshold markers."""
    import altair as alt

    edges = [0.0, *config.RISK_ZONE_BREAKS, 1.0]
    bands = pd.DataFrame({"zone": config.RISK_ZONES, "start": edges[:-1], "end": edges[1:],
                          "middle": [(a + b) / 2 for a, b in zip(edges[:-1], edges[1:])]})
    bars = pd.DataFrame({"model": list(scores), "score": list(scores.values()),
                         "threshold": [thresholds.get(m) for m in scores],
                         "zone": [config.risk_zone(s) for s in scores.values()],
                         "decision": [("meets benchmark threshold" if scores[m] >= thresholds[m] else "below benchmark threshold")
                                      if m in thresholds else "threshold unavailable" for m in scores]})
    x = alt.X("score:Q", scale=alt.Scale(domain=[0, 1]), title="Relative susceptibility score (%) — model output",
              axis=alt.Axis(values=edges, format=".0%", grid=False))
    y = alt.Y("model:N", sort=list(scores), title=None, axis=alt.Axis(labelFontSize=13, labelPadding=8))
    band_layer = alt.Chart(bands).mark_rect(opacity=0.45).encode(
        x=alt.X("start:Q", scale=alt.Scale(domain=[0, 1])), x2="end:Q",
        color=alt.Color("zone:N", scale=alt.Scale(domain=config.RISK_ZONES, range=ZONE_COLOURS), legend=None),
        tooltip=[alt.Tooltip("zone:N", title="Susceptibility class"), alt.Tooltip("start:Q", title="from", format=".0%"),
                 alt.Tooltip("end:Q", title="to", format=".0%")])
    band_labels = alt.Chart(bands).mark_text(fontSize=11, color=MUTED, baseline="bottom").encode(
        x=alt.X("middle:Q", scale=alt.Scale(domain=[0, 1])), y=alt.value(-6), text="zone:N")
    tooltip = [alt.Tooltip("model:N", title="Model"), alt.Tooltip("score:Q", title="Relative score (%)", format=".2%"),
               alt.Tooltip("zone:N", title="Class"), alt.Tooltip("threshold:Q", title="Retrospective Youden threshold (%)", format=".2%"),
               alt.Tooltip("decision:N", title="Decision")]
    bar_layer = alt.Chart(bars).mark_bar(size=26, cornerRadiusEnd=4).encode(
        x=x, y=y, tooltip=tooltip,
        color=alt.Color("model:N", scale=alt.Scale(domain=list(viz.MODEL_COLORS), range=list(viz.MODEL_COLORS.values())),
                        legend=None))
    value_layer = alt.Chart(bars).mark_text(align="left", dx=6, fontSize=13, fontWeight="bold", color=INK).encode(
        x="score:Q", y=y, text=alt.Text("score:Q", format=".2%"))
    threshold_layer = alt.Chart(bars).transform_filter(alt.datum.threshold != None).mark_tick(color="#ffffff", thickness=3, size=40).encode(
        x="threshold:Q", y=y, tooltip=[alt.Tooltip("model:N", title="Model"),
                                        alt.Tooltip("threshold:Q", title="Retrospective Youden threshold (%)", format=".2%")])
    # resolve_scale(color="independent"): layers share one colour scale by default, so the bars' model colours
    # and the bands' zone colours would fight over it and the bars would vanish.
    return (band_layer + band_labels + bar_layer + threshold_layer + value_layer).resolve_scale(
        color="independent").properties(
        height=50 * len(scores) + 50, padding={"top": 22, "left": 5, "right": 65, "bottom": 5}).configure_view(
        strokeWidth=0)


def page_predict_v2() -> None:
    assessment.page(p2, probability_chart, file_stamp)


def page_explainability() -> None:
    explainability.page(p2)


# ---------------------------------------------------------------------------
def main() -> None:
    st.set_page_config(page_title="HimShield | Landslide Susceptibility", page_icon=":material/shield:", layout="wide")
    ui.install()

    def show_explorer(default_scope="Uttarakhand", route="explorer"):
        explorer.page(p2, static_map_png, raster_summary, file_stamp, is_offline(),
                      default_scope=default_scope, route=route)

    explorer_page = st.Page(show_explorer, title="Susceptibility Explorer", icon=":material/map:", url_path="explorer")
    methodology_page = st.Page(lambda: benchmark_pages.methodology(p2), title="Methodology & Validation",
                               icon=":material/science:", url_path="methodology")
    visible_pages = [
        st.Page(lambda: benchmark_pages.overview(p2, explorer_page, methodology_page), title="Overview",
                icon=":material/landscape:", url_path="overview", default=True),
        explorer_page,
        st.Page(lambda: benchmark_pages.comparison(p2), title="Model Comparison", icon=":material/compare_arrows:", url_path="comparison"),
        st.Page(page_predict_v2, title="Location Assessment", icon=":material/tune:", url_path="predict"),
        st.Page(page_explainability, title="Explainability", icon=":material/insights:", url_path="explainability"),
        methodology_page,
    ]
    # Native page links expose exactly six choices. Register legacy addresses as
    # aliases without duplicating content or hiding menu entries through CSS.
    aliases = [
        st.Page(lambda: show_explorer(config.DEMO_DISTRICT, "map"), title="District map alias", url_path="map"),
        st.Page(lambda: show_explorer("Uttarakhand", "state-map"), title="State map alias", url_path="state-map"),
    ]
    pages = st.navigation(visible_pages + aliases, position="hidden")

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
                 f"**{config.DATA_SOURCE}**. Resolve the data-source mismatch before interpreting results.")

    with st.sidebar:
        ui.sidebar_brand()
        for page in visible_pages:
            st.page_link(page, use_container_width=True)
        st.divider()
        st.caption(f"Data source: **{config.DATA_SOURCE}** (`{config.DATASET_CSV.name}`)")
        st.caption("Connection: **offline**, maps shown as static copies" if is_offline()
                   else "Connection: **online**, interactive or static map views")
        with st.expander("Saved model availability"):
            ui.model_availability({"SVM": config.SVM_MODEL_PATH, "Random Forest": config.RF_MODEL_PATH,
                                   "XGBoost": config.XGB_MODEL_PATH})

    pages.run()


main()
