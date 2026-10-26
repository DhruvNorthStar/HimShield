"""Read-only presentation of existing maps. No prediction or GIS generation entry points."""
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from dashboard_v2 import district_views, statewide_maps, ui
from src import config
from src.demo_map import ZONE_COLOURS

INTERACTIVE = "Interactive map"
STATIC = "Static / offline map"

LEGACY_DISPLAY_STYLE = """
<style id="himshield-legacy-map-layout">
@media (max-width: 480px) {
  .leaflet-top.leaflet-right { top: 76px; }
  html .lsm-legend { max-width: calc(100vw - 24px); box-sizing: border-box; }
  html .lsm-legend .lsm-name { min-width: 0; }
}
</style>
"""


def legacy_display_html(content: str) -> str:
    """Add narrow-frame layout only; retain saved markup/scripts and disk bytes."""
    if LEGACY_DISPLAY_STYLE in content:
        return content
    if "</head>" in content:
        return content.replace("</head>", LEGACY_DISPLAY_STYLE + "</head>", 1)
    return LEGACY_DISPLAY_STYLE + content


def map_catalog(scope: str) -> dict:
    """Explicit saved-map registry: point-model availability does not imply map coverage."""
    if scope == "Uttarakhand":
        catalog = {"Random Forest": {
            "html": config.OUTPUTS_DIR / "susceptibility_map_uk.html",
            "raster": config.PROCESSED_DIR / "susceptibility_uk_zones.tif",
            "kind": "zones", "focus": "state", "metadata": None,
        }}
        catalog.update(statewide_maps.verified_products())
        return catalog
    if scope != config.DEMO_DISTRICT:
        return {}  # Other districts must never inherit Rudraprayag's dedicated files.
    slug = config.DEMO_DISTRICT.lower().replace(" ", "_")
    catalog = {name: {
        "html": config.DEMO_MAP_HTML.with_name(config.DEMO_MAP_HTML.stem + suffix + ".html"),
        "raster": config.PROCESSED_DIR / f"susceptibility_{slug}_{model}.tif",
        "kind": "probability", "focus": config.DEMO_DISTRICT, "metadata": "demo_map" + suffix,
    } for name, model, suffix in (("Random Forest", "rf", ""), ("SVM (RBF)", "svm", "_svm"))}
    # Retain the existing RF zones fallback; never substitute an RF raster for SVM.
    rf_zones = config.PROCESSED_DIR / f"susceptibility_{slug}_zones.tif"
    if not catalog["Random Forest"]["raster"].is_file() and rf_zones.is_file():
        catalog["Random Forest"].update(raster=rf_zones, kind="zones")
    return catalog


def available_maps(catalog: dict) -> dict:
    return {name: item for name, item in catalog.items()
            if (item.get("html") is not None and item["html"].is_file()) or item["raster"].is_file()}


def statewide_coverage() -> tuple[list[str], str]:
    """The card and Explorer describe the same genuinely available saved products."""
    names = list(available_maps(map_catalog("Uttarakhand")))
    badge = (" + ".join(names) + (" only" if len(names) == 1 else "")) if names else "unavailable"
    return names, "Statewide · " + badge


def statewide_unavailable(catalog: dict) -> str:
    missing = [name for name in statewide_maps.MODEL_NAMES.values() if name not in catalog]
    if not missing:
        return ""
    return ("Statewide maps for " + ", ".join(missing)
            + " are absent or have not passed local completion and integrity checks. "
              "The dashboard does not run inference.")


@st.cache_data(show_spinner=False)
def saved_html(path: str, stamp: float) -> str:
    return Path(path).read_text(encoding="utf-8")


def page(p2, static_map_png, raster_summary, file_stamp, offline: bool, *,
         default_scope="Uttarakhand", route="explorer") -> None:
    ui.page_header("Susceptibility Explorer", "Explore saved susceptibility coverage by geographic scope and model.")
    official, reason = district_views.availability()
    scopes = ["Uttarakhand", *district_views.DISTRICTS] if official else ["Uttarakhand", config.DEMO_DISTRICT]
    # Legacy routes open the correct scope once, then allow normal selector changes.
    if st.session_state.get("explorer-route") != route or "explorer-scope" not in st.session_state:
        st.session_state["explorer-scope"] = default_scope
        st.session_state["explorer-route"] = route
    if st.session_state["explorer-scope"] not in scopes:
        st.session_state["explorer-scope"] = "Uttarakhand"
        ui.availability("Previous district selection unavailable.", "Restored statewide coverage; no substitute boundary is used.")
    with ui.panel("explorer-controls"):
        scope = st.selectbox("Geographic scope", scopes, key="explorer-scope")
        derived = bool(official and scope != "Uttarakhand" and scope != config.DEMO_DISTRICT)
        if official and scope == config.DEMO_DISTRICT:
            product = st.selectbox("Map product", [district_views.DEDICATED, district_views.DERIVED], key="explorer-product")
            derived = product == district_views.DERIVED
        middle, right = st.columns([1, 1.3], gap="medium")
        catalog = {} if derived else available_maps(map_catalog(scope))
        if not derived and not catalog:
            ui.availability("Map coverage unavailable.",
                            "No saved map or raster exists for this scope. Select another scope; nothing is generated.")
            return
        if derived:
            model = "Random Forest"
            middle.markdown("**Map model**")
            middle.markdown("Random Forest — district view derived from statewide RF")
        elif len(catalog) == 1:
            model = next(iter(catalog))
            middle.markdown("**Map model**")
            coverage = "statewide" if scope == "Uttarakhand" else "district"
            middle.markdown(f"{model} — only available {coverage} model")
        else:
            key, retained = "explorer-model-" + scope, "explorer-retained-model-" + scope
            # Native widget cleanup removes a hidden model selector in the derived
            # product. Preserve its last real choice in a separate non-widget key.
            if key not in st.session_state or st.session_state[key] not in catalog:
                candidate = st.session_state.get(retained)
                st.session_state[key] = candidate if candidate in catalog else next(iter(catalog))
            model = middle.selectbox("Map model", list(catalog), key=key)
            st.session_state[retained] = model
        if offline:
            st.session_state["explorer-mode"] = STATIC
        mode = right.radio("Map view", [INTERACTIVE, STATIC], key="explorer-mode",
                           disabled=offline, horizontal=True)
        if scope == "Uttarakhand":
            ui.caption("Available saved statewide maps: " + ", ".join(catalog) + ".")
            unavailable = statewide_unavailable(catalog)
            if unavailable:
                ui.caption(unavailable)
        elif derived:
            ui.caption("Derived from the saved statewide RF classes using official 2025 district pixel-centre masks. "
                       "No dedicated SVM or XGBoost map is available for this product.")
        else:
            ui.caption("Available saved district maps: " + ", ".join(catalog) + ". No saved XGBoost district map is available.")

    if not official:
        ui.caption("Optional official district views unavailable: " + reason + " Existing statewide and dedicated Rudraprayag products remain available.")
    if derived:
        district_views.page(scope, official, use_static=offline or mode == STATIC)
        return

    item = catalog[model]
    summary = item.get("summary") or (p2.metadata().get(item["metadata"], {}) if item["metadata"]
                                     else raster_summary(item["raster"]))
    raster_interactive = item.get("renderer") == "raster"
    has_html = item.get("html") is not None and item["html"].is_file()
    use_static = offline or mode == STATIC or (not has_html and not raster_interactive)
    if offline:
        st.info("**Offline:** the static view uses local rasters, boundaries and landslide points. "
                "It needs no basemap connection and cannot be clicked.")
    elif mode == STATIC:
        ui.caption("Static view: local coverage without internet tiles or clickable features. Choose Interactive map to explore layers.")
    elif use_static:
        ui.availability("Interactive map unavailable.", "Showing the saved raster as a static view instead.", warning=True)
    with ui.panel("explorer-map"):
        st.subheader(f"{scope} · {model}")
        ui.susceptibility_legend(config.RISK_ZONES, config.RISK_ZONE_BREAKS, ZONE_COLOURS)
        if use_static:
            if item["raster"].is_file():
                st.image(static_map_png(str(item["raster"]), item["kind"], item["focus"],
                                        file_stamp(item["raster"]), model),
                         caption=f"{model} · {scope}. Static display of the saved raster; resolution reduced for display.",
                         use_container_width=True)
            else:
                ui.availability("Static raster unavailable.",
                                "This view needs the saved raster. The existing interactive map remains available when online.")
        else:
            if raster_interactive:
                ui.caption("Pan and zoom, and use the layer control to explore saved susceptibility coverage. "
                           "Internet access is required for map libraries and basemap tiles.")
                components.html(statewide_maps.interactive_html(str(item["raster"]), model,
                                (item["signature"], file_stamp(item["raster"]))), height=700)
            else:
                ui.caption("Use the map's layer control and click to inspect the saved geographic information and class. "
                           "Internet access is required for map libraries and basemap tiles.")
                components.html(legacy_display_html(saved_html(str(item["html"]), file_stamp(item["html"]))), height=700)
        if scope == "Uttarakhand":
            ui.caption("Source grid: 30 m. The statewide web overlay uses approximately 90 m display cells. "
                       + ("The display is reduced from the saved source classes." if raster_interactive else
                          "A click reports the display class, not an exact 30 m site assessment."))
        else:
            ui.caption("Source grid: 30 m. The saved district overlay visualizes model outputs; "
                       "display reduction and resampling do not provide a site survey.")
        ui.caption(ui.SCORE_NOTE + " Water and unavailable source cells are excluded; blank coverage is not a low class. "
                   + ("" if raster_interactive else "The preserved interactive map retains its original legend wording."))

    with ui.panel("explorer-summary"):
        st.subheader("Saved coverage summary")
        if not summary:
            ui.availability("Summary unavailable.", "No saved run summary accompanies this view. Coverage statistics are not invented.")
            return
        cols = st.columns(3)
        ui.metric_card(cols[0], "coverage-cells", "Cells scored", f"{summary.get('cells_scored', 0):,}",
                       help="Saved count on the 30 m source grid; not the number of web display cells")
        ui.metric_card(cols[1], "coverage-water", "Water cells excluded", f"{summary.get('cells_water_skipped', 0):,}")
        seconds = summary.get("timing_seconds", {}).get("predict")
        ui.metric_card(cols[2], "coverage-time", "Saved scoring time", f"{seconds:.0f} s" if seconds is not None else "—",
                       help="Historical computation time, not time to load this page or a future runtime estimate")
        if summary.get("zones"):
            st.dataframe(pd.DataFrame(summary["zones"]), hide_index=True, use_container_width=True,
                         column_config={"zone": "Susceptibility class", "cells": st.column_config.NumberColumn("Source cells", format="%d"),
                                        "share_percent": st.column_config.NumberColumn("Share (%)", format="%.1f"),
                                        "area_km2": st.column_config.NumberColumn("Area (km²)", format="%.1f")})
            ui.caption("Saved full-resolution counts and areas. Shares refer to scored cells; displayed shares are rounded.")
        if official and scope == "Uttarakhand":
            ui.caption("The saved statewide footprint differs from the official 2025 district outline. "
                       "Scored fringe cells remain unassigned to districts; NoData is not low susceptibility. "
                       + district_views.ATTRIBUTION)
            # The statewide product already has its saved full-resolution summary.
            # Avoid a scan of all district masks until their reconciliation is requested.
            if model == "Random Forest" and st.checkbox("Show official district coverage reconciliation", key="explorer-reconcile",
                           help="The first request counts original raster cells across all 13 districts. "
                                "The result is cached and also used by derived district views."):
                try:
                    report = district_views.coverage(**official)
                    ui.caption(district_views.reconciliation_note(report))
                    ui.caption(f"Official-state NoData inside the raster rectangle: {report['coverage']['official_state_nodata']:,} cells.")
                except (OSError, ValueError) as error:
                    ui.availability("Official coverage check unavailable.", str(error), warning=True)
