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

# ---------------------------------------------------------------------------
# Which dataset the pipeline runs on
# ---------------------------------------------------------------------------
# Stays "synthetic" until the real QGIS export (Step 2g) exists. Then change
# DEFAULT_DATA_SOURCE to "real" in one commit so all three of us switch together.
#
# To override for a single run without editing this file (PowerShell):
#     $env:LSM_DATA_SOURCE = "real"
DEFAULT_DATA_SOURCE = "synthetic"
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

SCHEMA_COLUMNS = [
    "landslide", "slope", "aspect", "elevation", "curvature", "rainfall",
    "soil_type", "lithology", "lulc", "dist_roads", "dist_streams", "dist_faults",
]
NUMERIC_FEATURES = [
    "slope", "aspect", "elevation", "curvature", "rainfall",
    "dist_roads", "dist_streams", "dist_faults",
]
CATEGORICAL_FEATURES = ["soil_type", "lithology", "lulc"]

FEATURE_UNITS = {
    "slope": "degrees",
    "aspect": "degrees from north (-1 = flat)",
    "elevation": "m above sea level",
    "curvature": "1/100 m (negative = concave)",
    "rainfall": "mm/year (mean annual)",
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
DROPPED_COLUMNS: dict[str, str] = {}

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
PRIMARY_CV_METRIC = "roc_auc"  # threshold-free, so it is not fooled by class imbalance

# ---------------------------------------------------------------------------
# Phase 2 exit artifacts. Phase 3 loads these by name. Do not rename.
# ---------------------------------------------------------------------------
SVM_MODEL_PATH = MODELS_DIR / "svm_model.pkl"
RF_MODEL_PATH = MODELS_DIR / "rf_model.pkl"
SCALER_PATH = MODELS_DIR / "scaler.pkl"
FEATURE_NAMES_PATH = MODELS_DIR / "feature_names.json"  # ordered, post-VIF. The contract between phases.
METADATA_PATH = MODELS_DIR / "metadata.json"

# ---------------------------------------------------------------------------
# Step 9: small-area demo map
# ---------------------------------------------------------------------------
DEMO_DISTRICT = "Rudraprayag"
DEMO_MAP_HTML = OUTPUTS_DIR / "demo_map_rudraprayag.html"
RISK_ZONES = ["Very Low", "Low", "Moderate", "High", "Very High"]
