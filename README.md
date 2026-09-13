# Landslide susceptibility mapping, Uttarakhand

A comparative study of Support Vector Machine and Random Forest for predicting landslide-prone terrain in Uttarakhand, India. BCA final-year PBL project.

Given terrain conditioning factors at a location (slope, aspect, elevation, curvature, rainfall, soil, lithology, land cover, and distance to roads, streams and faults), the models predict whether the location is landslide-prone. Positive samples are historical landslides from the GSI inventory. Negative samples are points sampled from stable terrain.

> **Data status: SYNTHETIC.** Until the real QGIS extraction is finished, the pipeline runs on `data/processed/dataset_synthetic.csv`, a simulated dataset with the same schema. Every script prints a banner and every figure is watermarked while this is the case. No result from it is a finding about Uttarakhand. See [Switching to real data](#switching-to-real-data).

## Phase 2 scope

In scope: environment and git setup, data sourcing, QGIS extraction to CSV, EDA, preprocessing (VIF, scaling, SMOTE), SVM and RF with grid search, evaluation and comparison, a basic 3-page Streamlit dashboard, and a demo susceptibility map for one district (Rudraprayag).

Phase 3, not built yet: full-state raster prediction, SHAP explainability, a polished dashboard.

## Setup on Windows

Do this once per laptop. It takes about 15 minutes, most of it downloading.

### 1. Install Miniforge

Miniforge is a small conda installer that uses the conda-forge channel by default. Install it with either:

- PowerShell: `winget install CondaForge.Miniforge3`
- or the installer from https://github.com/conda-forge/miniforge/releases (file `Miniforge3-Windows-x86_64.exe`). Install "Just Me", and keep the default path under your user folder.

Then open **Miniforge Prompt** from the Start menu. Use it for every command below. (In a normal PowerShell window, `conda activate` does not work until you run `conda init powershell` once and restart the window.)

### 2. Create the environment

```
cd C:\Projects\landslide-uttarakhand
conda env create -f environment.lock.yml
conda activate landslide
python verify_setup.py
```

`environment.lock.yml` holds the exact versions, so all three laptops get identical packages. (`environment.yml` is the looser source file it was generated from. Only edit that one when adding a package, then regenerate the lock.)

`verify_setup.py` must end with `READY`. If it prints a FAIL line, it also prints a hint. Fix that before doing anything else.

### 3. Turn on the notebook git filter

```
nbstripout --install
```

Run this once in each clone. It strips outputs from notebooks when you commit, which prevents most notebook merge conflicts. See [CONTRIBUTING.md](CONTRIBUTING.md).

### 4. Point your editor at the environment

- **PyCharm:** Settings > Project > Python Interpreter > Add Interpreter > Conda Environment > Use existing > `landslide`.
- **VS Code:** Ctrl+Shift+P > "Python: Select Interpreter" > pick the one with `landslide` in its path. For notebooks, choose the same kernel in the top right.

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

QGIS is installed separately (the standalone "QGIS LTR" installer from qgis.org) and is not part of the Python environment.

## Running the pipeline

Always run from the repo root with the environment active.

| Step | Command | Status |
|---|---|---|
| Environment check | `python verify_setup.py` | ready |
| Synthetic dataset | `python -m src.make_synthetic` | ready |
| Data sourcing guide | [docs/01_data_sourcing.md](docs/01_data_sourcing.md) | ready |
| Open fallback downloads | `python -m src.get_open_data --list` | ready |
| Check DEM tiles before mosaicking | `python -m src.check_dem` | ready |
| OpenStreetMap roads, tiled and resumable | `python -m src.get_open_data roads` | ready |
| Check derived rasters against dem.tif | `python -m src.check_layers` | ready |
| QGIS processing guide | [docs/02_qgis_processing.md](docs/02_qgis_processing.md) | ready |
| Where the project stands | [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md) | living document |
| QGIS export to dataset.csv | `python -m src.label_categories data/processed/dataset_raw.csv` | ready |
| EDA | `python -m src.eda` or `notebooks/01_eda.ipynb` | ready |
| Preprocessing | `python -m src.preprocess` | ready |
| Train SVM | `python -m src.train_svm` | ready |
| Train RF | `python -m src.train_rf` | ready |
| Evaluate and compare | `python -m src.evaluate` | ready |
| Dashboard | `streamlit run dashboard/app.py` | Step 8 |
| Demo map | (script added in Step 9) | Step 9 |

## Dataset schema

`data/processed/dataset.csv` has exactly these columns, in this order. Every script depends on the names.

| Column | Meaning | Unit / type |
|---|---|---|
| `landslide` | target: 1 = landslide, 0 = stable | int |
| `slope` | slope angle from DEM | degrees |
| `aspect` | slope direction from DEM, -1 where flat | degrees from north |
| `elevation` | SRTM elevation | m |
| `curvature` | surface curvature from DEM | negative = concave |
| `rainfall` | mean annual rainfall (IMD) | mm/year |
| `soil_type` | soil class | category name |
| `lithology` | rock type (GSI) | category name |
| `lulc` | land use / land cover (Bhuvan) | category name |
| `dist_roads` | distance to nearest road (OSM) | m |
| `dist_streams` | distance to nearest stream (from DEM) | m |
| `dist_faults` | distance to nearest fault (GSI) | m |

All column names, paths, the random seed (42) and hyperparameter grids live in [src/config.py](src/config.py). Nothing else hard-codes them.

### Dropped columns

If a column cannot be produced from real data, it is added to `DROPPED_COLUMNS` in `src/config.py` with the reason, and listed here. Every script reads that setting, so the drop applies everywhere at once.

None so far.

## Switching to real data

When the QGIS export is saved as `data/processed/dataset.csv`:

1. Change `DEFAULT_DATA_SOURCE = "real"` in `src/config.py` and commit it, so all three of us switch together.
2. Rerun the pipeline from preprocessing onward. Models trained on synthetic data must not be kept.

`models/metadata.json` records which data source each model was trained on.

## Phase 2 exit artifacts

Phase 3 loads these instead of retraining. Names and formats are fixed.

| File | Contents |
|---|---|
| `models/svm_model.pkl` | trained SVM (best estimator) |
| `models/rf_model.pkl` | trained RF (best estimator) |
| `models/scaler.pkl` | fitted StandardScaler |
| `models/feature_names.json` | ordered final feature list after VIF drops. Prediction must use this order. |
| `models/metadata.json` | kept and dropped features with VIF values, best params, test metrics, SMOTE ratio, random seed, data source |
| `data/processed/dataset.csv` | cleaned dataset before the split |
| `outputs/figures/*.png` | all plots |

## Folder structure

```
landslide-uttarakhand/
|-- data/
|   |-- raw/           portal downloads (not in git)
|   |-- processed/     extracted CSV
|   `-- shapefiles/    boundary, roads, faults, inventory (not in git)
|-- notebooks/         01_eda, 02_model_comparison
|-- src/               config and pipeline scripts
|-- models/            trained models (not in git)
|-- outputs/figures/   plots
|-- dashboard/app.py   Streamlit app
|-- environment.yml    conda environment (recommended)
|-- requirements.txt   pip fallback, same pins
`-- verify_setup.py    run first
```

## Working order (one person)

The whole build is being done by one person, so the order matters more than any split of work. The
pipeline runs on the synthetic dataset from day one, which means the ML half is finished and tested
before the real CSV arrives, and swapping in real data is a one-line change.

| Order | Work | Depends on |
|---|---|---|
| 1 | Register on the portals, place the Bhuvan order | nothing, do it first: approvals take days |
| 2 | Steps 3 to 8 on synthetic data (EDA, preprocessing, SVM, RF, evaluation, dashboard) | nothing |
| 3 | Step 1 downloads, in the background while Step 2 runs | registrations |
| 4 | Step 2 in QGIS, one sub-step per sitting | downloads |
| 5 | Switch to real data, rerun Steps 3 to 8, then Step 9 | dataset.csv |
