"""
Turn the QGIS export into data/processed/dataset.csv with the exact project schema.

    python -m src.label_categories data/processed/dataset_raw.csv

QGIS leaves three things that do not match the schema:
1. "Sample raster values" appends the band number, so columns arrive as slope1, aspect1, ...
2. Categorical rasters carry integer codes (ESA WorldCover, SoilGrids WRB), not class names.
3. NoData arrives as -9999 rather than an empty cell.

This script fixes all three, checks the result against src/config.py, prints a report and
writes the clean CSV. It never silently drops a column: anything unexpected is reported.
"""
import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from src import config

NODATA_VALUES = (-9999, -9999.0, -3.4028234663852886e38)

# ESA WorldCover v200 class codes (the Step 1 fallback for LULC).
WORLDCOVER_CLASSES = {
    10: "Tree cover", 20: "Shrubland", 30: "Grassland", 40: "Cropland", 50: "Built-up",
    60: "Bare/sparse vegetation", 70: "Snow and ice", 80: "Permanent water bodies",
    90: "Herbaceous wetland", 95: "Mangroves", 100: "Moss and lichen",
}
# SoilGrids WRB codes come from the legend file downloaded next to the raster.
SOIL_LEGEND_PATH = config.RAW_SOIL_DIR / "soilgrids_wrb_legend.json"


# SoilGrids writes 0 where it makes no prediction, and 0 is also the legend code for Acrisols.
# Tested on this project's clip (14 September 2026): code-0 cells cover 11.3 percent of Uttarakhand,
# with a median elevation of 5,224 m and 89 percent of them above 4,500 m, against 6.9 percent of all
# other cells. Acrisols are warm, humid lowland soils, so these cells are glaciers and bare rock.
# Labelling them Acrisols would plant a fake soil class that only exists high in the mountains, and
# treating them as missing would let Step 4 fill them with the most common soil. Both are wrong.
SOIL_FILL_CODE = 0
SOIL_FILL_LABEL = "No soil (rock or ice)"


def load_soil_legend() -> dict[int, str]:
    if not SOIL_LEGEND_PATH.exists():
        return {}
    raw = json.loads(SOIL_LEGEND_PATH.read_text(encoding="utf-8"))
    legend = {int(k): v for k, v in raw.items() if k.lstrip("-").isdigit()}
    legend[SOIL_FILL_CODE] = SOIL_FILL_LABEL
    return legend


def normalise_columns(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, str]]:
    """Match QGIS column names (slope1, SLOPE_1, lulc_1, ...) to the schema names."""
    wanted = [*config.SCHEMA_COLUMNS, "soil", "lulc"]
    renames: dict[str, str] = {}
    for column in df.columns:
        key = re.sub(r"[^a-z0-9]", "", column.lower())
        key = re.sub(r"1$", "", key)  # drop the band number QGIS appends
        for target in wanted:
            if key == re.sub(r"[^a-z0-9]", "", target.lower()):
                renames[column] = target
                break
    return df.rename(columns=renames), renames


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean the QGIS export into dataset.csv")
    parser.add_argument("csv", type=Path, help="CSV exported from QGIS (all_points)")
    parser.add_argument("--lithology-field", default=None,
                        help="name of the rock-type column if it is not already 'lithology'")
    parser.add_argument("--out", type=Path, default=config.REAL_DATASET_CSV)
    args = parser.parse_args()

    if not args.csv.exists():
        raise SystemExit(f"Not found: {args.csv}")

    df = pd.read_csv(args.csv)
    print(f"Read {len(df):,} rows, {len(df.columns)} columns from {args.csv}")

    if args.lithology_field:
        df = df.rename(columns={args.lithology_field: "lithology"})
    df, renames = normalise_columns(df)
    changed = {k: v for k, v in renames.items() if k != v}
    if changed:
        print("Renamed: " + ", ".join(f"{k} -> {v}" for k, v in changed.items()))

    # NoData -> missing, before any mapping, so -9999 never becomes a soil class.
    numeric = df.select_dtypes(include="number").columns
    df[numeric] = df[numeric].replace(list(NODATA_VALUES), np.nan)

    # Categorical codes -> class names.
    if "lulc" in df and pd.api.types.is_numeric_dtype(df["lulc"]):
        unknown = sorted(set(df["lulc"].dropna().astype(int)) - set(WORLDCOVER_CLASSES))
        if unknown:
            print(f"WARNING: land cover codes not in the WorldCover legend: {unknown}. "
                  f"If you used Bhuvan LULC, map those codes by hand.")
        df["lulc"] = df["lulc"].dropna().astype(int).map(WORLDCOVER_CLASSES).reindex(df.index)

    if "soil" in df.columns:
        legend = load_soil_legend()
        if pd.api.types.is_numeric_dtype(df["soil"]) and legend:
            df["soil"] = df["soil"].dropna().astype(int).map(legend).reindex(df.index)
        elif pd.api.types.is_numeric_dtype(df["soil"]):
            print(f"WARNING: {SOIL_LEGEND_PATH} missing, leaving soil codes as numbers.")
        df = df.rename(columns={"soil": "soil_type"})

    # Flat ground: aspect is undefined there, and the schema records it as -1.
    if {"aspect", "slope"} <= set(df.columns):
        flat = df["aspect"].isna() & (df["slope"] < 1)
        df.loc[flat, "aspect"] = -1
        if flat.any():
            print(f"Set aspect = -1 on {flat.sum():,} flat cells")

    expected = config.expected_csv_columns()
    missing = [c for c in expected if c not in df.columns]
    extra = [c for c in df.columns if c not in expected]
    if missing:
        raise SystemExit(
            f"Missing required column(s): {missing}\n"
            f"Columns present: {sorted(df.columns)}\n"
            f"Either fix the QGIS export, or record the drop in DROPPED_COLUMNS in src/config.py "
            f"(see docs/02_qgis_processing.md, 'If a column cannot be produced').")
    if extra:
        print(f"Dropping extra column(s) from the export: {extra}")
    df = df[expected]

    df[config.TARGET] = df[config.TARGET].astype(int)
    bad = set(df[config.TARGET].unique()) - {0, 1}
    if bad:
        raise SystemExit(f"{config.TARGET} must be 0 or 1, found {bad}")

    counts = df[config.TARGET].value_counts().sort_index()
    positives, negatives = int(counts.get(1, 0)), int(counts.get(0, 0))
    print(f"\nlandslide=1: {positives:,}   landslide=0: {negatives:,}   "
          f"ratio 1:{negatives / max(positives, 1):.2f} (config says 1:{config.NEG_TO_POS_RATIO})")

    missing_report = df.isna().sum()
    missing_report = missing_report[missing_report > 0]
    if len(missing_report):
        print("\nMissing values per column:")
        print((missing_report.to_frame("missing").assign(percent=lambda t: (100 * t["missing"] / len(df)).round(2))
               ).to_string())
    else:
        print("\nNo missing values.")

    print("\nRanges:")
    print(df[config.active_numeric_features()].describe().loc[["min", "max"]].T.round(2).to_string())

    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False)
    print(f"\nWrote {len(df):,} rows to {args.out}")
    print("Next: set DEFAULT_DATA_SOURCE = \"real\" in src/config.py, then rerun the pipeline.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
