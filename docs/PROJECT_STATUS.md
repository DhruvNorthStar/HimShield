# Project status

Last updated: 12 September 2026. Update this file whenever a decision is made or a dataset arrives.

## 1. Snapshot

| | |
|---|---|
| Project | Landslide susceptibility mapping, Uttarakhand: SVM vs Random Forest |
| Phase | 2 of 3 |
| Repo | `C:\Projects\landslide-uttarakhand` (deliberately outside OneDrive) |
| Git | branch `main`, 7 commits, no remote yet |
| Environment | conda env `landslide`, Python 3.11.16, at `%USERPROFILE%\miniforge3\envs\landslide` |
| QGIS | 3.44.12 LTR at `C:\Program Files\QGIS 3.44.12` |
| Data source in use | **synthetic** (`src/config.py`, `DEFAULT_DATA_SOURCE`) |
| Steps done | 0, 0.5, 1, 3 built; 2 documented but not yet run |
| Steps left | 2 (in QGIS), 4, 5, 6, 7, 8, 9 |
| Team | one person doing all of it |

What runs today, end to end:

```
conda activate landslide
python verify_setup.py                 # READY, 0 warnings
python -m src.make_synthetic           # 3,600-row simulated dataset
python -m src.eda                      # 5 figures + text report
python -m src.check_dem                # 14 Copernicus tiles, no voids
python -m src.get_open_data --list     # every fallback dataset and its size
```

## 2. What is built

### Code (`src/`)

| File | Lines | What it does |
|---|---|---|
| `src/config.py` | 179 | Every path, column name, seed, grid and artifact name. Nothing else hard-codes them. |
| `src/make_synthetic.py` | 254 | Builds the labelled synthetic dataset used until real data exists. |
| `src/get_open_data.py` | 260 | Downloads the no-account fallback datasets; builds the state and district layers. |
| `src/check_dem.py` | 148 | Validates DEM tiles before the Step 2a mosaic. |
| `src/label_categories.py` | 149 | Turns the QGIS export into `dataset.csv` with the exact schema. |
| `src/eda.py` | 362 | Step 3: reports, quality checks and five figures. |
| `src/viz.py` | 88 | Shared plot style, class colours, synthetic watermark. |
| `verify_setup.py` | 292 | Per-package OK/FAIL plus functional checks for GDAL, PROJ, and the ML chain. |

### Documents

| File | Lines | Contents |
|---|---|---|
| `README.md` | 175 | Setup, Windows failure table, schema, exit artifacts, solo working order. |
| `CONTRIBUTING.md` | 104 | Git workflow, why data stays out of git, notebook conflict recovery. |
| `docs/01_data_sourcing.md` | 284 | Step 1: every source, click path, fallback, sizes, registration delays. |
| `docs/02_qgis_processing.md` | 251 | Step 2a to 2g with verified QGIS algorithm IDs, pitfalls, timings. |
| `docs/data_sources_log.md` | 17 | Provenance table to fill in per file. |
| `docs/PROJECT_STATUS.md` | this file | Status, decisions, next steps. |
| `notebooks/01_eda.ipynb` | 247 | Thin notebook calling `src/eda.py`. |

### Environment files

`environment.yml` (minor-version pins), `environment.lock.yml` (exact resolved versions, the one to install from), `requirements.txt` (pip fallback), `.gitignore`, `.gitattributes`.

### Outputs

`outputs/figures/` holds five EDA figures; `outputs/eda_report.txt` holds the text report. All carry a synthetic-data watermark.

## 3. Decisions, and why

Each of these is a viva answer. The evidence column is the number to quote.

| # | Decision | Reason | Evidence |
|---|---|---|---|
| 1 | Repo at `C:\Projects`, not OneDrive | OneDrive locks files inside `.git` and syncs gigabytes of rasters, causing "file in use" errors and duplicate files | environment check warns if the path contains OneDrive |
| 2 | conda (Miniforge) with Python 3.11 | rasterio and geopandas wrap C libraries; conda-forge ships one matched binary set. pip on Python 3.13/3.14 tries to compile GDAL and fails | `verify_setup.py` passes with GDAL 3.12.3 |
| 3 | Minor-version pins plus a lock file | Exact patch pins were unsolvable: shapely, rasterio and pyogrio must share one GEOS build | first `conda env create` failed on a GEOS conflict |
| 4 | `PYTHONNOUSERSITE=1` on the env | An old `pip install --user` was shadowing the env with numpy 1.25 and pandas 2.0 | env has numpy 2.2.6, pandas 2.3.3 |
| 5 | **Copernicus DEM GLO-30, not SRTM** | SRTM left 766 km2 of voids inside the state (476 in Uttarkashi, 254 in Pithoragarh) in terrain above 4,000 m, plus 882 km2 uncovered from 2 missing tiles. Interpolating those would invent slope in the steepest ground | `python -m src.check_dem`; SRTM kept in `data/raw/dem_srtm_unused/` |
| 6 | geoBoundaries for the boundary, for now | Survey of India needs a login; geoBoundaries is instant and close enough to start | state area 53,418 km2 vs official 53,483; Rudraprayag 1,936 vs 1,984 |
| 7 | EPSG:32644 (UTM 44N) for everything | Slope in degrees and distance in metres need a metric grid. The western edge is 3.3 degrees off the centre line, about 0.1 percent scale error, smaller than DEM error. Two zones would put a seam through the study area | `docs/02_qgis_processing.md` |
| 8 | 1:2 landslide to stable sampling | 1:1 leaves SMOTE nothing to do; wider ratios make imbalance the dominant problem and slow SVM. 1:2 keeps a realistic mild imbalance | `config.NEG_TO_POS_RATIO = 2` |
| 9 | 500 m buffer around landslides when sampling stable points | Ground next to a mapped landslide is probably unstable; labelling it stable teaches the model the opposite. 500 m is about 17 cells | `config.NEGATIVE_BUFFER_M = 500` |
| 10 | Exclude water bodies from stable points | Standard practice; a lake is not stable terrain | Step 2e |
| 11 | SMOTE after the split, training set only | Before the split it leaks synthetic points resembling test rows into training and inflates every score | enforced in Step 4 |
| 12 | Scale once for both models | Required for SVM (distance-based), harmless for RF (split-based); one shared pipeline is simpler to defend | Step 4 |
| 13 | Aspect stored as -1 on flat ground | Flat ground has no direction. A missing value would hide that fact | `gdal:aspect` plus a raster-calculator pass |
| 14 | Curvature multiplied by 100 | GRASS returns 1/m, so values read as 0.0004. Our schema uses 1/100 m | Step 2b |
| 15 | Streams derived from the DEM, not downloaded | Derived streams line up exactly with our slope and curvature grid | `grass:r.watershed`, threshold 1,000 cells (0.9 km2) |
| 16 | SoilGrids WRB for soil | NBSS&LUP is not downloadable; HWSD ships names in an MS Access file Windows Python cannot read | tested: the server returns a clipped GeoTIFF |
| 17 | ESA WorldCover as the land-cover fallback | Bhuvan needs an order plus a signed MoU and takes days | 5 tiles, 472 MB, no account |
| 18 | Geofabrik **central-zone** for the OSM fallback | Uttarakhand is in the Central Zone, not the Northern Zone as first assumed | 10 towns across the state tested against both zone outlines |
| 19 | QuickOSM as the primary road source | Downloads only the roads instead of an 867 MB extract | Step 2c |
| 20 | Synthetic data until the real CSV exists | Lets Steps 3 to 8 be built and tested now; the switch is one line | `dataset_synthetic.csv`, watermarked everywhere |
| 21 | Okabe-Ito blue and vermillion for the two classes | Validated palette: colour-blind separation 21.9 against a floor of 8; survives greyscale printing | `src/viz.py` |
| 22 | Random seed 42 everywhere | Reproducibility | `config.RANDOM_STATE` |

### Settings in `src/config.py`

```
DATA_SOURCE = synthetic        RANDOM_STATE = 42           TEST_SIZE = 0.3
CV_FOLDS = 5                   VIF_THRESHOLD = 10.0        SMOTE_SAMPLING_STRATEGY = 1.0
NEG_TO_POS_RATIO = 2           NEGATIVE_BUFFER_M = 500     PROJECT_CRS = EPSG:32644
DEM_RESOLUTION_M = 30          DEMO_DISTRICT = Rudraprayag PRIMARY_CV_METRIC = roc_auc
DROPPED_COLUMNS = {}           (nothing dropped yet)
```

## 4. Data status

| Factor | Status | Where | Size |
|---|---|---|---|
| DEM | **have**, verified | `data/raw/dem/`, 14 Copernicus GLO-30 tiles | 554 MB |
| State and district boundary | **have**, built into layers | `data/raw/boundary/`, `data/shapefiles/*.gpkg` | 91 MB raw |
| SRTM (rejected) | archived with a note | `data/raw/dem_srtm_unused/` | 298 MB |
| **Landslide inventory (GSI)** | **missing, blocking** | needs Bhukosh or BhuSanket login | few MB |
| Rainfall | missing | IMD yearly files, or CHIRPS fallback | 0.75 to 1.15 GB |
| Land cover | missing | Bhuvan order plus MoU, or WorldCover fallback | 472 MB |
| Soil | missing | `python -m src.get_open_data soil` | about 5 MB |
| Lithology | missing | Bhukosh geology | tens of MB |
| Faults | missing | Bhukosh, or GEM fallback | 11 MB |
| Roads | missing | QuickOSM in QGIS | small |

Synthetic stand-in: `data/processed/dataset_synthetic.csv`, 3,600 rows, 1,200 landslide and 2,400 stable, with deliberate defects (missing values, flat-cell aspect).

Baseline scores on it, no tuning: linear SVM 0.84, RBF SVM 0.86, Random Forest 0.90 test AUC. These are pipeline tests, not findings.

## 5. Changes you made, and what each one caused

| What you did | Effect |
|---|---|
| Approved the move out of OneDrive | Repo lives at `C:\Projects\landslide-uttarakhand` |
| Approved Miniforge and the package downloads | Working environment, setup check passes |
| Approved the QGIS install | QGIS 3.44.12 LTR installed; GRASS provider still needs enabling on first use |
| Said you are doing all the work yourself | Docs rewritten from a three-person split to a solo working order; Step 2 budget raised to 5 to 8 days |
| Registered on USGS EarthExplorer | Account exists; no longer needed for the DEM, but keep it |
| Downloaded 12 SRTM tiles into `data/raw/dem/` | Checked them, found 2 missing tiles and 766 km2 of voids, which triggered the DEM decision |
| Chose Copernicus GLO-30 over SRTM | 14 tiles downloaded and verified void-free; SRTM archived with an explanation |
| Approved the boundary download | State and district layers built in EPSG:32644 |
| Asked for Step 3 | EDA module, notebook and five figures built |

Still open from your side: registering on Bhukosh and Bhuvan, and the QGIS question you were checking.

## 6. Pending

**Data:** the GSI landslide inventory is the blocker. Everything else has a working fallback that needs no account.

**Step 2 in QGIS:** not started. 5 to 8 days solo. The DEM is ready, so 2a can begin now.

**Steps 4 to 9:** not built. Each can be written and tested against synthetic data before real data arrives:

- Step 4 preprocessing: missing values, encoding, VIF, split, scaling, SMOTE
- Step 5 SVM: RBF grid search plus a linear kernel for comparison
- Step 6 Random Forest: grid search and feature importance
- Step 7 evaluation: confusion matrices, classification reports, both ROC curves on one plot, written verdict
- Step 8 dashboard: 3 pages, `streamlit run dashboard/app.py`
- Step 9 demo map: Rudraprayag risk zones, plus the timing projection that decides Phase 3 strategy

**Known issue waiting for Step 4:** the EDA leak check found categories that appear in only one class (`lulc = Water` all landslide; `soil_type = Fluvisols` and `lithology = Alluvium` all stable). These are artefacts of our own sampling rule and must be dropped or merged before training.

## 7. Exact next steps

**Today, by you:**

1. Register on **Bhukosh** (bhukosh.gsi.gov.in) as an External User, and try **BhuSanket** (bhusanket.gsi.gov.in) for "Landslide Inventory (Field Validated)".
2. Register on **Bhuvan** and place the LULC 250K order, because the MoU approval takes days.
3. Start the fallbacks downloading in the background:

   ```
   conda activate landslide
   python -m src.get_open_data soil faults
   python -m src.get_open_data lulc        # only if Bhuvan has not arrived in 5 days
   ```

**Then, Step 2a in QGIS** (about an hour), following `docs/02_qgis_processing.md`:

```
python -m src.check_dem      # must say: 14 tiles, one source, no voids
```

then merge the 14 tiles (**Float32**, since Copernicus heights are decimals), warp to EPSG:32644 at 30 m with bilinear resampling, and clip to `uttarakhand_boundary.gpkg`, producing `dem.tif`.

**In parallel, by me:** Step 4, then 5, 6, 7, 8 on synthetic data, so the ML half is finished and tested before your real CSV lands. Switching to real data is then one line in `src/config.py`.

## 8. Open questions

1. **What is the submission deadline?** Nothing above can be called on track or late without it.
2. **Does Bhukosh or Bhuvan publish a WFS service?** If so, QGIS could pull the inventory or geology directly, skipping the download portal. Unconfirmed.
3. **Survey of India boundary:** worth swapping in if you get it, since it is the official boundary for an Indian report. Drop it at the same paths and everything follows.
