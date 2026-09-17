"""
Warp the Google Earth Engine NDVI export onto the dem.tif grid.

    python -m src.warp_ndvi                                   writes data/processed/ndvi.tif
    python -m src.warp_ndvi --src other_export.tif --out x.tif --force

The export (docs/02_qgis_processing.md, "NDVI raster"): COPERNICUS/S2_SR_HARMONIZED, median of scenes from
2023-10-01 to 2023-11-30 with CLOUDY_PIXEL_PERCENTAGE < 15, NDVI = (B8 - B4) / (B8 + B4), EPSG:4326 at scale 30 m,
region [77.56, 28.71, 81.06, 31.47]. This script is what was run on 16 September 2026 to install export v3.

Steps:
1. Coverage check first. Exports v1 and v2 each stopped short of the state (28.85 N and 31.30 N), so the
   file's edges are tested against the state boundary and the script stops if any part is uncovered.
2. Bilinear resampling onto the exact dem.tif grid (CRS, transform, width, height): NDVI is a continuous value
   exported at the same 30 m, so nearest neighbour would only add blockiness. Float32, NoData -9999, DEFLATE.
3. Read in 1,024-row windows through a WarpedVRT, so the laptop never holds the whole state in memory.
Then run `python -m src.check_layers`: ndvi must show aligned yes and a range inside -1 to 1.
"""
import argparse
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT
from rasterio.windows import Window
from shapely.geometry import box

from src import config

SOURCE = config.RAW_DIR / "ndvi" / "Uttarakhand_NDVI_2023_v3.tif"
OUTPUT = config.PROCESSED_DIR / "ndvi.tif"
NODATA = -9999.0
ROWS_PER_WINDOW = 1024
DESCRIPTION = ("NDVI (B8-B4)/(B8+B4), Sentinel-2 L2A median 2023-10-01 to 2023-11-30 via Google Earth Engine; "
               "bilinear to the dem.tif grid by src/warp_ndvi.py")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--src", type=Path, default=SOURCE)
    parser.add_argument("--out", type=Path, default=OUTPUT)
    parser.add_argument("--force", action="store_true", help="overwrite an existing output")
    args = parser.parse_args()

    if not args.src.exists():
        raise SystemExit(f"{args.src} not found. Export NDVI from Google Earth Engine first "
                         f"(docs/02_qgis_processing.md, 'NDVI raster').")
    if args.out.exists() and not args.force:
        raise SystemExit(f"{args.out} exists. Pass --force to replace it.")

    # 1. Coverage
    state = gpd.read_file(config.STATE_BOUNDARY)
    with rasterio.open(args.src) as src:
        src_crs, bounds = src.crs, src.bounds
        print(f"Source {args.src.name}: {src.width:,} x {src.height:,}, {src.crs}, "
              f"W {bounds.left:.4f} S {bounds.bottom:.4f} E {bounds.right:.4f} N {bounds.top:.4f}")
    boundary = state.to_crs(src_crs).geometry.union_all()
    uncovered = boundary.difference(box(*bounds))
    uncovered_km2 = gpd.GeoSeries([uncovered], crs=src_crs).to_crs(config.PROJECT_CRS).area.iloc[0] / 1e6
    if uncovered_km2 > 0.01:
        sb = boundary.bounds
        raise SystemExit(f"The export misses {uncovered_km2:,.1f} km2 of the state. State bounds: W {sb[0]:.4f} "
                         f"S {sb[1]:.4f} E {sb[2]:.4f} N {sb[3]:.4f}. Re-export with a region covering them.")
    print("Coverage: the whole state lies inside the export")

    # 2 and 3. Warp in windows onto the dem grid
    with rasterio.open(config.PROCESSED_DIR / "dem.tif") as ref:
        crs, transform, width, height = ref.crs, ref.transform, ref.width, ref.height
    profile = dict(driver="GTiff", dtype="float32", count=1, crs=crs, transform=transform, width=width,
                   height=height, nodata=NODATA, compress="deflate", predictor=3, tiled=True,
                   blockxsize=256, blockysize=256, BIGTIFF="IF_SAFER")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(args.src) as src, \
            WarpedVRT(src, crs=crs, transform=transform, width=width, height=height,
                      resampling=Resampling.bilinear, src_nodata=np.nan, nodata=NODATA, dtype="float32") as vrt, \
            rasterio.open(args.out, "w", **profile) as dst:
        for row in range(0, height, ROWS_PER_WINDOW):
            window = Window(0, row, width, min(ROWS_PER_WINDOW, height - row))
            dst.write(vrt.read(1, window=window), 1, window=window)
        dst.set_band_description(1, "NDVI")
        dst.update_tags(SOURCE=DESCRIPTION)
    print(f"Wrote {args.out} ({args.out.stat().st_size / 2**20:,.0f} MB), {width:,} x {height:,}, 30 m, {crs}")
    print("Next: python -m src.check_layers")
    return 0


if __name__ == "__main__":
    sys.exit(main())
