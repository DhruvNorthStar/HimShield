"""
Project configuration. Every path and constant lives here.

Team rule: no script, notebook or dashboard hard-codes a path, a column name,
a random seed or a hyperparameter grid. Import it from this file, so a change
is made once and every step picks it up.

Usage (always run from the repo root):
    from src import config
    df = pd.read_csv(config.DATASET_CSV)
"""
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"                # portal downloads, never committed
PROCESSED_DIR = DATA_DIR / "processed"    # extracted CSVs
SHAPEFILE_DIR = DATA_DIR / "shapefiles"   # boundary, roads, faults, inventory
MODELS_DIR = ROOT / "models"              # never committed
OUTPUTS_DIR = ROOT / "outputs"
FIGURES_DIR = OUTPUTS_DIR / "figures"
NOTEBOOKS_DIR = ROOT / "notebooks"

# Raw downloads, one folder per factor (Step 1). See docs/01_data_sourcing.md.
RAW_DEM_DIR = RAW_DIR / "dem"                # SRTM or Copernicus 1-degree tiles
RAW_RAINFALL_DIR = RAW_DIR / "rainfall"      # IMD yearly files or CHIRPS annual GeoTIFFs
RAW_LULC_DIR = RAW_DIR / "lulc"              # Bhuvan LULC or ESA WorldCover tiles
RAW_SOIL_DIR = RAW_DIR / "soil"              # SoilGrids WRB or HWSD v2
RAW_GEOLOGY_DIR = RAW_DIR / "geology"        # GSI lithology polygons and fault lines
RAW_LANDSLIDE_DIR = RAW_DIR / "landslides"   # GSI inventory (or fallback catalogue)
RAW_OSM_DIR = RAW_DIR / "osm"                # OpenStreetMap extract for roads
RAW_BOUNDARY_DIR = RAW_DIR / "boundary"      # administrative boundaries as downloaded

# Cleaned vector layers produced in QGIS (Step 2), all in PROJECT_CRS
STATE_BOUNDARY = SHAPEFILE_DIR / "uttarakhand_boundary.gpkg"
DISTRICT_BOUNDARIES = SHAPEFILE_DIR / "uttarakhand_districts.gpkg"

# ---------------------------------------------------------------------------
# Which dataset the pipeline runs on
# ---------------------------------------------------------------------------
# Stays "synthetic" until the real QGIS export (Step 2g) exists. Then change
# DEFAULT_DATA_SOURCE to "real" in one commit so all three of us switch together.
#
# To override for a single run without editing this file (PowerShell):
#     $env:LSM_DATA_SOURCE = "real"
DEFAULT_DATA_SOURCE = "real"
DATA_SOURCE = os.environ.get("LSM_DATA_SOURCE", DEFAULT_DATA_SOURCE).strip().lower()
if DATA_SOURCE not in ("synthetic", "real"):
    raise ValueError(f"LSM_DATA_SOURCE must be 'synthetic' or 'real', got {DATA_SOURCE!r}")
IS_SYNTHETIC = DATA_SOURCE == "synthetic"

REAL_DATASET_CSV = PROCESSED_DIR / "dataset.csv"  # Phase 2 exit artifact
SYNTHETIC_DATASET_CSV = PROCESSED_DIR / "dataset_synthetic.csv"
DATASET_CSV = SYNTHETIC_DATASET_CSV if IS_SYNTHETIC else REAL_DATASET_CSV

# Stamped on every figure and printed by every script when running on synthetic data.
SYNTHETIC_LABEL = "SYNTHETIC DATA - NOT REAL"


def data_source_banner() -> str:
    """One-line banner each script prints first, so nobody mistakes which data a result came from."""
    if IS_SYNTHETIC:
        return f"*** {SYNTHETIC_LABEL} *** ({SYNTHETIC_DATASET_CSV.name}) Results are for pipeline testing only."
    return f"Data source: REAL ({REAL_DATASET_CSV.name})"


# ---------------------------------------------------------------------------
# CSV schema: the contract between the QGIS work and every Python script
# ---------------------------------------------------------------------------
TARGET = "landslide"  # 1 = GSI landslide location, 0 = sampled stable terrain

# twi added 14 September 2026. Measured on the real rasters before adding it: whole-state rank
# correlation with slope -0.51 and VIF 1.64, so it carries new information. TRI was measured and
# left out: rank correlation with slope 0.993, VIF 21.2. See docs/literature_review.md, section 2.3.
#
# ndvi added 16 September 2026. Source: Sentinel-2 L2A (COPERNICUS/S2_SR_HARMONIZED) in Google Earth
# Engine, median of scenes 2023-10-01 to 2023-11-30 with CLOUDY_PIXEL_PERCENTAGE < 15, exported at 30 m,
# bilinear to the dem.tif grid. Measured before adding it: VIF 5.11 on the 15,189 training points and 7.40
# on a whole-state grid sample, both under VIF_THRESHOLD. It overlaps land cover (R2 0.79 at the points,
# 0.84 on the grid), which the report states as a limitation. See docs/decisions.md.
SCHEMA_COLUMNS = [
    "landslide", "slope", "aspect", "elevation", "curvature", "twi", "rainfall", "ndvi",
    "soil_type", "lithology", "lulc", "dist_roads", "dist_streams", "dist_faults",
]
NUMERIC_FEATURES = [
    "slope", "aspect", "elevation", "curvature", "twi", "rainfall", "ndvi",
    "dist_roads", "dist_streams", "dist_faults",
]
CATEGORICAL_FEATURES = ["soil_type", "lithology", "lulc"]

FEATURE_UNITS = {
    "slope": "degrees",
    "aspect": "degrees from north (-1 = flat)",
    "elevation": "m above sea level",
    "curvature": "1/100 m (negative = concave)",
    "twi": "ln(a / tan slope), higher = wetter",
    "rainfall": "mm/year (mean annual)",
    "ndvi": "unitless (-1 to 1)",
    "dist_roads": "m",
    "dist_streams": "m",
    "dist_faults": "m",
    "soil_type": "class name",
    "lithology": "class name",
    "lulc": "class name",
}

# If a column genuinely cannot be produced from real data, record it here with
# the reason, and in the README section "Dropped columns". Every script reads
# this dict, so the drop is applied consistently in EDA, training, the
# dashboard and the map. Never delete a column in one script only.
#   Example: DROPPED_COLUMNS = {"soil_type": "No soil map at usable resolution"}
DROPPED_COLUMNS: dict[str, str] = {
    "dist_faults": (
        "GEM Global Active Faults holds only 8 faults within 50 km of Uttarakhand and misses the Main "
        "Central Thrust, so every cell in Rudraprayag is 56 to 127 km from a mapped fault. On a "
        "whole-state grid sample it tracks elevation (rank correlation 0.90) and pushed elevation's VIF "
        "to 14.5, so Step 4 would have dropped elevation instead. Dropped 14 September 2026; restore it "
        "if GSI structural lines arrive from Bhukosh."
    ),
    "lithology": (
        "No state-wide geology raster available. GSI geology layer requires Bhukosh access which is "
        "unavailable. Chauhan et al. (2025) used GSI geology via Bhukosh; this study could not access it "
        "within the project timeline. Dropped 16 September 2026; see docs/decisions.md."
    ),
}

assert set(SCHEMA_COLUMNS) == {TARGET, *NUMERIC_FEATURES, *CATEGORICAL_FEATURES}, "schema lists out of sync"
assert set(DROPPED_COLUMNS) <= set(NUMERIC_FEATURES + CATEGORICAL_FEATURES), "can only drop feature columns"


def expected_csv_columns() -> list[str]:
    """Columns the dataset CSV must contain, in schema order, after documented drops."""
    return [c for c in SCHEMA_COLUMNS if c not in DROPPED_COLUMNS]


def active_numeric_features() -> list[str]:
    return [c for c in NUMERIC_FEATURES if c not in DROPPED_COLUMNS]


def active_categorical_features() -> list[str]:
    return [c for c in CATEGORICAL_FEATURES if c not in DROPPED_COLUMNS]


# ---------------------------------------------------------------------------
# Spatial settings (used in QGIS instructions and the Step 9 demo map)
# ---------------------------------------------------------------------------
GEOGRAPHIC_CRS = "EPSG:4326"   # lat/lon, what the portals deliver
PROJECT_CRS = "EPSG:32644"     # WGS 84 / UTM zone 44N, metres. Covers almost all of Uttarakhand.
DEM_RESOLUTION_M = 30          # SRTM 1 arc-second

# Negative (non-landslide) sampling rules, Step 2e
NEG_TO_POS_RATIO = 2           # non-landslide points per landslide point
NEGATIVE_BUFFER_M = 500        # no negative point within this distance of a known landslide

# ---------------------------------------------------------------------------
# Modelling
# ---------------------------------------------------------------------------
RANDOM_STATE = 42              # used everywhere: split, SMOTE, CV shuffling, RF, SVM
TEST_SIZE = 0.30               # stratified 70/30 split
CV_FOLDS = 5                   # StratifiedKFold inside GridSearchCV
VIF_THRESHOLD = 10.0           # drop the worst feature above this, one at a time
# Categorical classes with fewer rows than this are merged into RARE_CLASS_LABEL before one-hot encoding.
# A dummy column holding 3 rows is noise, and in 5-fold CV some folds would see none of them. The rule
# counts rows only, never landslides, so it cannot pick classes by their outcome. Decided 17 Sep 2026.
RARE_CLASS_MIN_ROWS = 50
RARE_CLASS_LABEL = "Other"
SMOTE_SAMPLING_STRATEGY = 1.0  # after SMOTE, minority count = majority count (training set only)
SMOTE_K_NEIGHBORS = 5

# Windows note: n_jobs=-1 spawns worker processes. Every script that trains
# must keep its code under `if __name__ == "__main__":` or Windows will
# re-import the script in each worker and hang or crash.
N_JOBS = -1

SVM_RBF_PARAM_GRID = {
    "C": [0.1, 1, 10, 100],
    "gamma": [1, 0.1, 0.01, 0.001],
}
SVM_LINEAR_PARAM_GRID = {
    "C": [0.1, 1, 10, 100],
}
RF_PARAM_GRID = {
    "n_estimators": [100, 200, 300],
    "max_depth": [None, 10, 20],
    "min_samples_split": [2, 5, 10],
}
# Phase 3 extension (18 September 2026): XGBoost as a third model, same split, same SMOTE-inside-folds pipeline
# and same 5-fold CV on AUC as SVM and RF. Grid fixed here before any XGBoost training, and not changed after
# seeing results. 3 x 3 x 3 x 2 = 54 combinations, 270 fits.
XGB_PARAM_GRID = {
    "n_estimators": [100, 200, 300],
    "max_depth": [3, 5, 7],
    "learning_rate": [0.01, 0.1, 0.3],
    "subsample": [0.8, 1.0],
}
PRIMARY_CV_METRIC = "roc_auc"  # threshold-free, so it is not fooled by class imbalance

# ---------------------------------------------------------------------------
# Phase 2 exit artifacts. Phase 3 loads these by name. Do not rename.
# ---------------------------------------------------------------------------
SVM_MODEL_PATH = MODELS_DIR / "svm_model.pkl"
RF_MODEL_PATH = MODELS_DIR / "rf_model.pkl"
XGB_MODEL_PATH = MODELS_DIR / "xgb_model.pkl"  # Phase 3 extension; optional everywhere Phase 2 reads models
SCALER_PATH = MODELS_DIR / "scaler.pkl"
FEATURE_NAMES_PATH = MODELS_DIR / "feature_names.json"  # ordered, post-VIF. The contract between phases.
METADATA_PATH = MODELS_DIR / "metadata.json"

# ---------------------------------------------------------------------------
# Step 9: small-area demo map
# ---------------------------------------------------------------------------
DEMO_DISTRICT = "Rudraprayag"
DEMO_MAP_HTML = OUTPUTS_DIR / "demo_map_rudraprayag.html"
RISK_ZONES = ["Very Low", "Low", "Moderate", "High", "Very High"]

# Landslide-score cut-offs between the five zones: equal steps of 0.2.
# Why not natural breaks (Jenks) or quantiles, which many papers use: both are computed from
# each map's own scores, so the same score can be "High" on one run and "Moderate" on the next,
# and quantiles force 20 percent of the district into every zone whatever the terrain. Fixed
# breaks mean one thing on every map, in the dashboard, and for SVM and RF alike, so zone areas
# can be compared directly. Revisit once real-data scores exist, and say which rule was used.
RISK_ZONE_BREAKS = [0.2, 0.4, 0.6, 0.8]
assert len(RISK_ZONE_BREAKS) == len(RISK_ZONES) - 1, "one break fewer than zones"


def risk_zone(score: float) -> str:
    """Zone name for one landslide score. A score exactly on a break goes to the higher zone."""
    return RISK_ZONES[sum(score >= b for b in RISK_ZONE_BREAKS)]
