"""Local-only ABDB pixel-centre masks over the frozen RF classes. No GIS exports."""
import hashlib
import io
import math
import os
from pathlib import Path
import threading
import time
from urllib.parse import urlparse

import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from dashboard_v2 import image_map, ui
from src import config
from src.demo_map import ZONE_COLOURS

ATTRIBUTION = "Source: Survey of India, Government of India."
DERIVED = "District view from statewide RF"
DEDICATED = "Dedicated Rudraprayag maps"
DISTRICTS = {
    "Almora": ("064", "ALMORA"), "Bageshwar": ("063", "B>GESHWAR"),
    "Chamoli": ("057", "CHAMOLI"), "Champawat": ("065", "CHAMP>WAT"),
    "Dehradun": ("060", "DEHRAD@N"), "Haridwar": ("068", "HARIDW>R"),
    "Nainital": ("066", "NAINIT>L"), "Pauri Garhwal": ("061", "PAURI GARHW>L"),
    "Pithoragarh": ("062", "PITHOR>GARH"), "Rudraprayag": ("058", "RUDRAPRAY>G"),
    "Tehri Garhwal": ("059", "TEHRI GARHW>L"),
    "Udham Singh Nagar": ("067", "UDHAM SINGH NAGAR"), "Uttarkashi": ("056", "UTTARK>SHI"),
}
# Byte identities of the already validated 2025 release, not embedded vector data.
SOURCE_HASHES = {
    "State Boundary/State Boundary.cpg": "3ad3031f5503a4404af825262ee8232cc04d4ea6683d42c5dd0a2f2a27ac9824",
    "State Boundary/State Boundary.dbf": "e6afe169ff7055d02471a6ddae6536bed4c1dfb02c50765c0166ca2eb9a17ea0",
    "State Boundary/State Boundary.prj": "4e0115a1711327038fc52f74a11a80ee1c399c8d84e8f0e5f54bf00b9fd20f16",
    "State Boundary/State Boundary.shp": "602505cbaa149c3aef1701e8bc69cfbda7d8a73c2c2c4d891892bb67ba95b779",
    "State Boundary/State Boundary.shx": "c1edfa5638ec217291460d871db6ef0772b249c075ef6d4b06ae35f6bac127fc",
    "District_Subdistrict_PAN INDIA/District Boundary.cpg": "3ad3031f5503a4404af825262ee8232cc04d4ea6683d42c5dd0a2f2a27ac9824",
    "District_Subdistrict_PAN INDIA/District Boundary.dbf": "0bcc1d46dcbc403f29c47c8c47db2fe4b71e802cd3c8038fc4663765fc2c4236",
    "District_Subdistrict_PAN INDIA/District Boundary.prj": "4e0115a1711327038fc52f74a11a80ee1c399c8d84e8f0e5f54bf00b9fd20f16",
    "District_Subdistrict_PAN INDIA/District Boundary.shp": "05efac0a02c113f25cd55df3f01a4aee7201bfc9b299f73bb3e273b9aa7e3740",
    "District_Subdistrict_PAN INDIA/District Boundary.shx": "691482470b29fe9d5c6d5a7753e90823a1fbe162c603c6260fbd28b5e0a23aea",
}
RASTER_SHA256 = "69f9d3b5619af2256cb1248657aeb1d11cdf282a9f51fba67d95f44f3b57f86d"
STRIPE_ROWS = 128
PREVIEW_PIXELS = 1000
GDAL_CACHE_BYTES = 16 * 1024 * 1024
WORK_LOCK = threading.RLock()
LOOPBACK = {"localhost", "127.0.0.1", "::1"}


class DistrictUnavailable(ValueError):
    """Missing, different or invalid local reference inputs; never repair them."""


def local_session() -> bool:
    # URL/IP alone are not access control. Require a loopback-bound server too.
    return (st.get_option("server.address") in LOOPBACK
            and urlparse(st.context.url or "").hostname in LOOPBACK)


def reference_root() -> Path:
    supplied = os.environ.get("HIMSHIELD_ABDB_DIR")
    return Path(supplied).expanduser().resolve() if supplied else (
        config.ROOT / ".git/abdb-validation-2025/extracted/State_District_Subdistrict_PAN INDIA")


def raster_path() -> Path:
    return config.PROCESSED_DIR / "susceptibility_uk_zones.tif"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@st.cache_data(max_entries=2, show_spinner=False)
def checked_sources(root: str, raster: str, stamps: tuple) -> str:
    for relative, expected in SOURCE_HASHES.items():
        if sha256(Path(root) / relative) != expected:
            raise DistrictUnavailable("Local ABDB bytes differ from the validated 2025 release.")
    if sha256(Path(raster)) != RASTER_SHA256:
        raise DistrictUnavailable("The saved statewide RF raster differs from the validated benchmark.")
    return hashlib.sha256(("".join(SOURCE_HASHES.values()) + RASTER_SHA256).encode("ascii")).hexdigest()


@st.cache_resource(max_entries=1, show_spinner=False)
def boundaries(root: str, digest: str):
    """Official geometries stay in server memory, never in cache_data/browser values."""
    import geopandas as gpd
    import shapely

    with WORK_LOCK:
        state = gpd.read_file(Path(root) / "State Boundary/State Boundary.shp",
                              where="STATE = 'UTTARAKHAND'", engine="pyogrio")
        districts = gpd.read_file(Path(root) / "District_Subdistrict_PAN INDIA/District Boundary.shp",
                                  where="STATE_LGD = '05'", engine="pyogrio")
        if (len(state) != 1 or len(districts) != 13 or not state.crs.equals(districts.crs)
                or set(zip(districts.DIST_LGD, districts.DISTRICT)) != set(DISTRICTS.values())
                or set(districts.STATE_UT) != {"UTTARAKHAND"}):
            raise DistrictUnavailable("ABDB district identities or supplied CRS are inconsistent.")
        # Use the actual .prj, rather than relabelling the metadata's rounded EPSG:7755.
        state_geom = shapely.force_2d(state.to_crs(config.PROJECT_CRS).geometry.iloc[0])
        projected = districts.to_crs(config.PROJECT_CRS).set_index("DIST_LGD")
        geoms = {name: shapely.force_2d(projected.loc[code].geometry) for name, (code, _) in DISTRICTS.items()}
        if any(g.is_empty or not g.is_valid for g in [state_geom, *geoms.values()]):
            raise DistrictUnavailable("Invalid official geometry; no automatic repair is permitted.")
        union = shapely.union_all(list(geoms.values()))
        if (state_geom.symmetric_difference(union).area > .01
                or sum(g.area for g in geoms.values()) - union.area > .01):
            raise DistrictUnavailable("Official state/district union or topology no longer matches validation.")
        return state_geom, geoms


def availability() -> tuple[dict | None, str]:
    if not local_session():
        return None, "Official district views require local loopback hosting (--server.address=127.0.0.1)."
    if config.DATA_SOURCE != "real":
        return None, "Official district views require the verified real-data RF benchmark."
    root, raster = reference_root(), raster_path()
    if root.is_relative_to(config.ROOT) and not root.is_relative_to(config.ROOT / ".git"):
        return None, "Private ABDB references must stay outside the package tree or in the existing private Git reference directory."
    paths = [*(root / name for name in SOURCE_HASHES), raster]
    try:
        stamps = tuple((str(path), path.stat().st_size, path.stat().st_mtime_ns, path.stat().st_ctime_ns) for path in paths)
        digest = checked_sources(str(root), str(raster), stamps)
        boundaries(str(root), digest)
    except (OSError, ValueError, KeyError) as error:
        detail = str(error) if isinstance(error, DistrictUnavailable) else "Required local ABDB files are missing or unreadable."
        return None, detail
    return {"root": str(root), "raster": str(raster), "digest": digest}, ""


def validate_grid(src) -> None:
    if (str(src.crs) != config.PROJECT_CRS or src.count != 1 or src.dtypes != ("uint8",)
            or src.nodata != 0 or src.res != (30, 30) or src.transform.b != 0 or src.transform.d != 0
            or src.transform.a != 30 or src.transform.e != -30):
        raise DistrictUnavailable("Saved RF class grid has incompatible CRS, cells or NoData metadata.")


def scan_raster(path: str, state, geoms: dict, stripe_rows=STRIPE_ROWS) -> dict:
    """Independent masks; count conflicts instead of assigning cells by polygon order."""
    import rasterio
    from rasterio.features import geometry_mask
    from rasterio.windows import Window
    from shapely.geometry import box, mapping

    start = time.perf_counter()
    records = {name: {"code": DISTRICTS[name][0] if name in DISTRICTS else name,
                     "zone_cells": [0] * 5, "nodata_cells": 0, "scored_cells": 0} for name in geoms}
    total = {key: 0 for key in ("scored_cells", "assigned_scored", "unassigned_scored", "multiply_assigned_cells",
                               "official_state_nodata", "official_state_scored", "state_without_district_cells")}
    shapes = {name: mapping(geom) for name, geom in geoms.items()}
    state_shape = mapping(state)
    statewide = np.zeros(6, dtype=np.int64)
    max_pixels = 0
    with rasterio.Env(GDAL_CACHEMAX=GDAL_CACHE_BYTES, GDAL_NUM_THREADS="1"), rasterio.open(path) as src:
        validate_grid(src)
        for name, geom in geoms.items():
            records[name]["outside_raster_km2"] = geom.difference(box(*src.bounds)).area / 1e6
        for top in range(0, src.height, stripe_rows):
            window = Window(0, top, src.width, min(stripe_rows, src.height - top))
            cells = src.read(1, window=window)
            max_pixels = max(max_pixels, cells.size)
            if np.any(cells > 5):
                raise DistrictUnavailable("Unexpected RF susceptibility class; processing stopped.")
            statewide += np.bincount(cells.ravel(), minlength=6)
            memberships = np.zeros(cells.shape, dtype=np.uint8)
            transform = src.window_transform(window)
            for name, shape in shapes.items():
                inside = geometry_mask([shape], out_shape=cells.shape, transform=transform, invert=True, all_touched=False)
                memberships += inside
                counts = np.bincount(cells[inside], minlength=6)
                records[name]["nodata_cells"] += int(counts[0])
                records[name]["zone_cells"] = [a + int(b) for a, b in zip(records[name]["zone_cells"], counts[1:])]
            in_state = geometry_mask([state_shape], out_shape=cells.shape, transform=transform, invert=True, all_touched=False)
            scored = cells > 0
            total["scored_cells"] += int(scored.sum())
            total["assigned_scored"] += int(((memberships > 0) & scored).sum())
            total["unassigned_scored"] += int(((memberships == 0) & scored).sum())
            total["multiply_assigned_cells"] += int((memberships > 1).sum())
            total["official_state_nodata"] += int((in_state & ~scored).sum())
            total["official_state_scored"] += int((in_state & scored).sum())
            total["state_without_district_cells"] += int((in_state & (memberships == 0)).sum())
        cell_area = abs(src.transform.a * src.transform.e) / 1e6
    for item in records.values():
        item["scored_cells"] = sum(item["zone_cells"])
        item["in_raster_cells"] = item["scored_cells"] + item["nodata_cells"]
        item["zones"] = [{"zone": name, "cells": count,
                          "share_percent": 100 * count / item["scored_cells"] if item["scored_cells"] else 0,
                          "area_km2": count * cell_area} for name, count in zip(config.RISK_ZONES, item["zone_cells"])]
    if (total["multiply_assigned_cells"] or total["state_without_district_cells"]
            or total["assigned_scored"] != total["official_state_scored"]
            or sum(item["scored_cells"] for item in records.values()) + total["unassigned_scored"] != total["scored_cells"]):
        raise DistrictUnavailable("District raster reconciliation failed; no conflict or gap is silently allocated.")
    return {"districts": records, "coverage": total, "zone_cells_statewide": statewide[1:].tolist(),
            "scan_seconds": time.perf_counter() - start, "max_window_pixels": max_pixels, "workers": 1}


@st.cache_data(max_entries=1, show_spinner="Counting original RF cells for all 13 districts once…")
def coverage(root: str, raster: str, digest: str) -> dict:
    state, geoms = boundaries(root, digest)
    with WORK_LOCK:
        return scan_raster(raster, state, geoms)


def preview_raster(path: str, geom, max_pixels=PREVIEW_PIXELS) -> dict:
    """Sample actual masked source cells in bounded strips, never average class codes."""
    import rasterio
    from rasterio.features import geometry_mask
    from rasterio.windows import Window, from_bounds
    from shapely.geometry import mapping
    from PIL import Image

    start = time.perf_counter()
    with rasterio.Env(GDAL_CACHEMAX=GDAL_CACHE_BYTES, GDAL_NUM_THREADS="1"), rasterio.open(path) as src:
        validate_grid(src)
        raw = from_bounds(*geom.bounds, transform=src.transform)
        left, top = max(0, math.floor(raw.col_off)), max(0, math.floor(raw.row_off))
        right, bottom = min(src.width, math.ceil(raw.col_off + raw.width)), min(src.height, math.ceil(raw.row_off + raw.height))
        if right <= left or bottom <= top:
            raise DistrictUnavailable("District lies outside the saved raster extent.")
        stride = max(1, math.ceil(max(right - left, bottom - top) / max_pixels))
        rows, cols = np.arange(top, bottom, stride), np.arange(left, right, stride)
        grid = np.zeros((len(rows), len(cols)), dtype=np.uint8)
        selected = np.zeros(grid.shape, dtype=bool)
        shape = mapping(geom)
        for row in range(top, bottom, STRIPE_ROWS):
            window = Window(left, row, right - left, min(STRIPE_ROWS, bottom - row))
            values = src.read(1, window=window)
            inside = geometry_mask([shape], out_shape=values.shape, transform=src.window_transform(window),
                                   invert=True, all_touched=False)
            indices = np.flatnonzero((rows >= row) & (rows < row + window.height))
            rr, cc = rows[indices] - row, cols - left
            grid[indices] = values[np.ix_(rr, cc)]
            selected[indices] = inside[np.ix_(rr, cc)]
        if np.any(grid > 5):
            raise DistrictUnavailable("Unexpected class in RF preview.")
    rgba = np.zeros((*grid.shape, 4), dtype=np.uint8)
    rgba[selected & (grid == 0)] = [216, 226, 236, 255]
    for value, colour in enumerate(ZONE_COLOURS, start=1):
        rgba[selected & (grid == value)] = [*(int(colour[i:i + 2], 16) for i in (1, 3, 5)), 255]
    stream = io.BytesIO()
    Image.fromarray(rgba).save(stream, format="PNG")
    # Deliberately no polygon, bounds, geographic transform or coordinate arrays.
    return {"png": stream.getvalue(), "width": grid.shape[1], "height": grid.shape[0],
            "display_cell_spacing_m": 30 * stride, "render_seconds": time.perf_counter() - start}


@st.cache_data(max_entries=4, show_spinner="Preparing a private raster-image preview…")
def preview(root: str, raster: str, digest: str, district: str) -> dict:
    if district not in DISTRICTS:
        raise DistrictUnavailable("Unknown official district.")
    _, geoms = boundaries(root, digest)
    with WORK_LOCK:
        return preview_raster(raster, geoms[district])


def reconciliation_note(report: dict) -> str:
    count = report["coverage"]
    return (f"Official district reconciliation: {count['assigned_scored']:,} assigned + "
            f"{count['unassigned_scored']:,} unassigned = {count['scored_cells']:,} statewide scored cells. "
            f"Double-counted cells: {count['multiply_assigned_cells']:,}. Unassigned scored fringe cells lie outside the official state "
            "and stay in the statewide product.")


def page(scope: str, source: dict, use_static: bool) -> None:
    try:
        report = coverage(**source)
        rendered = preview(**source, district=scope)
    except (OSError, ValueError) as error:
        ui.availability("Official district view unavailable.", str(error), warning=True)
        return
    item = report["districts"][scope]
    ui.caption("Static / offline view: local image only." if use_static else
               "Interactive image: drag to pan, use zoom controls and click a sampled cell for its class. No internet tiles are needed.")
    with ui.panel("explorer-map"):
        st.subheader(f"{scope} · Random Forest · derived from statewide RF")
        ui.caption(f"Official 2025 ABDB district ID {item['code']}. Local academic display only. {ATTRIBUTION}")
        ui.susceptibility_legend(config.RISK_ZONES, config.RISK_ZONE_BREAKS, ZONE_COLOURS)
        if use_static:
            st.image(rendered["png"], caption=f"Random Forest · {scope}. Private static view derived from statewide RF.", width="stretch")
        else:
            components.html(image_map.html(rendered["png"], scope), height=680)
        ui.caption(f"30 m source grid; preview samples saved cells at {rendered['display_cell_spacing_m']} m spacing. "
                   "Zooming cannot add source detail. Gray = unscored NoData; blank = outside the masked view. "
                   "No GPS extraction, basemap or official vector coordinates are sent to the browser.")
        ui.caption(ui.SCORE_NOTE)
    with ui.panel("explorer-summary"):
        st.subheader("District coverage from original 30 m cells")
        cols = st.columns(3)
        ui.metric_card(cols[0], "district-scored", "Cells scored", f"{item['scored_cells']:,}")
        ui.metric_card(cols[1], "district-nodata", "NoData cells inside raster", f"{item['nodata_cells']:,}")
        ui.metric_card(cols[2], "district-coverage", "Scored share of in-raster district cells", ui.percent(
            item['scored_cells'] / item['in_raster_cells'] if item['in_raster_cells'] else 0))
        st.dataframe(pd.DataFrame(item["zones"]), hide_index=True, width="stretch",
                     column_config={"area_km2": st.column_config.NumberColumn("Area (km²)", format="%.3f"),
                                    "share_percent": st.column_config.NumberColumn("Share of scored cells (%)", format="%.2f")})
        ui.caption(f"District polygon outside the raster rectangle: {item['outside_raster_km2']:.6f} km² "
                   "(separate from in-raster NoData). All districts have incomplete coverage. "
                   "NoData is not automatically water or low susceptibility; missing cells are not filled.")
        ui.caption(reconciliation_note(report))
        ui.caption(f"Official-state NoData inside the saved rectangle: {report['coverage']['official_state_nodata']:,} cells. "
                   "The old raster footprint and official outline differ. These are masks of preserved RF classes, not newly trained district models.")
