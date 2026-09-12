"""
Check the DEM tiles in data/raw/dem/ before mosaicking them (Step 2a).

    python -m src.check_dem

Catches the mistakes that are cheap to fix now and expensive later: a missing tile
leaves a hole that turns into NULL columns after extraction, a mixed set of SRTM and
Copernicus tiles makes heights jump at the seams, and voids inside a tile become
missing values in the middle of the mountains.

Works with either source:
  SRTM from EarthExplorer     n30_e079_1arc_v3.tif
  Copernicus DEM GLO-30       Copernicus_DSM_COG_10_N30_00_E079_00_DEM.tif
"""
import re
import sys

import numpy as np

from src import config

SRTM_PATTERN = re.compile(r"^([ns])(\d{2})_([ew])(\d{3})_1arc", re.IGNORECASE)
COPERNICUS_PATTERN = re.compile(r"Copernicus_DSM_COG_10_([NS])(\d{2})_00_([EW])(\d{3})_00_DEM", re.IGNORECASE)


def tile_corner(name: str) -> tuple[int, int] | None:
    """South-west corner (lat, lon) from either naming scheme."""
    for pattern in (SRTM_PATTERN, COPERNICUS_PATTERN):
        m = pattern.search(name)
        if m:
            lat = int(m.group(2)) * (1 if m.group(1).lower() == "n" else -1)
            lon = int(m.group(4)) * (1 if m.group(3).lower() == "e" else -1)
            return lat, lon
    return None


def main() -> int:
    import geopandas as gpd
    import rasterio
    from shapely.geometry import box
    from shapely.ops import unary_union

    files = sorted(p for p in config.RAW_DEM_DIR.glob("*.tif") if p.is_file())
    if not files:
        raise SystemExit(f"No .tif files in {config.RAW_DEM_DIR}. See docs/01_data_sourcing.md.")

    sources = {"SRTM": 0, "Copernicus": 0, "unknown": 0}
    present: set[tuple[int, int]] = set()
    problems: list[str] = []

    # Voids only matter where they fall inside Uttarakhand. SRTM has large gaps over
    # Nepal and Tibet in these tiles, and those are none of our business.
    state_geom = None
    if config.STATE_BOUNDARY.exists():
        state_geom = gpd.read_file(config.STATE_BOUNDARY).to_crs(config.GEOGRAPHIC_CRS).union_all()

    print(f"{'file':<46} {'size':>10} {'dtype':>8} {'min m':>7} {'max m':>7} "
          f"{'voids all':>10} {'voids in state':>15}")
    for path in files:
        name = path.name
        sources["SRTM" if SRTM_PATTERN.search(name) else
                "Copernicus" if COPERNICUS_PATTERN.search(name) else "unknown"] += 1
        corner = tile_corner(name)
        if corner:
            present.add(corner)
        with rasterio.open(path) as src:
            band = src.read(1)
            nodata = src.nodata
            void_mask = (band == nodata) if nodata is not None else np.zeros_like(band, dtype=bool)
            void_mask |= band <= -32000  # SRTM voids are -32768 even when nodata is unset
            valid = band[~void_mask]
            inside_pct = None
            if state_geom is not None:
                tile_box = box(*src.bounds)
                if tile_box.intersects(state_geom):
                    from rasterio.features import geometry_mask

                    in_state = ~geometry_mask([state_geom], out_shape=band.shape, transform=src.transform,
                                              invert=False)
                    if in_state.any():
                        inside_pct = 100 * void_mask[in_state].mean()
            shown = f"{inside_pct:>14.2f}%" if inside_pct is not None else "     outside state"
            print(f"{name:<46} {src.width}x{src.height:<4} {str(src.dtypes[0]):>8} "
                  f"{valid.min() if valid.size else 0:>7,.0f} {valid.max() if valid.size else 0:>7,.0f} "
                  f"{100 * void_mask.mean():>9.2f}% {shown}")
            if src.crs is None or src.crs.to_epsg() != 4326:
                problems.append(f"{name}: CRS is {src.crs}, expected EPSG:4326 as downloaded.")
            if inside_pct is not None and inside_pct > 0.5:
                problems.append(f"{name}: {inside_pct:.1f}% of the cells inside Uttarakhand are voids. "
                                f"Fill them (gdal:fillnodata) before computing slope.")
            elif inside_pct is None and void_mask.mean() > 0.01:
                problems.append(f"{name}: {100 * void_mask.mean():.1f}% voids somewhere in the tile. "
                                f"Build the boundary layer to find out whether they fall inside the state.")
            if valid.size and (valid.max() > 9000 or valid.min() < -500):
                problems.append(f"{name}: heights from {valid.min()} to {valid.max()} m look wrong.")

    kinds = [k for k, n in sources.items() if n]
    print(f"\n{len(files)} tile(s): " + ", ".join(f"{sources[k]} {k}" for k in kinds))
    if len([k for k in kinds if k != "unknown"]) > 1:
        problems.append("Mixed DEM sources. SRTM and Copernicus heights differ, so the mosaic will "
                        "have steps at the seams. Use one source only.")

    # Which tiles does the state actually need, and what does a missing one cost?
    if state_geom is not None:
        state = state_geom
        min_lon, min_lat, max_lon, max_lat = state.bounds
        needed = {(lat, lon)
                  for lat in range(int(np.floor(min_lat)), int(np.ceil(max_lat)))
                  for lon in range(int(np.floor(min_lon)), int(np.ceil(max_lon)))
                  if box(lon, lat, lon + 1, lat + 1).intersects(state)}
        missing = sorted(needed - present)
        extra = sorted(present - needed)
        print(f"Tiles needed for the state: {len(needed)}. Present: {len(needed & present)}.")
        if extra:
            print("Not needed (harmless): " + ", ".join(f"n{lat:02d}_e{lon:03d}" for lat, lon in extra))
        if missing:
            covered = unary_union([box(lon, lat, lon + 1, lat + 1) for lat, lon in present])
            gap = gpd.GeoSeries([state.difference(covered)], crs=config.GEOGRAPHIC_CRS).to_crs(config.PROJECT_CRS)
            gap_km2 = float(gap.area.iloc[0]) / 1e6
            state_km2 = float(gpd.GeoSeries([state], crs=config.GEOGRAPHIC_CRS)
                              .to_crs(config.PROJECT_CRS).area.iloc[0]) / 1e6
            print(f"\nMISSING {len(missing)} tile(s): " +
                  ", ".join(f"n{lat:02d}_e{lon:03d}" for lat, lon in missing))
            print(f"They leave {gap_km2:,.0f} km2 uncovered, {100 * gap_km2 / state_km2:.1f}% of the state.")
            districts_path = config.DISTRICT_BOUNDARIES
            if districts_path.exists() and gap_km2 > 0:
                districts = gpd.read_file(districts_path).to_crs(config.GEOGRAPHIC_CRS)
                hit = districts[districts.intersects(state.difference(covered))]["district"].tolist()
                if hit:
                    print("Districts with a hole in them: " + ", ".join(sorted(hit)))
            problems.append("Download the missing tile(s) before mosaicking, or every point in the gap "
                            "gets NULL terrain values.")
    else:
        print(f"\n{config.STATE_BOUNDARY.name} not found, so coverage was not checked. "
              f"Run: python -m src.get_open_data boundary")

    print()
    if problems:
        print("PROBLEMS")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("All checks passed. Ready for the Step 2a mosaic.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
