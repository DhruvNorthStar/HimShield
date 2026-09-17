# Landslide Susceptibility Mapping for Uttarakhand

A comparative study of Support Vector Machine and Random Forest for predicting landslide-prone terrain in Uttarakhand, India. BCA final-year PBL project.

Given the terrain conditions at a location (slope, aspect, elevation, curvature, topographic wetness, rainfall, vegetation (NDVI), soil, land cover, and distance to roads and streams), the models score how likely that ground is to be landslide-prone. Positive samples are landslides from the Geological Survey of India (GSI) inventory. Negative samples are random points on terrain with no recorded landslide.

> **Data status: REAL.** Phase 2 ran on the GSI inventory on 17 September 2026. `src/config.py` sets `DEFAULT_DATA_SOURCE = "real"`. The synthetic dataset used to build the pipeline is kept for testing (`$env:LSM_DATA_SOURCE = "synthetic"`); nothing from it is a finding about Uttarakhand.

## Results

Held-out test set: 4,551 points (1,513 landslides), 30% of the data, stratified, never resampled and never used for tuning.

| | SVM (RBF) | Random Forest |
|---|---|---|
| **Test AUC** | **0.9404** | **0.9604** |
| 5-fold CV AUC | 0.9427 | 0.9618 |
| Average precision | 0.881 | 0.914 |
| Accuracy / precision / recall / F1 at 0.5 | 0.871 / 0.759 / 0.896 / 0.822 | 0.902 / 0.831 / 0.886 / 0.858 |
| Landslides caught / missed at 0.5 | 1,355 / 158 | 1,341 / 172 |
| False alarms at 0.5 | 430 | 272 |
| Best parameters | C = 100, gamma = 0.01 | 300 trees, max_depth None, min_samples_split 2 |

- **Random Forest ranks better.** RF minus SVM AUC is +0.0199, 95% bootstrap interval (1,000 resamples) +0.0157 to +0.0242, which excludes zero.
- **The RBF kernel helps:** a linear SVM scores 0.9265, so the non-linear kernel adds +0.0139.
- **Random Forest's strongest factors** (impurity / permutation importance): distance to roads 0.314 / +0.143, elevation 0.160 / +0.051, slope 0.117 / +0.042, NDVI 0.099 / +0.018, rainfall 0.058 / +0.008.

### Road-survey bias, measured

GSI surveyed largely along roads: the median distance to a road is 30 m at landslide points and 1,154 m at stable points, and distance to roads has the strongest class separation (point-biserial r = -0.34). Part of what the models learn is therefore "where GSI surveyed". `python -m src.near_road_check` splits the test set at 1 km from a road:

| Test points | Rows (landslides) | SVM AUC (95%) | RF AUC (95%) |
|---|---|---|---|
| All | 4,551 (1,513) | 0.940 (0.934 to 0.947) | 0.960 (0.955 to 0.966) |
| Within 1 km of a road | 2,855 (1,440) | **0.907** (0.896 to 0.918) | **0.934** (0.925 to 0.943) |
| Beyond 1 km | 1,696 (73) | 0.833 (0.774 to 0.886) | 0.952 (0.929 to 0.970) |

Within 1 km, where the classes are nearly balanced and road distance separates them far less, both models lose about 0.03 AUC and Random Forest stays ahead (RF minus SVM +0.027, interval +0.020 to +0.035). Beyond 1 km only 73 landslides remain, so those intervals are wide.

### Comparison with the primary reference

AUCs comparable to Chauhan et al. (2025), with road-survey bias quantified by the near-road check (RF 0.934 within 1 km of roads). The two studies differ in inventory handling, conditioning factors (they had GSI geology, soil moisture and geomorphons) and the train/test split, so this study does not claim higher accuracy. See [docs/literature_review.md](docs/literature_review.md).

### Rudraprayag demo maps

2,145,236 cells at 30 m (1,936 km2), water excluded, fixed zone breaks 0.2 / 0.4 / 0.6 / 0.8.

| Zone | Random Forest | SVM (RBF) |
|---|---|---|
| Very Low | 69.1% | 65.8% |
| Low | 15.6% | 10.0% |
| Moderate | 7.7% | 9.3% |
| High | 4.3% | 9.6% |
| Very High | 3.2% | 5.3% |

Scoring took 25 s for Random Forest and 11 min for SVM. In both maps the higher zones follow the valleys and road network of the southern half of the district.

### Limitations

- **Stable means "no recorded landslide"**, not "cannot fail", and the inventory follows roads (above).
- **Random train/test split:** nearby points fall on both sides, so scores are likely optimistic for an unseen region. A spatial cross-validation check is future work.
- **Lithology is missing:** GSI geology needs Bhukosh access, which was unavailable. Distance to faults was dropped (see below).
- **Best parameters on the edge of the grid** (SVM C = 100, RF 300 trees and min_samples_split 2). The grids were fixed before training and were not widened after seeing the results.
- **Duplicates:** 20 landslide rows share a 30 m cell with another landslide; 8 of these groups have copies in both train and test (at most 8 of 4,551 test rows).
- **NDVI overlaps land cover** (land cover explains R2 0.78 of it at the points). Several classes occur almost only at stable points (Snow and ice 856 / 0, No soil (rock or ice) 1,194 / 1), which makes the classes easier to separate.
- **Rainfall** is a 16-year annual mean at about 5.5 km, not the short bursts that trigger individual landslides.

Every decision behind these numbers, with its measurement, is in [docs/decisions.md](docs/decisions.md).

## Data

| Item | Value |
|---|---|
| Landslide inventory | GSI landslide inventory via the bharatlas.com public geoportal (NDSAP open data), downloaded 15 September 2026. 5,201 points inside the state, **5,063 after cleaning** |
| Stable points | **10,126** (2 per landslide), random inside the state, at least 500 m from every GSI point and from each other, 50 m clear of water, seed 42 |
| Dataset | **15,189 rows**; 20 rows on water dropped and 2 border rows median-filled in preprocessing, **15,169 used** |
| Grid | 30 m, EPSG:32644 (UTM 44N), 11,123 x 10,135 cells, 12 aligned rasters |
| Model inputs | **23** after encoding; VIF dropped none (highest elevation 6.47, NDVI 5.08) |

Sources: Copernicus GLO-30 DEM (slope, aspect, curvature, TWI and streams derived with GRASS), CHIRPS v2.0 rainfall 2009 to 2024, ESA WorldCover 2021, SoilGrids WRB, Sentinel-2 L2A NDVI (median of 1 October to 30 November 2023, Google Earth Engine), OpenStreetMap roads, geoBoundaries. Provenance, licences and processing per file: [docs/data_sources_log.md](docs/data_sources_log.md).

The GSI cleaning removed 2 repeat entries, all 125 rows of 41 groups of different landslides placed at one shared coordinate, and 11 points whose longitude or latitude has 0 or 1 decimal places (about 10 km precision or worse).

## Running the pipeline

Always run from the repo root with the environment active. The first rows need the raw downloads and rasters, which are not in git (see [Setup](#setup-on-windows)).

**One command for the Python half.** Once the base rasters, the GSI zip and the NDVI export exist, `python run_phase2.py` runs `warp_ndvi` through the Rudraprayag map (14 steps) in order, skips steps whose outputs are newer than their inputs, stops at the first failure and prints the results. `python run_phase2.py --dry-run` shows the plan and time estimate without running anything; `--force` reruns everything. Full run about 20 to 35 minutes on the project laptop.

| Step | Command | Output |
|---|---|---|
| Environment check | `python verify_setup.py` | must print READY |
| Open downloads | `python -m src.get_open_data --list` | `data/raw/` |
| DEM tile check | `python -m src.check_dem` | report |
| Raster processing (QGIS / GRASS) | [docs/02_qgis_processing.md](docs/02_qgis_processing.md) | `data/processed/*.tif` |
| Check rasters are aligned | `python -m src.check_layers` | 12 layers, `aligned yes` |
| 2d. Clean the GSI inventory | `python -m src.clean_gsi` | `data/shapefiles/landslides.gpkg` (5,063) |
| 2e. Sample stable points | `python -m src.make_stable_points` | `data/shapefiles/non_landslides.gpkg` (10,126) |
| 2f. Sample rasters at the points | `python -m src.extract_points` | `data/processed/dataset_raw.csv` |
| 2g. Codes to class names, schema check | `python -m src.label_categories data/processed/dataset_raw.csv` | `data/processed/dataset.csv` |
| 3. EDA | `python -m src.eda` (or `notebooks/01_eda.ipynb`) | `outputs/eda_report.txt`, figures |
| 4. Preprocessing | `python -m src.preprocess` | scaler, feature list, split |
| 5. Train SVM | `python -m src.train_svm` | `models/svm_model.pkl` (about 10 min) |
| 6. Train RF | `python -m src.train_rf` | `models/rf_model.pkl` (about 5 min) |
| 7. Evaluate and compare | `python -m src.evaluate` | `outputs/evaluation_report.txt`, figures |
| 7b. Near-road AUC check | `python -m src.near_road_check` | `models/metadata.json` |
| 8. Dashboard | `streamlit run dashboard/app.py` | Overview, Model Comparison, Predict, Rudraprayag Map |
| 9. Rudraprayag map | `python -m src.demo_map` (add `--model svm` for SVM) | `outputs/demo_map_rudraprayag*.html` (needs internet for the basemap) |

Synthetic test data: `python -m src.make_synthetic`, then run any step with `$env:LSM_DATA_SOURCE = "synthetic"`.

## Dataset schema

`data/processed/dataset.csv` has the schema columns below, minus dropped columns, in this order. Every script depends on the names.

| Column | Meaning | Unit / type |
|---|---|---|
| `landslide` | target: 1 = GSI landslide, 0 = stable | int |
| `slope` | slope angle from the DEM | degrees |
| `aspect` | slope direction from the DEM, -1 where flat | degrees from north |
| `elevation` | elevation (Copernicus GLO-30 DEM) | m |
| `curvature` | profile curvature from the DEM | 1/100 m, negative = concave |
| `twi` | topographic wetness index from the DEM (GRASS r.watershed) | ln(a / tan slope), higher = wetter |
| `rainfall` | mean annual rainfall 2009 to 2024 (CHIRPS) | mm/year |
| `ndvi` | vegetation index, Sentinel-2 L2A median of 1 October to 30 November 2023 (Google Earth Engine) | unitless, -1 to 1 |
| `soil_type` | soil class (SoilGrids WRB) | category name |
| `lithology` | rock type (GSI) | **dropped** |
| `lulc` | land use / land cover (ESA WorldCover 2021) | category name |
| `dist_roads` | distance to nearest road (OpenStreetMap) | m |
| `dist_streams` | distance to nearest stream (derived from the DEM) | m |
| `dist_faults` | distance to nearest fault (GEM Global Active Faults) | **dropped** |

Encoding in `src/preprocess.py`: aspect becomes sine and cosine (flat = 0, 0); categories with fewer than 50 rows are merged into "Other" (soil: Chernozems, Podzols, Regosols, Vertisols; land cover: Herbaceous wetland, Shrubland); each category becomes a yes/no column, with the most frequent class (Cambisols, Tree cover) as the reference. The 23 model inputs are listed in `models/feature_names.json`.

All column names, paths, the random seed (42) and hyperparameter grids live in [src/config.py](src/config.py). Nothing else hard-codes them.

### Dropped columns

A column that cannot be used is added to `DROPPED_COLUMNS` in `src/config.py` with the reason, and listed here. Every script reads that setting, so the drop applies everywhere at once.

| Column | Dropped | Reason |
|---|---|---|
| `dist_faults` | 14 September 2026 | The only open fault layer, GEM Global Active Faults, holds 8 faults within 50 km of the state and misses the Main Central Thrust: every cell in Rudraprayag is 56 to 127 km from a mapped fault. On a whole-state grid sample it tracks elevation (rank correlation 0.90) and pushes elevation's VIF to 14.5. Restore it if GSI structural lines arrive from Bhukosh. The raster is still sampled into `dataset_raw.csv`; the models ignore it |
| `lithology` | 16 September 2026 | No state-wide geology raster available. The GSI geology layer requires Bhukosh access, which was unavailable. Chauhan et al. (2025) used GSI geology via Bhukosh; this study could not access it within the project timeline |

## Method in brief

The order in `src/preprocess.py` and the training scripts:

1. Drop the 20 rows on water (they could only be landslides, because stable points avoid water).
2. Missing values: median for numbers, most frequent class for categories (2 rows). This is computed over the whole dataset before the split, a very small leak that the report states.
3. Encoding: rare classes merged, aspect to sine and cosine, one-hot categories.
4. VIF check at threshold 10, dropping the worst one at a time (none dropped).
5. Stratified 70/30 split, seed 42.
6. StandardScaler fitted on the training rows only.
7. 5-fold stratified grid search on ROC AUC, with SMOTE inside each fold on the training folds only: SVM C [0.1, 1, 10, 100] x gamma [1, 0.1, 0.01, 0.001]; RF trees [100, 200, 300] x max_depth [None, 10, 20] x min_samples_split [2, 5, 10].
8. One score on the untouched test set, with a bootstrap interval on the RF minus SVM AUC gap.

## Phase 2 exit artifacts

Phase 3 loads these instead of retraining. Names and formats are fixed. Models, rasters and the real CSVs are not in git.

| File | Contents |
|---|---|
| `models/svm_model.pkl` | trained SVM (best estimator, with probability estimates) |
| `models/rf_model.pkl` | trained Random Forest (best estimator) |
| `models/scaler.pkl` | StandardScaler fitted on the training rows |
| `models/feature_names.json` | the 23 model inputs in order. Prediction must use this order |
| `models/metadata.json` | data source, preprocessing (merged classes, VIF values, split, SMOTE), best parameters, test metrics, near-road check, demo maps |
| `data/processed/dataset.csv` | cleaned dataset before the split (local only) |
| `outputs/evaluation_report.txt`, `outputs/eda_report.txt`, `outputs/figures/*.png` | reports and figures (in git) |

Phase 3 (branch `phase3-preparation`, not merged): SHAP explainability, full-state prediction, a 6-page dashboard. XGBoost is planned for Phase 3 only.

## Setup on Windows

Do this once per laptop. It takes about 15 minutes, most of it downloading.

### 0. Get the code

```
git clone https://github.com/DhruvNorthStar/HimShield.git
cd HimShield
```

This repository holds the code, documentation, the synthetic dataset, the reports and the figures. Raw downloads, derived rasters, the real dataset CSVs and trained models are not in it, because of their size and licences: rebuild them with [docs/01_data_sourcing.md](docs/01_data_sourcing.md), [docs/02_qgis_processing.md](docs/02_qgis_processing.md) and the commands above.

### 1. Install Miniforge

Miniforge is a small conda installer that uses the conda-forge channel by default. Install it with either:

- PowerShell: `winget install CondaForge.Miniforge3`
- or the installer from https://github.com/conda-forge/miniforge/releases (file `Miniforge3-Windows-x86_64.exe`). Install "Just Me", and keep the default path under your user folder.

Then open **Miniforge Prompt** from the Start menu. Use it for every command below. (In a normal PowerShell window, `conda activate` does not work until you run `conda init powershell` once and restart the window.)

### 2. Create the environment

```
cd HimShield
conda env create -f environment.lock.yml
conda activate landslide
python verify_setup.py
```

`environment.lock.yml` holds the exact versions, so every machine gets identical packages. (`environment.yml` is the looser source file it was generated from. Only edit that one when adding a package, then regenerate the lock.)

`verify_setup.py` must end with `READY`. If it prints a FAIL line, it also prints a hint. Fix that before doing anything else.

### 3. Turn on the notebook git filter

```
nbstripout --install
```

Run this once in each clone. It strips outputs from notebooks when you commit, which prevents most notebook merge conflicts. See [CONTRIBUTING.md](CONTRIBUTING.md).

### 4. Point your editor at the environment

- **PyCharm:** Settings > Project > Python Interpreter > Add Interpreter > Conda Environment > Use existing > `landslide`.
- **VS Code:** Ctrl+Shift+P > "Python: Select Interpreter" > pick the one with `landslide` in its path. For notebooks, choose the same kernel in the top right.

QGIS is installed separately (the standalone "QGIS LTR" installer from qgis.org) and is not part of the Python environment.

## Why conda, and what fails on Windows

rasterio and geopandas are thin Python layers over C libraries (GDAL, GEOS, PROJ). The failures people hit on Windows all come from those libraries, not from Python:

| Symptom | Cause | What we do |
|---|---|---|
| `pip install rasterio` tries to compile and fails with "GDAL API version must be specified" or "Microsoft Visual C++ 14.0 is required" | No prebuilt wheel for your Python version (common on 3.13 and 3.14) | Use Python 3.11. The conda env pins it. |
| `ImportError: DLL load failed` | pip and conda copies of GDAL mixed in one env, or a QGIS GDAL on PATH | Install geospatial packages only from conda-forge. Never `pip install` them into the conda env. |
| `pyproj` or `to_crs` errors mentioning `proj.db` | `PROJ_LIB` / `PROJ_DATA` / `GDAL_DATA` set globally by a QGIS, OSGeo4W or PostGIS install | `verify_setup.py` warns about it. Remove the variable in System Properties > Environment Variables. |
| `verify_setup.py` shows an old numpy/pandas "loaded from OUTSIDE this env" | An earlier `pip install --user` left packages in `AppData\Roaming\Python\Python311`, and Python searches that folder first | The env sets `PYTHONNOUSERSITE=1` on activation, which ignores that folder. Always activate the env; do not run `python.exe` from the env folder directly. |
| `Warning: Cannot find ... (GDAL_DATA is not defined)` | Env not activated, so GDAL cannot find its data files | `conda activate landslide` first. In PyCharm/VS Code, select the conda env as interpreter (they activate it for you). |
| Random "file in use" or duplicated files | Project folder synced by OneDrive | Keep the repo in `C:\Projects\`, outside OneDrive. |
| Training script hangs or starts itself repeatedly | Windows starts parallel workers by re-importing the script | All training code sits under `if __name__ == "__main__":`. |

Do not use `pipwin` or the old Gohlke wheel site. Both are abandoned, and that advice is out of date.

**Fallback without conda:** install Python 3.11 from python.org, then `py -3.11 -m venv .venv`, `.venv\Scripts\activate`, `pip install -r requirements.txt`. This works because rasterio and pyogrio publish Windows wheels with GDAL bundled for 3.11. It is the second choice because QGIS and other GDAL installs can still interfere with it.

## Documentation

| File | Contents |
|---|---|
| [docs/decisions.md](docs/decisions.md) | every decision since the synthetic run, with the measurement behind it |
| [docs/data_sources_log.md](docs/data_sources_log.md) | source, licence and processing for each dataset |
| [docs/01_data_sourcing.md](docs/01_data_sourcing.md) | Step 1: portals, fallbacks, the DEM choice |
| [docs/02_qgis_processing.md](docs/02_qgis_processing.md) | Step 2: raster processing, click by click, plus the NDVI export |
| [docs/literature_review.md](docs/literature_review.md) | Chauhan et al. (2025) and how this project differs |
| [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md) | where the project stands |

## Folder structure

```
landslide-uttarakhand/
|-- data/
|   |-- raw/           portal downloads (not in git)
|   |-- processed/     aligned rasters, dataset.csv (not in git); dataset_synthetic.csv (in git)
|   `-- shapefiles/    boundary, districts, roads, landslide and stable points (not in git)
|-- docs/              guides, decisions, data log, literature review, status
|-- notebooks/         01_eda
|-- src/               config and pipeline scripts
|-- models/            trained models and metadata (not in git)
|-- outputs/           reports, figures (in git); demo maps (not in git)
|-- dashboard/app.py   Streamlit app
|-- environment.yml    conda environment (recommended); environment.lock.yml exact versions
|-- requirements.txt   pip fallback, same pins
`-- verify_setup.py    run first
```
