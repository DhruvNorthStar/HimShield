"""
Step 9: landslide susceptibility map for the demo district (Rudraprayag).

    python -m src.demo_map                 Random Forest (the default)
    python -m src.demo_map --model svm     SVM, for comparison; several times slower

What it does, in order:
    1. Cut the district out of the ten aligned Step 2 rasters (30 m, EPSG:32644).
    2. Turn every cell inside the district into one row with the dataset.csv schema. Water cells are
       skipped: Step 2e never samples stable points on water and Step 4 drops water rows, so the
       models have learned nothing about it.
    3. Score the rows in chunks through prepare_for_prediction, the exact transform used in
       training, and the saved model.
    4. Put each score into one of five risk zones with the fixed breaks in src/config.py.
    5. Write the scores as a GeoTIFF and the zones as a folium web map, time every stage, and project
       the time for the whole state (full-state mapping itself is Phase 3).

Outputs:
    outputs/demo_map_rudraprayag.html                   web map (…_svm.html for --model svm)
    data/processed/susceptibility_rudraprayag_rf.tif    scores, float32, NoData -9999 (…_svm.tif)
    models/metadata.json                                demo_map section (demo_map_svm for SVM)

While the models are trained on synthetic data, this run tests plumbing and timing only. The map
shows nothing about Uttarakhand: the synthetic dataset uses its own class names and value ranges,
so its categories are bridged to the real raster classes below and some real values fall outside
anything the models saw. Both are measured and reported rather than hidden.
"""
import argparse
import sys
import time

import joblib
import numpy as np
import pandas as pd

from src import artifacts, config
from src.label_categories import WORLDCOVER_CLASSES, load_soil_legend
from src.preprocess import EXCLUDED_LULC, prepare_for_prediction

# Feature column -> raster name in data/processed/. Lithology has no raster yet (it needs Bhukosh).
RASTERS = {
    "elevation": "dem", "slope": "slope", "aspect": "aspect", "curvature": "curvature", "twi": "twi",
    "rainfall": "rainfall", "ndvi": "ndvi", "dist_roads": "dist_roads", "dist_streams": "dist_streams",
    "dist_faults": "dist_faults", "lulc": "lulc", "soil_type": "soil",
}
WATER_CODE = 80        # WorldCover "Permanent water bodies"
NODATA_SCORE = -9999.0
CHUNK_ROWS = 250_000   # about 60 MB of model input per chunk, comfortable on an 8 GB laptop

MODELS = {
    "rf": ("Random Forest", config.RF_MODEL_PATH),
    "svm": ("SVM (RBF)", config.SVM_MODEL_PATH),
}

# One hue, light to dark, for five ordered zones: an ordinal scale, so no rainbow and no
# green-to-red (which also fails for red-green colour-blind readers). Vermillion matches the
# landslide colour in every report figure. Checked with a palette validator for an ordinal ramp on
# a light basemap: every step clears 2:1 contrast and neighbouring steps stay distinguishable.
ZONE_COLOURS = ["#ec9a60", "#e27a3a", "#d55e00", "#a94700", "#6e2c00"]

# SYNTHETIC MODELS ONLY. The simulated dataset invented its own class names, while the rasters carry
# WorldCover and SoilGrids names. Without a bridge every real class would be unknown to the model and
# silently scored as the reference class. With real models, dataset.csv comes from the same rasters
# via src/label_categories.py, the names already match, and this bridge is not applied.
SYNTHETIC_CLASS_BRIDGE = {
    "lulc": {"Tree cover": "Forest", "Shrubland": "Scrub", "Grassland": "Grassland",
             "Cropland": "Agriculture", "Built-up": "Builtup", "Bare/sparse vegetation": "Barren",
             "Snow and ice": "Snow", "Herbaceous wetland": "Grassland", "Mangroves": "Forest",
             "Moss and lichen": "Grassland"},
    "soil_type": {"No soil (rock or ice)": "Glacier", "Cryosols": "Glacier"},
}


# ---------------------------------------------------------------------------
# 1. Read the district from the aligned rasters
# ---------------------------------------------------------------------------
def district_geometry():
    import geopandas as gpd

    districts = gpd.read_file(config.DISTRICT_BOUNDARIES).to_crs(config.PROJECT_CRS)
    match = districts[districts["district"] == config.DEMO_DISTRICT]
    if match.empty:
        raise SystemExit(f"No district named {config.DEMO_DISTRICT!r} in {config.DISTRICT_BOUNDARIES.name}. "
                         f"Names present: {sorted(districts['district'])}")
    return match.geometry.union_all(), float(match.area.sum())


def read_district(geometry) -> dict:
    """Read a window around the district from every raster and mark the cells that can be scored."""
    import rasterio
    from rasterio.features import geometry_mask
    from rasterio.windows import Window, from_bounds

    reference = config.PROCESSED_DIR / "dem.tif"
    if not reference.exists():
        raise SystemExit(f"{reference} not found. Finish Step 2a first.")
    with rasterio.open(reference) as ref:
        window = from_bounds(*geometry.bounds, transform=ref.transform).round_offsets().round_lengths()
        window = window.intersection(Window(0, 0, ref.width, ref.height))
        transform, crs, ref_transform = ref.window_transform(window), ref.crs, ref.transform
    shape = (int(window.height), int(window.width))
    inside = geometry_mask([geometry], out_shape=shape, transform=transform, invert=True)

    layers, readable = {}, inside.copy()
    for feature, name in RASTERS.items():
        if feature in config.DROPPED_COLUMNS:
            continue
        path = config.PROCESSED_DIR / f"{name}.tif"
        if not path.exists():
            raise SystemExit(f"{path.name} not found. Build it in Step 2, then run `python -m src.check_layers`.")
        with rasterio.open(path) as src:
            if src.crs != crs or not src.transform.almost_equals(ref_transform):
                raise SystemExit(f"{path.name} is not on the dem.tif grid. Run `python -m src.check_layers`.")
            data = src.read(1, window=window)
            if src.nodata is not None:
                readable &= data != src.nodata
            if np.issubdtype(data.dtype, np.floating):
                readable &= np.isfinite(data)
            layers[feature] = data

    water = readable & (layers["lulc"] == WATER_CODE) if "lulc" in layers else np.zeros(shape, bool)
    return {"layers": layers, "inside": inside, "scorable": readable & ~water, "water": water,
            "transform": transform, "crs": crs, "shape": shape}


# ---------------------------------------------------------------------------
# 2. Turn cells into rows the models understand
# ---------------------------------------------------------------------------
def category_lookups() -> dict[str, np.ndarray]:
    """Raster code -> class name, as arrays indexed by code, with the synthetic bridge if needed."""
    names = {"lulc": dict(WORLDCOVER_CLASSES), "soil_type": load_soil_legend()}
    if not names["soil_type"]:
        raise SystemExit("Soil legend not found in data/raw/soil/. Rerun `python -m src.get_open_data soil`.")
    lookups = {}
    for feature, mapping in names.items():
        if config.IS_SYNTHETIC:
            mapping = {code: SYNTHETIC_CLASS_BRIDGE[feature].get(name, name) for code, name in mapping.items()}
        table = np.full(256, None, dtype=object)
        for code, name in mapping.items():
            table[code] = name
        lookups[feature] = table
    return lookups


def training_profile(dataset: pd.DataFrame, feature_names: list[str]) -> dict:
    """What the models saw: numeric ranges, the classes they know, and a stand-in for missing layers."""
    from src.preprocess import reference_levels

    # Step 4 leaves out the most frequent class of each feature (after dropping water rows); that
    # class is scored as all zeros, so it counts as known even though it has no column.
    trained_rows = dataset[~dataset["lulc"].isin(EXCLUDED_LULC)] if "lulc" in dataset.columns else dataset
    references = reference_levels(trained_rows)
    known = {}
    for col in config.active_categorical_features():
        levels = set(dataset[col].dropna().astype(str))
        known[col] = {lvl for lvl in levels if f"{col}_{lvl}" in feature_names} | {references[col]}
    ranges = {col: (float(dataset[col].min()), float(dataset[col].max()))
              for col in config.active_numeric_features()}
    return {"known_classes": known, "ranges": ranges}


def rows_for(cells: np.ndarray, layers: dict, lookups: dict, fills: dict) -> pd.DataFrame:
    frame = {}
    for feature, data in layers.items():
        values = data.ravel()[cells]
        frame[feature] = lookups[feature][values.astype(np.int64)] if feature in lookups \
            else values.astype(np.float64)
    for feature, value in fills.items():
        frame[feature] = np.full(len(cells), value, dtype=object)
    return pd.DataFrame(frame)


def check_inputs(grid: dict, lookups: dict, profile: dict) -> dict:
    """Measure, before scoring, how much of the district the models were never trained on."""
    cells = grid["scorable"]
    report = {"outside_training_range_percent": {}, "classes_unknown_to_model": {}}
    for feature, (low, high) in profile["ranges"].items():
        if feature not in grid["layers"]:
            continue
        values = grid["layers"][feature][cells]
        share = 100 * float(np.mean((values < low) | (values > high)))
        if share > 0:
            report["outside_training_range_percent"][feature] = round(share, 2)
    for feature in lookups:
        if feature not in grid["layers"] or feature not in profile["known_classes"]:
            continue
        codes, counts = np.unique(grid["layers"][feature][cells], return_counts=True)
        for code, count in zip(codes, counts):
            name = lookups[feature][int(code)]
            if name not in profile["known_classes"][feature]:
                report["classes_unknown_to_model"].setdefault(feature, {})[str(name)] = int(count)
    return report


# ---------------------------------------------------------------------------
# 5. Outputs
# ---------------------------------------------------------------------------
def write_scores(scores: np.ndarray, grid: dict, path) -> None:
    import rasterio

    profile = {"driver": "GTiff", "height": grid["shape"][0], "width": grid["shape"][1], "count": 1,
               "dtype": "float32", "crs": grid["crs"], "transform": grid["transform"],
               "nodata": NODATA_SCORE, "compress": "deflate", "predictor": 3, "tiled": True}
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(scores.astype(np.float32), 1)


def render_map(zones: np.ndarray, grid: dict, geometry, zone_rows: list[dict], label: str, path) -> None:
    """Zones as an image over a web basemap, with the district outline and a legend."""
    import folium
    import geopandas as gpd
    from rasterio.transform import array_bounds
    from rasterio.warp import Resampling, calculate_default_transform, reproject, transform_bounds

    # Leaflet stretches an image overlay linearly in Web Mercator, so warp the zones there first.
    # Nearest neighbour, because zones are classes and must never be averaged.
    height, width = zones.shape
    left, bottom, right, top = array_bounds(height, width, grid["transform"])
    dst_transform, dst_width, dst_height = calculate_default_transform(
        grid["crs"], "EPSG:3857", width, height, left, bottom, right, top)
    mercator = np.zeros((dst_height, dst_width), dtype=np.uint8)
    reproject(zones, mercator, src_transform=grid["transform"], src_crs=grid["crs"],
              dst_transform=dst_transform, dst_crs="EPSG:3857", resampling=Resampling.nearest,
              src_nodata=0, dst_nodata=0)
    rgba = np.zeros((dst_height, dst_width, 4), dtype=np.uint8)
    for zone, colour in enumerate(ZONE_COLOURS, start=1):
        rgba[mercator == zone] = [int(colour[i:i + 2], 16) for i in (1, 3, 5)] + [255]
    west, south, east, north = transform_bounds(
        "EPSG:3857", config.GEOGRAPHIC_CRS, *array_bounds(dst_height, dst_width, dst_transform))

    fmap = folium.Map(location=[(south + north) / 2, (west + east) / 2], zoom_start=10,
                      tiles=None, control_scale=True)
    folium.TileLayer("CartoDB positron", name="Light basemap").add_to(fmap)
    folium.TileLayer("OpenStreetMap", name="OpenStreetMap").add_to(fmap)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Tiles &copy; Esri, Maxar, Earthstar Geographics", name="Satellite imagery").add_to(fmap)
    folium.raster_layers.ImageOverlay(image=rgba, bounds=[[south, west], [north, east]], opacity=0.75,
                                      name=f"Susceptibility ({label})").add_to(fmap)
    outline = gpd.GeoSeries([geometry], crs=config.PROJECT_CRS).to_crs(config.GEOGRAPHIC_CRS)
    folium.GeoJson(outline.__geo_interface__, name=f"{config.DEMO_DISTRICT} boundary",
                   style_function=lambda _: {"color": "#1a1a1a", "weight": 2, "fillOpacity": 0}).add_to(fmap)
    folium.LayerControl(collapsed=False).add_to(fmap)
    fmap.fit_bounds([[south, west], [north, east]])

    rows = "".join(
        f'<div style="display:flex;align-items:center;gap:8px;margin:3px 0">'
        f'<span style="width:18px;height:14px;background:{colour};border:2px solid #fff;'
        f'outline:1px solid rgba(0,0,0,.15);flex:none"></span>'
        f'<span style="flex:1">{row["zone"]}</span>'
        f'<span style="color:#52514e;font-variant-numeric:tabular-nums">{row["score_range"]} &middot; '
        f'{row["share_percent"]:.1f}%</span></div>'
        for colour, row in zip(ZONE_COLOURS, zone_rows))
    warning = (f'<div style="margin-top:6px;font-weight:600;color:#0b0b0b">{config.SYNTHETIC_LABEL}</div>'
               f'<div style="color:#52514e">Pipeline test only. Shows nothing about {config.DEMO_DISTRICT}.</div>'
               if config.IS_SYNTHETIC else "")
    legend = (
        '<div style="position:fixed;bottom:24px;left:12px;z-index:9999;background:#fcfcfb;'
        'padding:10px 12px;border:1px solid rgba(11,11,11,.12);border-radius:6px;min-width:250px;'
        'font:12px system-ui,-apple-system,Segoe UI,sans-serif;color:#0b0b0b;'
        'box-shadow:0 1px 4px rgba(0,0,0,.12)">'
        f'<div style="font-weight:600;margin-bottom:4px">{config.DEMO_DISTRICT}: landslide susceptibility</div>'
        f'<div style="color:#52514e;margin-bottom:6px">{label} score, share of scored area</div>'
        f'{rows}<div style="color:#52514e;margin-top:6px">Uncoloured: water or outside the district</div>'
        f'{warning}</div>')
    fmap.get_root().html.add_child(folium.Element(legend))
    fmap.save(str(path))


# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description="Step 9: susceptibility map for the demo district")
    parser.add_argument("--model", choices=sorted(MODELS), default="rf")
    args = parser.parse_args()
    label, model_path = MODELS[args.model]
    suffix = "" if args.model == "rf" else f"_{args.model}"
    district_slug = config.DEMO_DISTRICT.lower().replace(" ", "_")
    html_path = config.DEMO_MAP_HTML.with_name(f"{config.DEMO_MAP_HTML.stem}{suffix}.html")
    tif_path = config.PROCESSED_DIR / f"susceptibility_{district_slug}_{args.model}.tif"

    print(config.data_source_banner())
    for path in (model_path, config.SCALER_PATH, config.FEATURE_NAMES_PATH, config.DATASET_CSV):
        if not path.exists():
            raise SystemExit(f"{path} not found. Run Steps 4 to 6 first.")
    model = joblib.load(model_path)
    scaler = joblib.load(config.SCALER_PATH)
    feature_names = artifacts.load_feature_names()
    if list(getattr(model, "feature_names_in_", feature_names)) != feature_names:
        raise SystemExit("The model's features do not match models/feature_names.json. Retrain Steps 4 to 6.")
    if hasattr(model, "n_jobs"):
        model.n_jobs = config.N_JOBS  # trained with 1 job inside the grid search; predict on every core
    dataset = pd.read_csv(config.DATASET_CSV)
    profile = training_profile(dataset, feature_names)
    timings, started = {}, time.perf_counter()

    print(f"\n[1] Reading {config.DEMO_DISTRICT} from the aligned rasters")
    tick = time.perf_counter()
    geometry, district_m2 = district_geometry()
    grid = read_district(geometry)
    lookups = category_lookups()
    timings["read"] = time.perf_counter() - tick
    n_inside, n_water, n_scorable = int(grid["inside"].sum()), int(grid["water"].sum()), int(grid["scorable"].sum())
    n_nodata = n_inside - n_water - n_scorable
    print(f"  window {grid['shape'][1]:,} x {grid['shape'][0]:,} cells; {n_inside:,} inside the district "
          f"({n_inside * 900 / 1e6:,.0f} km2)")
    print(f"  skipped: {n_water:,} water cells, {n_nodata:,} cells with NoData in a layer")
    print(f"  to score: {n_scorable:,} cells   ({timings['read']:.1f} s)")

    fills = {}
    for col in config.active_categorical_features():
        if col not in grid["layers"]:
            fills[col] = dataset[col].dropna().astype(str).mode().iloc[0]
            print(f"  WARNING: no raster for {col}; every cell gets the most common training value "
                  f"({fills[col]}). Build the layer, or add {col} to DROPPED_COLUMNS with the reason.")

    print("\n[2] What the models were never trained on")
    diagnostics = check_inputs(grid, lookups, profile)
    for feature, share in diagnostics["outside_training_range_percent"].items():
        low, high = profile["ranges"][feature]
        print(f"  {feature}: {share:.1f}% of cells outside the training range {low:,.1f} to {high:,.1f}")
        if share > 50:
            # Seen on the synthetic models (14 September): real dist_faults in Rudraprayag is 56 to 127 km,
            # far beyond training, and the RBF SVM scored every cell 0.000 while RF was unaffected. An RBF
            # kernel decays towards its intercept away from all support vectors; trees just use their
            # last split. Swapping that one input for a typical value restored the SVM scores.
            print(f"    WARNING: most of the district lies outside what the models saw for {feature}. "
                  f"RBF SVM scores can collapse to one class there; treat this map as unreliable.")
    for feature, classes in diagnostics["classes_unknown_to_model"].items():
        listed = ", ".join(f"{name} ({count:,} cells)" for name, count in classes.items())
        print(f"  {feature}: classes the model has no column for, scored as the reference class: {listed}")
    if not any(diagnostics.values()):
        print("  nothing: every value and class is inside what the models saw")
    if config.IS_SYNTHETIC:
        print("  (Expected on synthetic models. With real models these should be near zero.)")

    print(f"\n[3] Scoring with {label}, {CHUNK_ROWS:,} cells per chunk")
    tick = time.perf_counter()
    cells = np.flatnonzero(grid["scorable"].ravel())
    scores = np.full(grid["shape"][0] * grid["shape"][1], NODATA_SCORE, dtype=np.float32)
    for start in range(0, len(cells), CHUNK_ROWS):
        chunk = cells[start:start + CHUNK_ROWS]
        X = prepare_for_prediction(rows_for(chunk, grid["layers"], lookups, fills), feature_names, scaler)
        scores[chunk] = model.predict_proba(pd.DataFrame(X, columns=feature_names))[:, 1]
        done = start + len(chunk)
        print(f"  {done:>10,} / {len(cells):,} cells   {time.perf_counter() - tick:6.1f} s")
    timings["predict"] = time.perf_counter() - tick
    scores = scores.reshape(grid["shape"])
    rate = len(cells) / timings["predict"]

    print("\n[4] Risk zones")
    zones = np.zeros(grid["shape"], dtype=np.uint8)
    zones[grid["scorable"]] = np.digitize(scores[grid["scorable"]], config.RISK_ZONE_BREAKS) + 1
    edges = [0.0, *config.RISK_ZONE_BREAKS, 1.0]
    zone_rows = []
    for i, name in enumerate(config.RISK_ZONES, start=1):
        count = int((zones == i).sum())
        zone_rows.append({"zone": name, "score_range": f"{edges[i - 1]:.1f}-{edges[i]:.1f}", "cells": count,
                          "area_km2": round(count * 900 / 1e6, 1),
                          "share_percent": round(100 * count / max(len(cells), 1), 1)})
        print(f"  {name:<10} {zone_rows[-1]['score_range']}  {count:>10,} cells  "
              f"{zone_rows[-1]['area_km2']:>8,.1f} km2  {zone_rows[-1]['share_percent']:5.1f}%")
    valid_scores = scores[grid["scorable"]]
    score_stats = {k: round(float(v), 4) for k, v in zip(
        ["min", "p05", "median", "p95", "max"], np.percentile(valid_scores, [0, 5, 50, 95, 100]))}
    print(f"  scores: median {score_stats['median']:.3f}, 5th to 95th percentile "
          f"{score_stats['p05']:.3f} to {score_stats['p95']:.3f}")

    print("\n[5] Writing outputs")
    tick = time.perf_counter()
    write_scores(scores, grid, tif_path)
    timings["write_geotiff"] = time.perf_counter() - tick
    tick = time.perf_counter()
    config.OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    render_map(zones, grid, geometry, zone_rows, label, html_path)
    timings["render_map"] = time.perf_counter() - tick
    timings["total"] = time.perf_counter() - started
    print(f"  {tif_path.relative_to(config.ROOT)}  ({tif_path.stat().st_size / 1e6:.1f} MB)")
    print(f"  {html_path.relative_to(config.ROOT)}  ({html_path.stat().st_size / 1e6:.1f} MB)")

    # Projection for the whole state. Scoring time grows with the number of cells, so scale by area.
    import geopandas as gpd

    state_m2 = float(gpd.read_file(config.STATE_BOUNDARY).to_crs(config.PROJECT_CRS).area.sum())
    state_cells = state_m2 / config.DEM_RESOLUTION_M ** 2
    scale = state_cells / n_inside
    projection = {
        "state_cells_estimate": int(state_cells),
        "predict_minutes": round(state_cells * (len(cells) / n_inside) / rate / 60, 1),
        "total_minutes": round(timings["total"] * scale / 60, 1),
        "note": (f"Linear scaling by area from this run ({scale:.0f} times the district). A single "
                 f"in-memory pass would need about {state_cells * len(feature_names) * 8 / 1e9:.0f} GB "
                 f"for the model input alone, so Phase 3 must process the state in tiles."),
    }

    print("\nTiming")
    for stage, seconds in timings.items():
        print(f"  {stage:<14} {seconds:7.1f} s")
    print(f"  rate           {rate:,.0f} cells per second ({label})")
    print(f"\nWhole state, projected (Phase 3): about {state_cells / 1e6:.1f} million cells, "
          f"{projection['predict_minutes']:.0f} min of scoring, {projection['total_minutes']:.0f} min end to end")
    print(f"  {projection['note']}")

    artifacts.update_metadata(f"demo_map{suffix}", {
        "model": label,
        "district": config.DEMO_DISTRICT,
        "cells_in_district": n_inside,
        "cells_water_skipped": n_water,
        "cells_nodata_skipped": n_nodata,
        "cells_scored": int(len(cells)),
        "zone_breaks": config.RISK_ZONE_BREAKS,
        "zones": zone_rows,
        "score_stats": score_stats,
        "input_diagnostics": diagnostics,
        "filled_without_raster": fills,
        "synthetic_class_bridge_applied": config.IS_SYNTHETIC,
        "timing_seconds": {k: round(v, 1) for k, v in timings.items()},
        "cells_per_second": round(rate),
        "projection_full_state": projection,
        "outputs": [str(tif_path.relative_to(config.ROOT)), str(html_path.relative_to(config.ROOT))],
    })
    print(f"\nmodels/metadata.json: demo_map{suffix} section written")
    return 0


if __name__ == "__main__":
    # Required on Windows: Random Forest prediction with n_jobs=-1 starts worker processes.
    sys.exit(main())
