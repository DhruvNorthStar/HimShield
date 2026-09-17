"""
Step 2f: sample every factor raster at the landslide and stable points.

    python -m src.extract_points
    python -m src.label_categories data/processed/dataset_raw.csv      (Step 2g, writes dataset.csv)

Does what docs/02_qgis_processing.md section 2f does with "Sample raster values": each point takes the value of
the 30 m cell it falls in (no interpolation). Every raster's own NoData value becomes an empty cell, so a
NoData code can never be read as a class. Outputs:
    data/shapefiles/all_points.gpkg     both point sets with their values, for checking in QGIS
    data/processed/dataset_raw.csv      the same without geometry, plus x and y, for label_categories
Each row keeps a point_id (GSI-<OBJECTID> or STABLE-<n>) so any row can be traced back to its source.
"""
import sys

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio

from src import config
from src.check_layers import EXPECTED
from src.demo_map import RASTERS, WATER_CODE

LANDSLIDES = config.SHAPEFILE_DIR / "landslides.gpkg"
STABLE = config.SHAPEFILE_DIR / "non_landslides.gpkg"
ALL_POINTS = config.SHAPEFILE_DIR / "all_points.gpkg"
RAW_CSV = config.PROCESSED_DIR / "dataset_raw.csv"


def column_name(feature: str) -> str:
    """label_categories expects the soil codes in a column called soil, then renames it soil_type."""
    return "soil" if feature == "soil_type" else feature


def main() -> int:
    sys.stdout.reconfigure(encoding="ascii", errors="backslashreplace")
    for path in (LANDSLIDES, STABLE):
        if not path.exists():
            raise SystemExit(f"{path} not found. Run `python -m src.clean_gsi` and `python -m src.make_stable_points`.")

    pos = gpd.read_file(LANDSLIDES)
    neg = gpd.read_file(STABLE)
    for name, g in [("landslides", pos), ("non_landslides", neg)]:
        if g.crs.to_epsg() != 32644:
            raise SystemExit(f"{name}.gpkg is not in EPSG:32644")
    points = pd.concat([
        gpd.GeoDataFrame({"point_id": "GSI-" + pos["gsi_objectid"].astype(str), config.TARGET: 1},
                         geometry=pos.geometry.values, crs=pos.crs),
        gpd.GeoDataFrame({"point_id": "STABLE-" + neg["stable_id"].astype(str), config.TARGET: 0},
                         geometry=neg.geometry.values, crs=neg.crs),
    ], ignore_index=True)
    points[config.TARGET] = points[config.TARGET].astype("int32")
    points["x"], points["y"] = points.geometry.x.round(2), points.geometry.y.round(2)
    print(f"Points: {len(pos):,} landslide + {len(neg):,} stable = {len(points):,}")

    order = np.argsort(-points["y"].to_numpy())  # north to south, so strip reads run in file order
    coords = list(zip(points["x"].to_numpy()[order], points["y"].to_numpy()[order]))
    with rasterio.open(config.PROCESSED_DIR / "dem.tif") as ref:
        ref_transform, ref_crs = ref.transform, ref.crs
    for feature, name in RASTERS.items():
        path = config.PROCESSED_DIR / f"{name}.tif"
        with rasterio.open(path) as src:
            if src.crs != ref_crs or not src.transform.almost_equals(ref_transform):
                raise SystemExit(f"{path.name} is not on the dem.tif grid. Run `python -m src.check_layers`.")
            values = np.fromiter((v[0] for v in src.sample(coords)), dtype="float64", count=len(coords))
            if src.nodata is not None:
                values[values == src.nodata] = np.nan
        values[~np.isfinite(values)] = np.nan
        column = np.empty(len(points))
        column[order] = values
        points[column_name(feature)] = column
        print(f"  sampled {path.name:<18} -> {column_name(feature)}")

    # ---- Report ----
    value_cols = [column_name(f) for f in RASTERS]
    print("\nROWS: landslide %s, stable %s" % (f"{(points[config.TARGET] == 1).sum():,}", f"{(points[config.TARGET] == 0).sum():,}"))
    print("\nMISSING VALUES (NoData at the point), by class")
    miss = points.groupby(config.TARGET)[value_cols].apply(lambda t: t.isna().sum()).T
    miss.columns = ["stable", "landslide"]
    print(miss[(miss.sum(axis=1) > 0)].to_string() if miss.values.sum() else "  none")

    water = points["lulc"] == WATER_CODE
    active = [column_name(f) for f in RASTERS if f not in config.DROPPED_COLUMNS]
    problem = water | points[active].isna().any(axis=1)
    print(f"\nPROBLEM ROWS (on WorldCover water, or NoData in a factor the models use): {problem.sum()}"
          f" (landslide {int((problem & (points[config.TARGET] == 1)).sum())},"
          f" stable {int((problem & (points[config.TARGET] == 0)).sum())})")
    if problem.any():
        districts = gpd.read_file(config.DISTRICT_BOUNDARIES).to_crs(config.PROJECT_CRS)
        joined = gpd.sjoin(points.loc[problem, ["point_id", "geometry"]], districts[["district", "geometry"]],
                           predicate="intersects", how="left")
        joined = joined[~joined.index.duplicated()]
        state = gpd.read_file(config.STATE_BOUNDARY).to_crs(config.PROJECT_CRS).geometry.union_all()
        edge = points.loc[problem].geometry.distance(state.boundary)
        print(f"  {'point_id':<12}{'class':>6}{'x':>11}{'y':>12}  {'district':<18}{'edge m':>7}  reason")
        for i in points.index[problem]:
            r = points.loc[i]
            reasons = (["water (lulc 80)"] if water[i] else []) + \
                      [f"{c} NoData" for c in active if pd.isna(r[c])]
            dist = joined.loc[i, "district"] if isinstance(joined.loc[i, "district"], str) else "(between polygons)"
            print(f"  {r['point_id']:<12}{r[config.TARGET]:>6}{r['x']:>11,.0f}{r['y']:>12,.0f}  {dist:<18}"
                  f"{edge[i]:>7,.0f}  {', '.join(reasons)}")

    print("\nRANGES at the points (min / median / max), with check_layers' expected bounds")
    print(f"  {'column':<14}{'min':>11}{'median':>11}{'max':>11}   expected")
    raster_of = {column_name(f): n for f, n in RASTERS.items()}
    out_of_range = []
    for col in value_cols:
        s = points[col].dropna()
        low, high, _ = EXPECTED[raster_of[col]]
        flag = "" if s.between(low, high).all() else "  <-- OUTSIDE"
        if flag:
            out_of_range.append(col)
        print(f"  {col:<14}{s.min():>11,.2f}{s.median():>11,.2f}{s.max():>11,.2f}   {low:,} to {high:,}{flag}")
    lulc_codes = points["lulc"].dropna().astype(int).value_counts().sort_index()
    print("  lulc codes:", lulc_codes.to_dict())
    print("  soil codes:", points["soil"].dropna().astype(int).value_counts().sort_index().to_dict())
    if out_of_range:
        raise SystemExit(f"Values outside the expected range in: {out_of_range}")

    ALL_POINTS.unlink(missing_ok=True)
    points.to_file(ALL_POINTS, layer="all_points", driver="GPKG")
    points.drop(columns="geometry").to_csv(RAW_CSV, index=False)
    print(f"\nWrote {ALL_POINTS} and {RAW_CSV} ({len(points):,} rows, columns {list(points.drop(columns='geometry').columns)})")
    print("Next: python -m src.label_categories data/processed/dataset_raw.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
