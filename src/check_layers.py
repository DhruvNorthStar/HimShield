"""
Check the derived rasters from Steps 2b and 2c against dem.tif.

    python -m src.check_layers

Every factor raster must sit on exactly the same grid as dem.tif. If one is shifted
by even a single cell, "Sample raster values" in Step 2f still returns numbers, and
they belong to the wrong place on the ground. Nothing later warns you. This is the
cheapest way to catch it.

It also checks that values are physically possible, which catches the classic
mistakes: slope computed on a latitude/longitude grid (maxes out near 0.5),
distances left in pixels instead of metres, and aspect missing the -1 flat rule.
"""
import sys

import numpy as np

from src import config

# name -> (expected min, expected max, note shown when the range looks wrong)
EXPECTED = {
    "dem": (0, 9000, "elevation in metres"),
    "slope": (0, 90, "degrees. A maximum near 0.5 means the slope was computed on a lat/long grid"),
    "aspect": (-1, 360, "compass degrees, -1 on flat ground"),
    "curvature": (-100, 100, "1/100 m. Values near 0.0001 mean the x100 step was skipped"),
    "rainfall": (0, 10000, "mm/year"),
    "dist_roads": (0, 200000, "metres. Small whole numbers mean proximity ran in pixel units"),
    "dist_streams": (0, 200000, "metres. Small whole numbers mean proximity ran in pixel units"),
    "dist_faults": (0, 200000, "metres. Small whole numbers mean proximity ran in pixel units"),
    "lulc": (0, 255, "class codes"),
    "soil": (0, 255, "class codes"),
}


def main() -> int:
    import rasterio

    reference_path = config.PROCESSED_DIR / "dem.tif"
    if not reference_path.exists():
        stray = list(config.PROCESSED_DIR.glob("*.tif.vrt"))
        if stray:
            raise SystemExit(
                f"{reference_path} not found, but {stray[0].name} exists. "
                "That is a pointer file, not a raster: the Save dialog was left on VRT. Reading it walks "
                "back through the original tiles every time, which makes GRASS crawl. "
                "Convert it once with Raster > Conversion > Translate, output type GeoTIFF, saved as dem.tif.")
        raise SystemExit(f"{reference_path} not found. Finish Step 2a first.")

    with rasterio.open(reference_path) as ref:
        ref_shape, ref_transform, ref_crs = (ref.height, ref.width), ref.transform, ref.crs
    print(f"Reference grid from dem.tif: {ref_shape[1]:,} x {ref_shape[0]:,} cells, "
          f"{ref_transform.a:g} m, {ref_crs}\n")

    problems, missing = [], []
    print(f"{'layer':<14} {'grid':>18} {'CRS':>12} {'min':>10} {'max':>10} {'nodata %':>9}  aligned")
    for name, (low, high, note) in EXPECTED.items():
        path = config.PROCESSED_DIR / f"{name}.tif"
        if not path.exists():
            missing.append(name)
            continue
        with rasterio.open(path) as src:
            data = src.read(1, masked=True)
            aligned = (src.height, src.width) == ref_shape and src.crs == ref_crs and \
                      all(abs(a - b) < 1e-6 for a, b in zip(src.transform[:6], ref_transform[:6]))
            lo, hi = float(data.min()), float(data.max())
            nodata_pct = 100 * float(np.ma.count_masked(data)) / data.size
            print(f"{name:<14} {src.width:>8,}x{src.height:<8,} {str(src.crs.to_epsg()):>12} "
                  f"{lo:>10,.2f} {hi:>10,.2f} {nodata_pct:>8.1f}%  {'yes' if aligned else 'NO'}")

            if not aligned:
                problems.append(f"{name}.tif is not on the dem.tif grid. Redo it with the extent set to "
                                f"'Calculate from layer > dem' and the same 30 m resolution.")
            if lo < low or hi > high:
                problems.append(f"{name}.tif ranges {lo:,.2f} to {hi:,.2f}, outside {low} to {high}: {note}")
            if nodata_pct > 60:
                problems.append(f"{name}.tif is {nodata_pct:.0f}% NoData. Check the clip and the source coverage.")
            # A range check alone passes a raster that is 0 everywhere, because 0 is a legal distance.
            if lo == hi:
                problems.append(f"{name}.tif holds one value ({lo:,.2f}) in every cell, so it carries no "
                                f"information for the models.")
            if name.startswith("dist_"):
                zero_share = float((data == 0).sum()) / max(int(data.count()), 1)
                if zero_share > 0.5:
                    problems.append(
                        f"{name}.tif is 0 on {100 * zero_share:.0f}% of cells, so almost everything counts as "
                        f"a target. Proximity treated NoData as a feature: set 'target pixel values' to 1 on "
                        f"the binary input and rerun (Step 2c, Parts 5 and 6).")

    if "aspect" in EXPECTED and (config.PROCESSED_DIR / "aspect.tif").exists():
        with rasterio.open(config.PROCESSED_DIR / "aspect.tif") as src:
            flat = int((src.read(1) == -1).sum())
        print(f"\naspect: {flat:,} cells marked flat (-1)")
        if flat == 0:
            problems.append("aspect.tif has no -1 cells. The flat-ground rule was not applied; "
                            "see Step 2b in docs/02_qgis_processing.md.")

    if missing:
        print(f"\nNot built yet: {', '.join(missing)}")

    print()
    if problems:
        print("PROBLEMS")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("Every layer present is on the dem.tif grid with sensible values.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
