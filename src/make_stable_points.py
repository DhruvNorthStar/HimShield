"""
Step 2e: sample stable (non-landslide) points, NEG_TO_POS_RATIO per landslide point.

    python -m src.make_stable_points                          writes data/shapefiles/non_landslides.gpkg
    python -m src.make_stable_points --out x.gpkg --figure y.png

Rules (docs/02_qgis_processing.md section 2e, docs/decisions.md):
1. Uniformly random inside the state boundary, seed config.RANDOM_STATE.
2. At least NEGATIVE_BUFFER_M from every GSI inventory point, not only the cleaned training points: a record
   dropped for a vague coordinate still says a landslide happened somewhere near there.
3. Not within WATER_BUFFER_M of a WorldCover "Permanent water bodies" cell (code 80): a lake is not stable terrain.
4. At least NEGATIVE_BUFFER_M from every other stable point, so negatives do not bunch up.
5. Every active factor raster has a value at the point, so each point becomes a usable row in Step 2f.
Candidates are tested in the order they are drawn and the first N that pass are kept, so the same seed
always gives the same points.
"""
import argparse
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from scipy.spatial import cKDTree
from shapely import contains_xy, prepare
from shapely.geometry import box

from src import config
from src.clean_gsi import GSI_LAYER, GSI_ZIP
from src.demo_map import RASTERS, WATER_CODE

LANDSLIDES = config.SHAPEFILE_DIR / "landslides.gpkg"
OUTPUT = config.SHAPEFILE_DIR / "non_landslides.gpkg"
WATER_BUFFER_M = 50
BATCH = 20_000
QUADRAT_M = 20_000  # grid for the clustering check


def factor_rasters() -> dict[str, Path]:
    return {f: config.PROCESSED_DIR / f"{name}.tif" for f, name in RASTERS.items() if f not in config.DROPPED_COLUMNS}


def valid_everywhere(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """True where every active factor raster holds a real value."""
    ok = np.ones(len(x), dtype=bool)
    order = np.argsort(-y)  # north to south, so the strip reads run in file order
    coords = list(zip(x[order], y[order]))
    for path in factor_rasters().values():
        with rasterio.open(path) as src:
            values = np.fromiter((v[0] for v in src.sample(coords)), dtype="float64", count=len(coords))
            good = np.isfinite(values)
            if src.nodata is not None and np.isfinite(src.nodata):
                good &= values != src.nodata
        ok[order] &= good
    return ok


def near_water(x: np.ndarray, y: np.ndarray, lulc: np.ndarray, transform) -> np.ndarray:
    """True where any water cell lies within WATER_BUFFER_M of the point (distance to the cell's edge)."""
    size = transform.a
    reach = int(np.ceil(WATER_BUFFER_M / size))
    col = np.floor((x - transform.c) / size).astype(int)
    row = np.floor((transform.f - y) / size).astype(int)
    hit = np.zeros(len(x), dtype=bool)
    for dr in range(-reach, reach + 1):
        for dc in range(-reach, reach + 1):
            r, c = row + dr, col + dc
            inside = (r >= 0) & (r < lulc.shape[0]) & (c >= 0) & (c < lulc.shape[1])
            water = np.zeros(len(x), dtype=bool)
            water[inside] = lulc[r[inside], c[inside]] == WATER_CODE
            xmin, ymax = transform.c + c * size, transform.f - r * size
            dx = np.maximum(np.maximum(xmin - x, x - (xmin + size)), 0)
            dy = np.maximum(np.maximum((ymax - size) - y, y - ymax), 0)
            hit |= water & (np.hypot(dx, dy) < WATER_BUFFER_M)
    return hit


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--out", type=Path, default=OUTPUT)
    parser.add_argument("--figure", type=Path, default=None, help="optional PNG of both point sets")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="ascii", errors="backslashreplace")

    if not LANDSLIDES.exists():
        raise SystemExit(f"{LANDSLIDES} not found. Run `python -m src.clean_gsi` first.")
    positives = gpd.read_file(LANDSLIDES)
    target = len(positives) * config.NEG_TO_POS_RATIO
    print(f"Landslide points: {len(positives):,} -> target {target:,} stable points (1:{config.NEG_TO_POS_RATIO})")

    state = gpd.read_file(config.STATE_BOUNDARY).to_crs(config.PROJECT_CRS)
    boundary = state.geometry.union_all()
    prepare(boundary)
    xmin, ymin, xmax, ymax = boundary.bounds

    gsi_all = gpd.read_file(f"zip://{GSI_ZIP.as_posix()}!{GSI_LAYER}").to_crs(config.PROJECT_CRS)
    gx, gy = gsi_all.geometry.x.values, gsi_all.geometry.y.values
    near_state = (gx > xmin - 5_000) & (gx < xmax + 5_000) & (gy > ymin - 5_000) & (gy < ymax + 5_000)
    exclusion = np.column_stack([gx[near_state], gy[near_state]])
    exclusion_tree = cKDTree(exclusion)
    print(f"Exclusion set: {len(exclusion):,} GSI points within 5 km of the state's bounding box "
          f"({len(positives):,} of them are the training points)")

    lulc_path = factor_rasters()["lulc"]
    with rasterio.open(lulc_path) as src:
        lulc, transform = src.read(1), src.transform
    print(f"Loaded {lulc_path.name} ({lulc.nbytes / 2**20:.0f} MB) for the water test")

    rng = np.random.default_rng(config.RANDOM_STATE)
    kept_x, kept_y = [], []
    occupied: dict[tuple[int, int], list[int]] = {}
    spacing = config.NEGATIVE_BUFFER_M
    drawn = 0
    rejected = {"outside state": 0, "near landslide": 0, "near water": 0, "no data": 0, "near stable point": 0}
    while len(kept_x) < target:
        x = rng.uniform(xmin, xmax, BATCH)
        y = rng.uniform(ymin, ymax, BATCH)
        drawn += BATCH
        inside = contains_xy(boundary, x, y)
        rejected["outside state"] += int((~inside).sum())
        x, y = x[inside], y[inside]

        dist, _ = exclusion_tree.query(np.column_stack([x, y]))
        far = dist >= config.NEGATIVE_BUFFER_M
        rejected["near landslide"] += int((~far).sum())
        x, y = x[far], y[far]

        wet = near_water(x, y, lulc, transform)
        rejected["near water"] += int(wet.sum())
        x, y = x[~wet], y[~wet]

        valid = valid_everywhere(x, y)
        rejected["no data"] += int((~valid).sum())
        x, y = x[valid], y[valid]

        for px, py in zip(x, y):  # draw order, so the result depends only on the seed
            if len(kept_x) >= target:
                break
            key = (int(px // spacing), int(py // spacing))
            clash = False
            for i in range(key[0] - 1, key[0] + 2):
                for j in range(key[1] - 1, key[1] + 2):
                    for k in occupied.get((i, j), ()):
                        if (kept_x[k] - px) ** 2 + (kept_y[k] - py) ** 2 < spacing ** 2:
                            clash = True
                            break
                    if clash:
                        break
                if clash:
                    break
            if clash:
                rejected["near stable point"] += 1
                continue
            occupied.setdefault(key, []).append(len(kept_x))
            kept_x.append(px)
            kept_y.append(py)
        print(f"  drawn {drawn:,}, kept {len(kept_x):,}")
    del lulc

    sx, sy = np.array(kept_x), np.array(kept_y)
    print(f"\nGENERATED: {len(sx):,} stable points from {drawn:,} random draws "
          f"(draws after the target was reached were not tested)")
    for reason, n in rejected.items():
        print(f"  rejected, {reason:<18} {n:>8,}")

    # ---- Verification, recomputed from scratch on the final points ----
    print("\nVERIFY")
    print(f"  inside the state boundary:            {contains_xy(boundary, sx, sy).all()}")
    d_train, _ = cKDTree(np.column_stack([positives.geometry.x, positives.geometry.y])).query(np.column_stack([sx, sy]))
    d_all, _ = exclusion_tree.query(np.column_stack([sx, sy]))
    print(f"  min distance to training landslides:  {d_train.min():,.1f} m (>= {config.NEGATIVE_BUFFER_M}: {d_train.min() >= config.NEGATIVE_BUFFER_M})")
    print(f"  min distance to any GSI point:        {d_all.min():,.1f} m (>= {config.NEGATIVE_BUFFER_M}: {d_all.min() >= config.NEGATIVE_BUFFER_M})")
    with rasterio.open(lulc_path) as src:
        codes = np.array([v[0] for v in src.sample(zip(sx, sy))])
    print(f"  land cover at the point = water (80): {(codes == WATER_CODE).sum()}")
    with rasterio.open(lulc_path) as src:
        lulc = src.read(1)
    print(f"  water cell within {WATER_BUFFER_M} m:              {near_water(sx, sy, lulc, transform).sum()}")
    del lulc
    nn, _ = cKDTree(np.column_stack([sx, sy])).query(np.column_stack([sx, sy]), k=2)
    nn = nn[:, 1]
    print(f"  nearest other stable point:           min {nn.min():,.0f} m, median {np.median(nn):,.0f} m, max {nn.max():,.0f} m")
    print(f"  every factor raster has a value:      {valid_everywhere(sx, sy).all()}")
    nasa = config.RAW_LANDSLIDE_DIR / "global_landslide_catalog_NASA.shp"
    if nasa.exists():
        n_pts = gpd.read_file(nasa).to_crs(config.PROJECT_CRS)
        n_pts = n_pts[n_pts.geometry.intersects(boundary)]
        d_nasa, _ = cKDTree(np.column_stack([n_pts.geometry.x, n_pts.geometry.y])).query(np.column_stack([sx, sy]))
        print(f"  within 500 m of a NASA GLC point:     {(d_nasa < 500).sum()} (NASA is overlay only, for information)")

    out = gpd.GeoDataFrame({config.TARGET: np.zeros(len(sx), dtype="int32")},
                           geometry=gpd.points_from_xy(sx, sy), crs=config.PROJECT_CRS)
    out.insert(0, "stable_id", np.arange(1, len(sx) + 1, dtype="int32"))

    # ---- Spatial distribution ----
    districts = gpd.read_file(config.DISTRICT_BOUNDARIES).to_crs(config.PROJECT_CRS)
    districts["area_km2"] = districts.area / 1e6
    total_area = boundary.area / 1e6
    s_join = gpd.sjoin(out[["geometry"]], districts[["district", "geometry"]], predicate="intersects", how="left")
    s_join = s_join[~s_join.index.duplicated()]
    l_join = gpd.sjoin(positives[["geometry"]], districts[["district", "geometry"]], predicate="intersects", how="left")
    l_join = l_join[~l_join.index.duplicated()]
    table = districts.set_index("district")[["area_km2"]]
    table["area_share_%"] = 100 * table["area_km2"] / total_area
    table["stable"] = s_join["district"].value_counts()
    table["stable_share_%"] = 100 * table["stable"] / len(out)
    table["landslides"] = l_join["district"].value_counts()
    table = table.fillna(0).sort_values("area_km2", ascending=False)
    print("\nDISTRIBUTION by district (stable share should track area share if the sampling is uniform)")
    print(f"  {'district':<18}{'km2':>8}{'area %':>8}{'stable':>8}{'stable %':>9}{'per 100 km2':>12}{'landslides':>11}")
    for name, r in table.iterrows():
        print(f"  {name:<18}{r['area_km2']:>8,.0f}{r['area_share_%']:>8.1f}{int(r['stable']):>8,}"
              f"{r['stable_share_%']:>9.1f}{100 * r['stable'] / r['area_km2']:>12.1f}{int(r['landslides']):>11,}")
    print(f"  {'(between polygons)':<18}{'':>8}{'':>8}{int(s_join['district'].isna().sum()):>8,}")

    col = ((sx - xmin) // QUADRAT_M).astype(int)
    row = ((ymax - sy) // QUADRAT_M).astype(int)
    cells = pd.Series(1, index=pd.MultiIndex.from_arrays([row, col])).groupby(level=[0, 1]).sum()
    interior = [(r, c) for r in range(int((ymax - ymin) // QUADRAT_M) + 1)
                for c in range(int((xmax - xmin) // QUADRAT_M) + 1)
                if boundary.contains(box(xmin + c * QUADRAT_M, ymax - (r + 1) * QUADRAT_M,
                                         xmin + (c + 1) * QUADRAT_M, ymax - r * QUADRAT_M))]
    counts = np.array([cells.get((r, c), 0) for r, c in interior])
    lx = ((positives.geometry.x.values - xmin) // QUADRAT_M).astype(int)
    ly = ((ymax - positives.geometry.y.values) // QUADRAT_M).astype(int)
    lcells = pd.Series(1, index=pd.MultiIndex.from_arrays([ly, lx])).groupby(level=[0, 1]).sum()
    lcounts = np.array([lcells.get((r, c), 0) for r, c in interior])
    print(f"\nCLUSTERING: {len(interior)} whole {QUADRAT_M // 1000} km squares inside the state")
    print(f"  stable points per square:    mean {counts.mean():.1f}, min {counts.min()}, max {counts.max()}, "
          f"empty {int((counts == 0).sum())}, variance/mean {counts.var(ddof=1) / counts.mean():.2f}")
    print(f"  landslide points per square: mean {lcounts.mean():.1f}, min {lcounts.min()}, max {lcounts.max()}, "
          f"empty {int((lcounts == 0).sum())}, variance/mean {lcounts.var(ddof=1) / lcounts.mean():.2f}")
    print("  (variance/mean near 1 = random, well below 1 = evenly spread, well above 1 = clustered)")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    if args.out.exists():
        args.out.unlink()
    out.to_file(args.out, layer="non_landslides", driver="GPKG")
    back = gpd.read_file(args.out)
    assert len(back) == target and set(back[config.TARGET]) == {0} and back.crs.to_epsg() == 32644
    print(f"\nWrote {args.out} ({len(back):,} rows, EPSG:{back.crs.to_epsg()}, columns {list(back.columns)})")

    if args.figure:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(1, 2, figsize=(13, 6.2), sharex=True, sharey=True)
        for ax, (title, pts, colour) in zip(axes, [
            (f"Stable points (n = {len(back):,})", back, "#0072B2"),
            (f"GSI landslide points (n = {len(positives):,})", positives, "#D55E00"),
        ]):
            districts.boundary.plot(ax=ax, color="#999999", linewidth=0.5)
            state.boundary.plot(ax=ax, color="#333333", linewidth=0.9)
            pts.plot(ax=ax, markersize=1.2, color=colour, alpha=0.7)
            ax.set_title(title)
            ax.set_axis_off()
        fig.suptitle("Uttarakhand, EPSG:32644. Stable points: seed 42, 500 m from any GSI point, no water")
        fig.tight_layout(rect=(0, 0, 1, 0.94))
        fig.savefig(args.figure, dpi=150)
        print(f"Figure: {args.figure}")


if __name__ == "__main__":
    main()
