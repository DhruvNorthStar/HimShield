"""
Build a SYNTHETIC landslide dataset with the exact project CSV schema.

    python -m src.make_synthetic

Output: data/processed/dataset_synthetic.csv (and a README text file next to it)

THIS IS NOT REAL DATA. It exists so the ML pipeline (EDA, preprocessing, SVM,
RF, evaluation, dashboard) can be built and tested while the real GSI / SRTM /
IMD data is still being processed in QGIS. Scripts print a banner and figures
carry a watermark whenever they run on this file. It must never be presented
as a finding about Uttarakhand.

How it is generated, so the values are plausible rather than random noise:

1. A pool of terrain points is drawn from the four physiographic belts of
   Uttarakhand (Terai-Bhabar, Siwalik, Lesser Himalaya, Higher Himalaya).
   Each belt has its own elevation, slope, rainfall, lithology, soil and land
   cover mix, so the factors are correlated the way real terrain is.
2. Rainfall is assigned per coarse grid cell, not per point, imitating the
   0.25 degree IMD grid. Many points share one rainfall value, as they will
   in the real data.
3. A hidden landslide log-odds is computed from the factors using NON-LINEAR
   terms (slope risk peaks near 35 degrees, a mid-elevation band, distance
   decays, a steep-and-wet interaction) plus noise for everything we do not
   measure. This is why an RBF kernel should beat a linear one here.
4. Each pool point then either fails or does not (a coin flip weighted by its
   risk), with the overall failure rate fixed at TARGET_PREVALENCE. Landslide
   points are sampled from the points that failed. Non-landslide points are
   sampled uniformly from points where no landslide occurred, excluding water
   bodies, at config.NEG_TO_POS_RATIO per landslide. This mirrors Step 2e:
   real negatives come from terrain with no recorded landslide, and some of
   that terrain is still risky, which is why no model reaches AUC 1.0.
5. Realistic defects are injected on purpose so the EDA has something to
   catch: aspect = -1 on flat cells (the QGIS convention) and a few percent
   missing values where real rasters have NoData gaps.
"""
import numpy as np
import pandas as pd

from src import config

N_POOL = 60_000       # candidate terrain points
N_POSITIVE = 1_200    # landslide points (an arbitrary size for testing, not the real inventory count)
N_RAIN_CELLS = 70     # roughly the number of 0.25 degree IMD cells over Uttarakhand

# Difficulty knobs. Tuned so test AUC lands in the range published landslide
# studies report (about 0.80-0.95): easy enough to show the pipeline works,
# hard enough that the models do not look magically perfect.
# Quick baseline at these settings (70/30 split, no grid search), measured before TWI was added:
#   linear SVM 0.84, RBF SVM 0.86, RF 0.90 test AUC.
# Do not tune these to favour one model; that would make the comparison dishonest.
SIGNAL_SCALE = 1.0    # multiplies every terrain effect in the hidden log-odds
NOISE_SD = 0.8        # spread of the "everything we do not measure" term
TARGET_PREVALENCE = 0.05  # share of pool points that experience a landslide

BELTS = {
    "terai_bhabar": dict(
        share=0.12, elev=(350, 120), slope_gamma=(1.5, 3.0), rain=(1500, 150),
        road_scale_m=400, fault_scale_m=8000,
        lithology={"Alluvium": 0.85, "Sandstone": 0.15},
        soil={"Fluvisols": 0.60, "Cambisols": 0.40},
        lulc={"Agriculture": 0.55, "Forest": 0.30, "Builtup": 0.10, "Water": 0.05},
    ),
    "siwalik": dict(
        share=0.18, elev=(900, 300), slope_gamma=(5.0, 4.4), rain=(2100, 250),
        road_scale_m=1500, fault_scale_m=2500,
        lithology={"Sandstone": 0.55, "Shale": 0.25, "Conglomerate": 0.20},
        soil={"Cambisols": 0.50, "Regosols": 0.30, "Luvisols": 0.20},
        lulc={"Forest": 0.65, "Agriculture": 0.15, "Scrub": 0.12, "Builtup": 0.04, "Water": 0.04},
    ),
    "lesser_himalaya": dict(
        share=0.45, elev=(1700, 550), slope_gamma=(6.0, 5.0), rain=(1900, 300),
        road_scale_m=1200, fault_scale_m=3000,
        lithology={"Phyllite": 0.25, "Quartzite": 0.20, "Schist": 0.15, "Limestone": 0.15,
                   "Shale": 0.15, "Granite": 0.10},
        soil={"Cambisols": 0.45, "Regosols": 0.25, "Leptosols": 0.20, "Luvisols": 0.10},
        lulc={"Forest": 0.50, "Agriculture": 0.20, "Scrub": 0.15, "Barren": 0.07, "Builtup": 0.04,
              "Grassland": 0.02, "Water": 0.02},
    ),
    "higher_himalaya": dict(
        share=0.25, elev=(3800, 900), slope_gamma=(6.0, 5.7), rain=(1200, 200),
        road_scale_m=6000, fault_scale_m=4500,
        lithology={"Gneiss": 0.45, "Schist": 0.25, "Granite": 0.20, "Quartzite": 0.10},
        soil={"Leptosols": 0.50, "Regosols": 0.20, "Cambisols": 0.15, "Glacier": 0.15},
        lulc={"Snow": 0.30, "Grassland": 0.25, "Barren": 0.25, "Forest": 0.15, "Water": 0.05},
    ),
}

# Effect of each class on the hidden log-odds. Weak, fractured rock and bare
# ground raise risk; massive rock, alluvial plains, forest and snow lower it.
LITHOLOGY_EFFECT = {"Phyllite": 0.8, "Shale": 0.7, "Schist": 0.6, "Conglomerate": 0.4, "Sandstone": 0.3,
                    "Limestone": 0.2, "Gneiss": 0.1, "Quartzite": -0.1, "Granite": -0.4, "Alluvium": -1.0}
LULC_EFFECT = {"Barren": 0.7, "Scrub": 0.5, "Agriculture": 0.4, "Builtup": 0.3, "Grassland": 0.0,
               "Forest": -0.4, "Snow": -1.5, "Water": -2.0}
SOIL_EFFECT = {"Regosols": 0.3, "Leptosols": 0.2, "Luvisols": 0.1, "Cambisols": 0.0,
               "Fluvisols": -0.3, "Glacier": -0.8}

# Typical NDVI per synthetic land-cover class, from the class medians on the real Sentinel-2 layer.
NDVI_BY_LULC = {"Forest": 0.78, "Scrub": 0.69, "Grassland": 0.50, "Agriculture": 0.48, "Builtup": 0.30,
                "Barren": 0.04, "Snow": -0.03, "Water": -0.05}
NDVI_NOISE_SD = 0.15  # chosen so NDVI overlaps land cover as on the real training points: R2 0.78, VIF 5.0 (real 0.79, 5.11)

MISSING_RATES = {"rainfall": 0.005, "soil_type": 0.015, "lithology": 0.010,
                 "twi": 0.002}  # the real layer is NoData on a one-cell rim along the state border


def _pick(rng: np.random.Generator, options: dict[str, float], n: int) -> np.ndarray:
    names = np.array(list(options))
    probs = np.array(list(options.values()), dtype=float)
    return rng.choice(names, size=n, p=probs / probs.sum())


def build_terrain_pool(rng: np.random.Generator) -> pd.DataFrame:
    shares = np.array([b["share"] for b in BELTS.values()])
    belt_idx = rng.choice(len(BELTS), size=N_POOL, p=shares / shares.sum())
    parts = []
    for i, (belt, b) in enumerate(BELTS.items()):
        n = int((belt_idx == i).sum())
        # Coarse rainfall grid: a few cell values per belt, each point takes one of them.
        n_cells = max(4, round(N_RAIN_CELLS * b["share"]))
        cell_values = rng.normal(*b["rain"], size=n_cells).clip(700, 3200)
        slope = rng.gamma(*b["slope_gamma"], size=n).clip(0, 75)
        parts.append(pd.DataFrame({
            "belt": belt,
            "elevation": rng.normal(*b["elev"], size=n).clip(180, 7000),
            "slope": slope,
            "aspect": rng.uniform(0, 360, size=n),
            "curvature": rng.normal(0, 1.0 + slope / 30),
            "rainfall": rng.choice(cell_values, size=n),
            "lithology": _pick(rng, b["lithology"], n),
            "soil_type": _pick(rng, b["soil"], n),
            "lulc": _pick(rng, b["lulc"], n),
            "dist_roads": rng.exponential(b["road_scale_m"], size=n),
            "dist_faults": rng.exponential(b["fault_scale_m"], size=n).clip(0, 40_000),
        }))
    pool = pd.concat(parts, ignore_index=True)

    # Snow, glaciers only exist high up; below that the same ground is bare.
    low = pool["elevation"] < 4000
    pool.loc[low & (pool["lulc"] == "Snow"), "lulc"] = "Barren"
    pool.loc[low & (pool["soil_type"] == "Glacier"), "soil_type"] = "Leptosols"
    # Settlements and farms sit next to roads.
    near_people = pool["lulc"].isin(["Builtup", "Agriculture"])
    pool.loc[near_people, "dist_roads"] *= 0.4
    pool["dist_roads"] = pool["dist_roads"].clip(0, 25_000)
    # Streams run in concave hollows: more concave means closer to a stream.
    pool["dist_streams"] = (rng.exponential(450, size=len(pool)) * np.exp(0.2 * pool["curvature"])).clip(0, 5_000)

    # Topographic wetness index, ln(a / tan slope). It has its own random generator, so adding it
    # (14 September 2026) left every column above exactly as it was. Wetter where ground is gentle,
    # concave and close to a stream, matching the directions measured on the real layer (whole
    # state: rank correlation with slope -0.51, curvature -0.42, distance to streams -0.27).
    twi_rng = np.random.default_rng(config.RANDOM_STATE + 1)
    log_area = (4.5 + 1.5 * np.exp(-pool["dist_streams"] / 200) - 0.35 * pool["curvature"]
                + twi_rng.normal(0, 1.0, size=len(pool)))
    pool["twi"] = (log_area - np.log(np.tan(np.radians(pool["slope"].clip(lower=0.5))))).clip(1.3, 32)

    # NDVI, added 16 September 2026, also with its own generator so every column above is unchanged. It is
    # set mostly by land cover, at the class medians measured on the real Sentinel-2 layer (Tree cover 0.78
    # ... Snow and ice -0.03), falling with elevation and rising with rainfall as measured there (whole-state
    # rank correlation -0.50 and 0.42). It is deliberately left out of hidden_log_odds: land cover already
    # carries the vegetation effect, and adding a term would change which synthetic points are landslides.
    ndvi_rng = np.random.default_rng(config.RANDOM_STATE + 2)
    pool["ndvi"] = (pool["lulc"].map(NDVI_BY_LULC)
                    - 0.00004 * (pool["elevation"] - 1500)
                    + 0.00005 * (pool["rainfall"] - 1500)
                    + ndvi_rng.normal(0, NDVI_NOISE_SD, size=len(pool))).clip(-1, 1)
    return pool


def hidden_log_odds(pool: pd.DataFrame, rng: np.random.Generator) -> np.ndarray:
    slope, elev, rain = pool["slope"], pool["elevation"], pool["rainfall"]
    signal = (
        3.0 * np.exp(-((slope - 35) / 10) ** 2)          # risk peaks on ~35 degree slopes, falls on cliffs
        + 2.0 * np.exp(-((elev - 1600) / 700) ** 2)      # mid-elevation band (low in plains AND high peaks)
        + 1.0 * (rain - 1600) / 500
        + 1.6 * np.exp(-pool["dist_roads"] / 300)        # road cuts undercut slopes
        + 1.0 * np.exp(-pool["dist_streams"] / 250)      # toe erosion by streams
        + 0.35 * ((pool["twi"] - 6) / 3).clip(-1, 2)     # wet ground loses strength, a modest effect
        + 0.9 * np.exp(-pool["dist_faults"] / 1500)      # sheared rock near faults
        - 0.25 * pool["curvature"]                       # concave slopes collect water
        + 0.15 * np.cos(np.radians(pool["aspect"] - 180))
        + 0.6 * ((slope > 25) & (rain > 2000))           # steep AND wet
        + pool["lithology"].map(LITHOLOGY_EFFECT)
        + pool["lulc"].map(LULC_EFFECT)
        + pool["soil_type"].map(SOIL_EFFECT)
    )
    noise = rng.normal(0, NOISE_SD, size=len(pool))      # everything we do not measure
    return (SIGNAL_SCALE * signal + noise).to_numpy()   # intercept is calibrated in sample_points


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-x))


def _calibrate_intercept(z: np.ndarray, prevalence: float) -> float:
    """Find b so that the mean of sigmoid(b + z) equals the target prevalence (bisection)."""
    lo, hi = -50.0, 50.0
    for _ in range(100):
        mid = (lo + hi) / 2
        if _sigmoid(mid + z).mean() > prevalence:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def sample_points(pool: pd.DataFrame, z: np.ndarray, rng: np.random.Generator) -> pd.DataFrame:
    p = _sigmoid(_calibrate_intercept(z, TARGET_PREVALENCE) + z)
    failed = rng.random(len(pool)) < p

    pos_candidates = np.flatnonzero(failed)
    if len(pos_candidates) < N_POSITIVE:
        raise ValueError(f"only {len(pos_candidates)} failures in the pool; raise N_POOL or TARGET_PREVALENCE")
    pos_idx = rng.choice(pos_candidates, size=N_POSITIVE, replace=False)

    not_water = pool["lulc"].to_numpy() != "Water"  # Step 2e: exclude water bodies
    neg_candidates = np.flatnonzero(~failed & not_water)
    neg_idx = rng.choice(neg_candidates, size=N_POSITIVE * config.NEG_TO_POS_RATIO, replace=False)

    df = pd.concat([pool.iloc[pos_idx].assign(landslide=1), pool.iloc[neg_idx].assign(landslide=0)])
    return df.sample(frac=1, random_state=config.RANDOM_STATE).reset_index(drop=True)


def inject_defects(df: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    df = df.copy()
    df.loc[df["slope"] < 1.0, "aspect"] = -1  # QGIS writes -1 where the ground is flat
    for col, rate in MISSING_RATES.items():
        df.loc[rng.random(len(df)) < rate, col] = np.nan
    return df


def tidy(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["landslide"] = df["landslide"].astype(int)
    df["elevation"] = df["elevation"].round(0)
    df["rainfall"] = df["rainfall"].round(1)
    for col in ["slope", "aspect", "dist_roads", "dist_streams", "dist_faults"]:
        df[col] = df[col].round(2)
    df["curvature"] = df["curvature"].round(3)
    df["twi"] = df["twi"].round(3)
    df["ndvi"] = df["ndvi"].round(3)
    return df[config.SCHEMA_COLUMNS]


README_TEXT = f"""SYNTHETIC DATASET - NOT REAL DATA
=================================
File: {config.SYNTHETIC_DATASET_CSV.name}
Generator: src/make_synthetic.py (random seed {config.RANDOM_STATE})

These rows were generated by a simulation, not extracted from GSI, SRTM, IMD
or Bhuvan data. The schema matches the real dataset exactly so the ML
pipeline can be built and demonstrated before the real extraction is ready.

Do not report any metric, map or feature importance from this file as a
result about Uttarakhand. The real dataset is data/processed/dataset.csv.
"""


def main() -> None:
    rng = np.random.default_rng(config.RANDOM_STATE)
    pool = build_terrain_pool(rng)
    z = hidden_log_odds(pool, rng)
    df = tidy(inject_defects(sample_points(pool, z, rng), rng))

    assert list(df.columns) == config.SCHEMA_COLUMNS, "schema drift"
    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(config.SYNTHETIC_DATASET_CSV, index=False)
    config.SYNTHETIC_DATASET_CSV.with_suffix(".README.txt").write_text(README_TEXT, encoding="utf-8")

    counts = df["landslide"].value_counts().sort_index()
    print(f"*** {config.SYNTHETIC_LABEL} ***")
    print(f"Wrote {len(df):,} rows to {config.SYNTHETIC_DATASET_CSV}")
    print(f"  landslide=1: {counts.get(1, 0):,}   landslide=0: {counts.get(0, 0):,}   "
          f"(ratio 1:{counts.get(0, 0) / counts.get(1, 1):.0f})")
    print(f"  flat cells with aspect=-1: {(df['aspect'] == -1).sum():,}")
    missing = df.isna().sum()
    print("  missing values: " + ", ".join(f"{c}={n}" for c, n in missing[missing > 0].items()))


if __name__ == "__main__":
    main()
