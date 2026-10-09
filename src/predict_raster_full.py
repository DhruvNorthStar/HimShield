"""
Phase 3: Random Forest susceptibility rasters for one district or the whole state, processed in strips.

    python src/predict_raster_full.py --district rudraprayag
    python src/predict_raster_full.py --state                  warns first; add --yes to run
    python src/predict_raster_full.py --state --estimate-only   estimates only, predicts nothing

Why it is built this way (8 GB RAM, 4-thread i3, Windows):
- The state grid is 11,123 x 10,135 cells. As one model input it would need about 14 GB, so the area is
  processed in horizontal strips of rows: read one strip from every raster, score it, write it to disk,
  let it go. Memory use depends on the strip size, not on the area.
- The strip size comes from the RAM free when the script starts: at most a quarter of it, and never
  more than 1.2 GB, is planned for one strip.
- Every cell goes through exactly the code the Phase 2 demo map uses (src.demo_map for raster names,
  class lookups and row building, src.preprocess.prepare_for_prediction for the transform), so a
  district run reproduces the Phase 2 map cell for cell.
- Random Forest only: the RBF SVM scored Rudraprayag at about 7,000 cells a second against RF's
  150,000, which projects to over two hours for the state.
- Time is estimated before anything runs, from the Phase 2 Rudraprayag timing in metadata.json scaled
  by area, and refined after the first strip. Anything over 5 minutes, and every --state run, stops
  with a warning unless --yes is given.

Outputs (data/processed/, ignored by git):
    susceptibility_<area>_probability.tif   Float32 landslide score, NoData -9999
    susceptibility_<area>_zones.tif         UInt8 risk zones 1 to 5 (breaks in config), 0 = no data,
                                            with the Phase 2 colour ramp embedded; its tags carry the
                                            run summary (model, data source, zone counts, timings)
<area> is the district name, or "uk" for the whole state. Water and cells with a gap in any layer
are left as no data, exactly as in the Phase 2 demo map.
"""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    # Lets `python src/predict_raster_full.py` work as well as `python -m src.predict_raster_full`.
    sys.path.insert(0, str(ROOT))

# Cap GDAL's raster block cache before anything loads GDAL. Left alone, GDAL may keep up to 5 percent of
# RAM (about 410 MB on an 8 GB laptop) in cached blocks: memory the strip plan cannot see. Measured on
# Rudraprayag, halving the strip size moved the peak only from 0.80 to 0.74 GB, which is that cache.
GDAL_CACHE_MB = 256
os.environ["GDAL_CACHEMAX"] = str(GDAL_CACHE_MB)

import joblib  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from src import artifacts, config  # noqa: E402
from src.demo_map import (NODATA_SCORE, RASTERS, WATER_CODE, ZONE_COLOURS, category_lookups,  # noqa: E402
                          rows_for, training_profile)
from src.preprocess import prepare_for_prediction  # noqa: E402

STATE_SLUG = "uk"
LONG_STEP_SECONDS = 300          # project rule: warn before anything over 5 minutes
BYTES_PER_CELL = 1_000           # planning figure for one scored cell: row frame, dummies, scaled copy,
                                 # float32 copy inside the forest, per-thread tree outputs. Measured on
                                 # Rudraprayag (14 Sep 2026): strips of 207,536 and 104,640 cells peaked at
                                 # 0.80 and 0.74 GB, about 600 bytes per extra cell; the rest was the GDAL
                                 # cache, now capped above and counted separately. 1,000 leaves a margin.
RAM_SHARE = 0.25                 # share of free RAM planned for one strip
MAX_STRIP_BYTES = 1_200_000_000  # never plan more than 1.2 GB for one strip
MIN_STRIP_BYTES = 100_000_000    # nor less than 100 MB, or the run crawls
FALLBACK_AVAILABLE = 2_000_000_000


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------
def memory_snapshot() -> dict:
    """Free RAM and this process's current and peak memory, in bytes (None where unavailable)."""
    try:
        import psutil
    except ImportError:
        return {"total": None, "available": None, "rss": None, "peak": None}
    vm, info = psutil.virtual_memory(), psutil.Process().memory_info()
    peak = getattr(info, "peak_wset", None)  # Windows reports the peak working set directly
    return {"total": vm.total, "available": vm.available, "rss": info.rss, "peak": peak}


def gb(n) -> str:
    return "unknown" if n is None else f"{n / 1e9:.2f} GB"


def plan_strips(width: int, snapshot: dict, override_mb: int | None) -> tuple[int, int]:
    """Rows per strip and the planned bytes per strip, sized to the RAM that is actually free."""
    if override_mb:
        budget = override_mb * 1_000_000
    else:
        available = snapshot["available"] or FALLBACK_AVAILABLE
        budget = int(min(max(available * RAM_SHARE, MIN_STRIP_BYTES), MAX_STRIP_BYTES))
    rows = max(1, budget // (BYTES_PER_CELL * width))
    return int(rows), int(rows * width * BYTES_PER_CELL)


# ---------------------------------------------------------------------------
# Area
# ---------------------------------------------------------------------------
def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def area_geometry(args) -> tuple[str, str, object, float]:
    """Display name, file slug, geometry in the project CRS, and area in m2."""
    import geopandas as gpd

    if args.state:
        state = gpd.read_file(config.STATE_BOUNDARY).to_crs(config.PROJECT_CRS)
        return "Uttarakhand (whole state)", STATE_SLUG, state.geometry.union_all(), float(state.area.sum())
    districts = gpd.read_file(config.DISTRICT_BOUNDARIES).to_crs(config.PROJECT_CRS)
    match = districts[districts["district"].map(slugify) == slugify(args.district)]
    if match.empty:
        raise SystemExit(f"No district called {args.district!r}. Choose one of: "
                         + ", ".join(sorted(slugify(d) for d in districts["district"])))
    name = match["district"].iloc[0]
    return name, slugify(name), match.geometry.union_all(), float(match.area.sum())


# ---------------------------------------------------------------------------
# Estimates
# ---------------------------------------------------------------------------
def reference_timing(meta: dict) -> dict | None:
    """The Phase 2 Rudraprayag RF run, if it was made with the current model."""
    demo = meta.get("demo_map", {})
    written = meta.get("written", {}).get("demo_map")
    if demo.get("model") != "Random Forest" or not demo.get("cells_scored") or not written:
        return None
    model_time = datetime.fromtimestamp(config.RF_MODEL_PATH.stat().st_mtime, tz=timezone.utc)
    if datetime.fromisoformat(written) < model_time:
        return None  # timed with an older model
    t = demo["timing_seconds"]
    return {"cells": demo["cells_scored"], "predict": t["predict"],
            "pipeline": t.get("read", 0) + t["predict"] + t.get("write_geotiff", 0),
            "inside": demo.get("cells_in_district", demo["cells_scored"])}


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------
def open_outputs(prob_path: Path, zone_path: Path, height: int, width: int, transform, crs):
    import rasterio

    common = {"driver": "GTiff", "height": height, "width": width, "count": 1, "crs": crs,
              "transform": transform, "tiled": True, "blockxsize": 512, "blockysize": 512,
              "compress": "deflate", "BIGTIFF": "IF_SAFER"}
    prob = rasterio.open(prob_path, "w", dtype="float32", nodata=NODATA_SCORE, predictor=3, **common)
    zones = rasterio.open(zone_path, "w", dtype="uint8", nodata=0, **common)
    colours = {0: (0, 0, 0, 0)}
    for zone, hex_colour in enumerate(ZONE_COLOURS, start=1):
        colours[zone] = tuple(int(hex_colour[i:i + 2], 16) for i in (1, 3, 5)) + (255,)
    zones.write_colormap(1, colours)
    return prob, zones


# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description="Chunked Random Forest susceptibility rasters")
    where = parser.add_mutually_exclusive_group(required=True)
    where.add_argument("--district", help="district name, for example rudraprayag or tehri_garhwal")
    where.add_argument("--state", action="store_true", help="the whole of Uttarakhand (warns first)")
    parser.add_argument("--yes", action="store_true", help="run even if the estimate is over 5 minutes or --state")
    parser.add_argument("--estimate-only", action="store_true", help="print the estimates and stop")
    parser.add_argument("--max-chunk-mb", type=int, help="override the automatic memory budget per strip")
    args = parser.parse_args()

    import rasterio
    from rasterio.features import geometry_mask
    from rasterio.windows import Window, from_bounds
    try:
        from tqdm import tqdm
    except ImportError:  # the Phase 2 lock file lacks tqdm; environment.phase3.yml adds it
        tqdm = None

    print(config.data_source_banner())
    for path in (config.RF_MODEL_PATH, config.SCALER_PATH, config.FEATURE_NAMES_PATH, config.DATASET_CSV):
        if not path.exists():
            raise SystemExit(f"{path} not found. Run python src/verify_phase2.py first.")

    started = time.perf_counter()
    rf = joblib.load(config.RF_MODEL_PATH)
    scaler = joblib.load(config.SCALER_PATH)
    names = artifacts.load_feature_names()
    if list(rf.feature_names_in_) != names:
        raise SystemExit("The RF model and feature_names.json disagree. Run python src/verify_phase2.py.")
    rf.n_jobs = config.N_JOBS
    meta = json.loads(config.METADATA_PATH.read_text(encoding="utf-8")) if config.METADATA_PATH.exists() else {}
    dataset = pd.read_csv(config.DATASET_CSV)
    profile = training_profile(dataset, names)
    lookups = category_lookups()
    fills = {c: dataset[c].dropna().astype(str).mode().iloc[0]
             for c in config.active_categorical_features() if c not in RASTERS}

    label, slug, geometry, area_m2 = area_geometry(args)
    reference = config.PROCESSED_DIR / "dem.tif"
    with rasterio.open(reference) as ref:
        window = from_bounds(*geometry.bounds, transform=ref.transform).round_offsets().round_lengths()
        window = window.intersection(Window(0, 0, ref.width, ref.height))
        out_transform, crs, ref_transform = ref.window_transform(window), ref.crs, ref.transform
    height, width = int(window.height), int(window.width)
    expected_cells = area_m2 / config.DEM_RESOLUTION_M ** 2

    print(f"\n[1] Area: {label}")
    print(f"    window {width:,} x {height:,} cells ({width * height / 1e6:.1f} million), "
          f"about {expected_cells / 1e6:.2f} million cells inside ({area_m2 / 1e6:,.0f} km2)")

    before = memory_snapshot()
    rows_per_strip, strip_bytes = plan_strips(width, before, args.max_chunk_mb)
    n_strips = -(-height // rows_per_strip)
    print("\n[2] Memory estimate")
    print(f"    RAM: {gb(before['total'])} total, {gb(before['available'])} free now; "
          f"this process uses {gb(before['rss'])} with the model loaded")
    print(f"    strip plan: {rows_per_strip:,} rows x {width:,} columns = up to {rows_per_strip * width:,} cells, "
          f"about {gb(strip_bytes)} at {BYTES_PER_CELL:,} bytes per cell; {n_strips:,} strips")
    expected_peak = (before["rss"] or 0) + GDAL_CACHE_MB * 1_000_000 + strip_bytes
    if before["rss"] is not None:
        print(f"    expected peak: about {gb(expected_peak)} (process {gb(before['rss'])} + GDAL cache "
              f"{GDAL_CACHE_MB} MB + one strip {gb(strip_bytes)})")

    timing = reference_timing(meta)
    print("\n[3] Time estimate")
    estimate = None
    if timing:
        scale = expected_cells / timing["inside"]
        estimate = timing["pipeline"] * scale
        print(f"    Phase 2 Rudraprayag reference: {timing['cells']:,} cells, {timing['predict']:.1f} s scoring, "
              f"{timing['pipeline']:.1f} s with reading and writing")
        print(f"    scale factor {scale:.2f}x by area -> about {estimate:.0f} s ({estimate / 60:.1f} min); "
              f"refined after the first strip")
    else:
        print("    no current Phase 2 RF timing in metadata.json (run python -m src.demo_map); "
              "the estimate will come from the first strip")

    too_long = estimate is None or estimate > LONG_STEP_SECONDS
    if args.estimate_only:
        print("\n--estimate-only: nothing predicted.")
        return 0
    if (args.state or too_long) and not args.yes:
        why = "the whole state was requested" if args.state else "the estimate is over 5 minutes or unknown"
        print(f"\nWARNING: stopping before prediction because {why}.")
        if estimate is not None:
            print(f"    expected: about {estimate / 60:.1f} min, peak memory about "
                  f"{gb(expected_peak)}. Close other programs first.")
        print("    Rerun with --yes to go ahead.")
        return 2

    prob_path = config.PROCESSED_DIR / f"susceptibility_{slug}_probability.tif"
    zone_path = config.PROCESSED_DIR / f"susceptibility_{slug}_zones.tif"
    sources = {}
    for feature, name in RASTERS.items():
        if feature in config.DROPPED_COLUMNS:
            continue
        src = rasterio.open(config.PROCESSED_DIR / f"{name}.tif")
        if src.crs != crs or not src.transform.almost_equals(ref_transform):
            raise SystemExit(f"{name}.tif is not on the dem.tif grid. Run python -m src.check_layers.")
        sources[feature] = src
    prob_out, zone_out = open_outputs(prob_path, zone_path, height, width, out_transform, crs)

    counts = np.zeros(len(config.RISK_ZONES) + 1, dtype=np.int64)
    inside_total = water_total = scored_total = 0
    outside_range = {f: 0 for f in profile["ranges"] if f in sources}
    score_sum = 0.0
    predict_seconds = 0.0
    refined = False
    print(f"\n[4] Scoring {label} with the Random Forest, {n_strips:,} strips")
    bar = tqdm(total=height, unit="row", desc="rows", ncols=90) if tqdm else None
    loop_started = time.perf_counter()
    try:
        for strip_index, row_off in enumerate(range(0, height, rows_per_strip)):
            h = min(rows_per_strip, height - row_off)
            strip = Window(window.col_off, window.row_off + row_off, width, h)
            strip_transform = rasterio.windows.transform(strip, ref_transform)
            inside = geometry_mask([geometry], out_shape=(h, width), transform=strip_transform, invert=True)
            prob = np.full((h, width), NODATA_SCORE, dtype=np.float32)
            zones = np.zeros((h, width), dtype=np.uint8)

            if inside.any():
                layers, readable = {}, inside.copy()
                for feature, src in sources.items():
                    data = src.read(1, window=strip)
                    if src.nodata is not None and not np.isnan(src.nodata):
                        readable &= data != src.nodata
                    if np.issubdtype(data.dtype, np.floating):
                        readable &= np.isfinite(data)
                    layers[feature] = data
                water = readable & (layers["lulc"] == WATER_CODE)
                scorable = readable & ~water
                cells = np.flatnonzero(scorable.ravel())
                inside_total += int(inside.sum())
                water_total += int(water.sum())
                if len(cells):
                    for feature in outside_range:
                        low, high = profile["ranges"][feature]
                        values = layers[feature].ravel()[cells]
                        outside_range[feature] += int(((values < low) | (values > high)).sum())
                    tick = time.perf_counter()
                    X = prepare_for_prediction(rows_for(cells, layers, lookups, fills), names, scaler)
                    scores = rf.predict_proba(pd.DataFrame(X, columns=names))[:, 1].astype(np.float32)
                    predict_seconds += time.perf_counter() - tick
                    prob.ravel()[cells] = scores
                    zone_values = (np.digitize(scores, config.RISK_ZONE_BREAKS) + 1).astype(np.uint8)
                    zones.ravel()[cells] = zone_values
                    counts += np.bincount(zone_values, minlength=len(counts))
                    scored_total += len(cells)
                    score_sum += float(scores.sum(dtype=np.float64))

            prob_out.write(prob, 1, window=Window(0, row_off, width, h))
            zone_out.write(zones, 1, window=Window(0, row_off, width, h))
            if bar:
                bar.update(h)
                bar.set_postfix(cells=f"{scored_total:,}")
            # Refine by cells inside the area, not by rows: strips at the edge of the window are mostly
            # outside the boundary and finish almost at once, so rows done would understate the time.
            if not refined and inside_total >= 0.05 * expected_cells:
                elapsed = time.perf_counter() - loop_started
                projected = elapsed / inside_total * expected_cells
                message = (f"    refined estimate after {100 * inside_total / expected_cells:.0f}% of the area: "
                           f"about {projected:.0f} s in total")
                (bar.write if bar else print)(message)
                refined = True
    finally:
        if bar:
            bar.close()
        for src in sources.values():
            src.close()

    loop_seconds = time.perf_counter() - loop_started
    after = memory_snapshot()
    zone_rows = []
    for i, name in enumerate(config.RISK_ZONES, start=1):
        zone_rows.append({"zone": name, "cells": int(counts[i]), "area_km2": round(counts[i] * 900 / 1e6, 1),
                          "share_percent": round(100 * counts[i] / max(scored_total, 1), 1)})
    summary = {
        "written": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "area": label, "model": "Random Forest", "data_source": config.DATA_SOURCE,
        "rf_model_mtime": config.RF_MODEL_PATH.stat().st_mtime,
        "cells_inside": inside_total, "cells_water_skipped": water_total, "cells_scored": scored_total,
        "mean_score": round(score_sum / max(scored_total, 1), 4),
        "zone_breaks": config.RISK_ZONE_BREAKS, "zones": zone_rows,
        "outside_training_range_percent": {f: round(100 * n / max(scored_total, 1), 2)
                                           for f, n in outside_range.items() if n},
        "filled_without_raster": fills,
        "strips": {"rows_per_strip": rows_per_strip, "count": n_strips, "planned_bytes": strip_bytes},
        "timing_seconds": {"predict": round(predict_seconds, 1), "loop": round(loop_seconds, 1),
                           "total": round(time.perf_counter() - started, 1)},
        "memory_bytes": {"rss_before": before["rss"], "peak": after["peak"], "planned_peak": expected_peak,
                         "available_before": before["available"], "gdal_cache_mb": GDAL_CACHE_MB},
    }
    zone_out.update_tags(PHASE3_SUMMARY=json.dumps(summary))
    prob_out.update_tags(PHASE3_SUMMARY=json.dumps({k: summary[k] for k in
                                                    ("written", "area", "model", "data_source", "rf_model_mtime")}))
    prob_out.close()
    zone_out.close()

    print("\n[5] Result")
    print(f"    {inside_total:,} cells inside, {water_total:,} water skipped, {scored_total:,} scored")
    for row in zone_rows:
        print(f"    {row['zone']:<10} {row['cells']:>12,} cells  {row['area_km2']:>9,.1f} km2  {row['share_percent']:5.1f}%")
    if summary["outside_training_range_percent"]:
        print("    outside the training range: " + ", ".join(
            f"{f} {p}%" for f, p in summary["outside_training_range_percent"].items()))
    print(f"    {prob_path.relative_to(config.ROOT)}  ({prob_path.stat().st_size / 1e6:.1f} MB)")
    print(f"    {zone_path.relative_to(config.ROOT)}  ({zone_path.stat().st_size / 1e6:.1f} MB)")

    print("\n[6] Timing and memory")
    rate = scored_total / predict_seconds if predict_seconds else 0
    print(f"    scoring {predict_seconds:.1f} s ({rate:,.0f} cells/s), strip loop {loop_seconds:.1f} s, "
          f"whole run {summary['timing_seconds']['total']:.1f} s")
    if after["peak"] is not None:
        print(f"    peak memory of this process: {gb(after['peak'])} "
              f"(planned about {gb(expected_peak)})")
    if not args.state and rate:
        import geopandas as gpd

        state_cells = float(gpd.read_file(config.STATE_BOUNDARY).to_crs(config.PROJECT_CRS).area.sum()) / 900
        per_cell_loop = loop_seconds / max(inside_total, 1)
        print(f"    whole state at this pace: about {state_cells * per_cell_loop / 60:.0f} min for "
              f"{state_cells / 1e6:.1f} million cells (run with --state --yes)")

    demo = meta.get("demo_map", {})
    if slug == slugify(config.DEMO_DISTRICT) and demo.get("model") == "Random Forest" and demo.get("zones"):
        print(f"\n[7] Compared with the Phase 2 demo map ({config.DEMO_DISTRICT}, Random Forest)")
        print(f"    {'zone':<10} {'this run':>9} {'Phase 2':>9} {'difference':>11}")
        for mine, theirs in zip(zone_rows, demo["zones"]):
            diff = mine["share_percent"] - theirs["share_percent"]
            print(f"    {mine['zone']:<10} {mine['share_percent']:>8.1f}% {theirs['share_percent']:>8.1f}% "
                  f"{diff:>+10.1f} pts")
        print(f"    cells scored: this run {scored_total:,}, Phase 2 {demo.get('cells_scored', 0):,}")
    if config.IS_SYNTHETIC:
        print(f"\n{config.SYNTHETIC_LABEL}: a pipeline test on simulated training data, not a map of Uttarakhand.")
    return 0


if __name__ == "__main__":
    # Required on Windows: Random Forest prediction with n_jobs=-1 starts worker threads and processes.
    sys.exit(main())
