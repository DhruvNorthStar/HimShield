"""
Step 2d: turn the GSI landslide inventory into the cleaned training points.

    python -m src.clean_gsi                       writes data/shapefiles/landslides.gpkg
    python -m src.clean_gsi --out other.gpkg      writes somewhere else (for a rehearsal)

Rules, decided 16 September 2026 after inspecting the file (reasons in docs/decisions.md):
1. Spatial clip to the state boundary, not the STATE text field. Both counts are printed.
2. Points sharing one coordinate:
   - every attribute identical apart from the ids -> the same landslide entered twice, keep one;
   - attributes differ -> different landslides placed at one shared coordinate. That point cannot be
     where all of them are (the largest group holds 19 slides from 4 toposheets), so drop them all.
3. Longitude or latitude written with 0 or 1 decimal places (about 100 km or 10 km precision): drop. At a
   30 m grid such a point samples the wrong slope. Two decimals (about 1 km) are kept and reported as a
   limitation.
Only an id and landslide = 1 are written: the inventory's other fields (GEOLOGY, LANDUSE_LA, ...) exist
at landslide points only and would leak the class.
"""
import argparse
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

from src import config

GSI_ZIP = config.RAW_LANDSLIDE_DIR / "GSI_Landslide_Inventory.shp.zip"
GSI_LAYER = "GSI_Landslide_Inventory.shp"
OUTPUT = config.SHAPEFILE_DIR / "landslides.gpkg"
MIN_DECIMALS = 2
ID_FIELDS = ["OBJECTID", "SLIDE_NO"]
GRID_ORIGIN = (170670, 3481770)  # top-left corner of the dem.tif grid, for the shared-cell count


def decimals(value: float) -> int:
    """Decimal places as stored: 78.35 -> 2, 78.3508 -> 4."""
    text = repr(float(value))
    return len(text.split(".")[1].rstrip("0")) if "." in text else 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--out", type=Path, default=OUTPUT)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="ascii", errors="backslashreplace")  # GSI text fields are not ASCII

    raw = gpd.read_file(f"zip://{GSI_ZIP.as_posix()}!{GSI_LAYER}")
    print(f"GSI inventory: {len(raw):,} points, all India")
    state = gpd.read_file(config.STATE_BOUNDARY)
    districts = gpd.read_file(config.DISTRICT_BOUNDARIES)
    boundary = state.to_crs(config.PROJECT_CRS).geometry.union_all()

    # 1. Spatial clip, with the STATE field count alongside for the report
    points = raw.to_crs(config.PROJECT_CRS)
    inside = points.geometry.intersects(boundary)
    by_field = raw["STATE"].astype(str).str.strip().str.lower() == "uttarakhand"
    print(f"\n1. Inside the state boundary (spatial): {inside.sum():,}")
    print(f"   STATE == Uttarakhand (text field):  {by_field.sum():,}"
          f"  [both {(inside & by_field).sum():,}, spatial only {(inside & ~by_field).sum():,},"
          f" field only {(~inside & by_field).sum():,}]")
    sel = points[inside].copy()
    lonlat = raw.loc[sel.index].geometry
    sel["_lon"], sel["_lat"] = lonlat.x.values, lonlat.y.values

    # 2. Shared coordinates, tested on the original longitude/latitude
    attributes = [c for c in raw.columns if c not in ["geometry", *ID_FIELDS]]
    keep = pd.Series(True, index=sel.index)
    same_slide = shared_location = 0
    shared_rows = same_rows = 0
    for _, group in sel.groupby(["_lon", "_lat"]):
        if len(group) == 1:
            continue
        if len(group[attributes].astype(str).drop_duplicates()) == 1:
            same_slide += 1
            same_rows += len(group) - 1
            keep[group.index[1:]] = False
        else:
            shared_location += 1
            shared_rows += len(group)
            keep[group.index] = False
    print(f"\n2. Same landslide entered twice: {same_slide} groups, {same_rows} extra rows removed (one kept each)")
    print(f"   Different landslides at one coordinate: {shared_location} groups, all {shared_rows} rows removed")

    # 3. Coordinate precision, longitude first, then latitude
    lon_dec, lat_dec = sel["_lon"].map(decimals), sel["_lat"].map(decimals)
    coarse_lon = lon_dec < MIN_DECIMALS
    print(f"\n3. Longitude with 0 or 1 decimals: {coarse_lon.sum()} in the state, "
          f"{(coarse_lon & keep).sum()} of them not already removed in step 2"
          f" (0 decimals: {(coarse_lon & keep & (lon_dec == 0)).sum()}, 1 decimal: {(coarse_lon & keep & (lon_dec == 1)).sum()})")
    keep &= ~coarse_lon
    coarse_lat = lat_dec < MIN_DECIMALS
    print(f"4. Latitude with 0 or 1 decimals: {coarse_lat.sum()} in the state, "
          f"{(coarse_lat & keep).sum()} of them not already removed above"
          f" (0 decimals: {(coarse_lat & keep & (lat_dec == 0)).sum()}, 1 decimal: {(coarse_lat & keep & (lat_dec == 1)).sum()})")
    keep &= ~coarse_lat
    clean = sel[keep]

    print(f"   Kept with a 2-decimal longitude (about 1 km, limitation): {int((lon_dec[keep] == 2).sum())}")
    print(f"   Kept with a 2-decimal latitude (about 1 km, limitation): {int((lat_dec[keep] == 2).sum())}")
    print(f"   Kept with either at 2 decimals: {int(((lon_dec[keep] == 2) | (lat_dec[keep] == 2)).sum())}")

    cells = ((clean.geometry.x - GRID_ORIGIN[0]) // config.DEM_RESOLUTION_M).astype(int).astype(str) + "_" + \
            ((GRID_ORIGIN[1] - clean.geometry.y) // config.DEM_RESOLUTION_M).astype(int).astype(str)
    print(f"   Points sharing a 30 m cell with an earlier point (kept, for information): {cells.duplicated().sum()}")

    joined = gpd.sjoin(clean[["geometry"]], districts.to_crs(config.PROJECT_CRS)[["district", "geometry"]],
                       predicate="intersects", how="left")
    joined = joined[~joined.index.duplicated(keep="first")]
    print(f"\nFINAL: {len(clean):,} landslide points "
          f"(removed {len(sel) - len(clean):,} of {len(sel):,} inside the state)")
    for name, n in joined["district"].fillna("(between district polygons)").value_counts().items():
        print(f"  {name:<28} {n:>5,}")

    out = gpd.GeoDataFrame(
        {"gsi_objectid": clean["OBJECTID"].values, "slide_no": clean["SLIDE_NO"].values, config.TARGET: 1},
        geometry=clean.geometry.values, crs=config.PROJECT_CRS,
    )
    out[config.TARGET] = out[config.TARGET].astype("int32")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if args.out.exists():
        args.out.unlink()
    out.to_file(args.out, layer="landslides", driver="GPKG")
    back = gpd.read_file(args.out)
    assert len(back) == len(clean) and back["gsi_objectid"].is_unique and set(back[config.TARGET]) == {1}
    print(f"\nWrote {args.out} ({len(back):,} rows, {back.crs.to_string()})")


if __name__ == "__main__":
    main()
