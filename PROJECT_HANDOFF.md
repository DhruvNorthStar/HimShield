# PROJECT HANDOFF: HimShield

Written 14 September 2026 at the end of a working session, so a fresh Claude Code session can continue without losing context. Updated later on 14 September: rainfall raster built and verified, deadline confirmed as 19 October. Read this whole file before doing anything. `docs/PROJECT_STATUS.md` is the living status document; this file is the complete briefing.

---

## 1. What the project is

**HimShield**: landslide susceptibility mapping for Uttarakhand, India, comparing **Support Vector Machine** and **Random Forest**. BCA final-year PBL project, built by **one person** (GitHub user DhruvNorthStar). Faculty requirement: SVM and RF are mandatory, and their comparison is the core deliverable.

Binary classification: given terrain conditioning factors at a location, predict whether it is landslide-prone. Positives are historical landslide locations; negatives are points sampled from stable terrain.

### Phase boundary (the user asked to be held to this)

- **Phase 2, in scope now:** environment and git, data sourcing, QGIS extraction to CSV, EDA, preprocessing, SVM, RF, evaluation and comparison, a basic 3-page Streamlit dashboard, a demo susceptibility map for **Rudraprayag district only**.
- **Phase 3, out of scope:** full-Uttarakhand raster prediction, SHAP explainability, a polished dashboard. If the user asks for these, remind them they are Phase 3 and confirm before building.

### Deadline

Phase 2 is due **25 working days from 13 September 2026: Monday 19 October 2026**. Day 1 is Monday 14 September; days run Monday to Friday, and Gandhi Jayanti (Friday 2 October) is a college holiday (confirmed by the user on 14 September). Any other college holiday before then pushes the date back one working day.

---

## 2. Status at handoff

**Phase 2 is about 75 percent complete.** Everything on the ML side runs end to end on synthetic data. The remaining work is mostly QGIS and data, and one dataset (the real GSI landslide inventory) is blocking.

| Step | State |
|---|---|
| 0 Environment | done, `verify_setup.py` prints READY |
| 0.5 Git and GitHub | done, pushed to public repo after every commit |
| 1 Data sourcing | mostly done; inventory provisional, lithology missing |
| 2 QGIS processing | 2a, 2b, 2c, land cover, soil and rainfall **done and verified** (all 10 rasters), plus `twi.tif` added 14 September; lithology, landslide points, stable points, extraction **not started** |
| 3 EDA | done (synthetic) |
| 4 Preprocessing | done (synthetic) |
| 5 SVM | done (synthetic) |
| 6 Random Forest | done (synthetic) |
| 7 Evaluation | done (synthetic) |
| 8 Dashboard | **done** (synthetic): `streamlit run dashboard/app.py`, four pages, browser-tested 14 September |
| 9 Rudraprayag demo map | **groundwork done** (synthetic): `python -m src.demo_map`, timed; real result needs real models. RF: 2,145,236 cells in 9 to 14 s across runs (148,000 to 229,000 cells/s), state projected 4 to 7 min of scoring. SVM: 444 s (4,827 cells/s), state projected about 204 min. Full state must be tiled (about 14 GB in one pass). The synthetic SVM scored all of Rudraprayag 0.000: tested and traced to `dist_faults` alone (real 56 to 127 km, 13 to 30 sd beyond synthetic training); RF unaffected. `demo_map` now warns when a factor is more than half out of range |

**Naming mismatch to be aware of:** the user calls the land cover and soil work "Step 2d". In `docs/02_qgis_processing.md`, section **2d is "Landslide points"**, and land cover and soil live under **"Land cover and soil rasters"**. Rainfall lives under **"Rainfall raster (CHIRPS)"**. Use the user's wording in conversation, and the document's headings when pointing to the file.

---

## 3. Machine and environment

| Item | Value |
|---|---|
| OS | Windows 11 Home |
| RAM / CPU | 7.7 GB / 4 logical cores |
| Free disk on C: | 35 GB |
| Local repo | `C:\Projects\landslide-uttarakhand` (deliberately outside OneDrive) |
| Conda | Miniforge at `%USERPROFILE%\miniforge3` |
| Environment | `landslide`, Python 3.11.16 |
| Key packages | numpy 2.2.6, pandas 2.3.3, scikit-learn 1.7.2, imbalanced-learn 0.14.2, statsmodels 0.14.6, rasterio 1.4.4 (GDAL 3.12.3), geopandas 1.1.4, shapely 2.1.2, streamlit 1.49.1, folium 0.20.0 |
| QGIS | 3.44.12 LTR at `C:\Program Files\QGIS 3.44.12`; GRASS provider enabled in the user's profile |

### Environment traps (all hit already)

- **Always activate the environment** (`conda activate landslide`) or use `conda run -n landslide`. An old `pip install --user` left numpy 1.25 and pandas 2.0 in `AppData\Roaming\Python\Python311`. The env sets `PYTHONNOUSERSITE=1` on activation to ignore it. Calling `miniforge3\envs\landslide\python.exe` directly skips that and loads the wrong numpy, which then cannot read the numpy 2 pickles in `models/`. If you must call python.exe directly, pass `-s`.
- `conda run ... python -c` cannot take multi-line code. Write a script file (the session scratchpad) and run that.
- Shell tools: the Bash tool is Git Bash; PowerShell is 5.1, which strips double quotes from arguments to native programs. Long heredocs containing apostrophes broke once in Bash; use the Write tool for long text.

### Running QGIS algorithms headless (how every QGIS step was rehearsed)

```
cd "/c/Program Files/QGIS 3.44.12/bin"
echo '{"inputs": {"INPUT": "...", "OUTPUT": "..."}}' | ./qgis_process-qgis-ltr.bat run gdal:warpreproject -
```

- Launcher name is `qgis_process-qgis-ltr.bat` (not `qgis_process-ltr.bat`).
- GRASS algorithms are hidden headless unless the plugin is enabled. Make a throwaway profile folder containing `profiles/default/QGIS/QGIS3.ini` with `[PythonPlugins]` and `grassprovider=true`, and set `QGIS_CUSTOM_CONFIG_PATH` to it. Delete it afterwards. Never edit the user's own QGIS profile.
- Extent format: `"170670,504360,3177720,3481770 [EPSG:32644]"` (this is the dem.tif extent).
- GDAL command-line tools are in `%USERPROFILE%\miniforge3\envs\landslide\Library\bin`.
- Rehearse in the session scratchpad, never over the user's files in `data/processed/`.

---

## 4. Repository and git

| Item | Value |
|---|---|
| GitHub | https://github.com/DhruvNorthStar/HimShield (**public**) |
| Branch | `main`, tracking `origin/main` |
| State at handoff | clean, local `main` equals `origin/main` |
| Commit author | `DhruvNorthStar <pandeydhruv92@gmail.com>`; the user explicitly chose this over the GitHub noreply address, knowing the repo is public |
| Workflow | commit on `main`, **push after every commit**, confirm GitHub matches (`git ls-remote origin refs/heads/main`) |
| Commit trailer | end messages with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>` |
| Notebook filter | `nbstripout --install` is active in this clone |

### What is tracked, what is not

Tracked on purpose: code, docs, `environment*.yml`, `requirements.txt`, the synthetic dataset, figures and reports in `outputs/`, `uttarakhand.qgz`, and the six QuickOSM extent rectangles in `data/processed/quickosm_extents/`.

Ignored on purpose (see `.gitignore`): `data/raw/`, `data/shapefiles/`, all rasters (`*.tif`, `*.vrt`), derived vector layers `data/processed/*.gpkg`, QGIS sidecars (`*.tfw`, `*.aux.xml`, `*.qgd`), `models/`, `*.pkl`, `*.joblib`. Reasons: size, regenerable, and third-party licences (ODbL, CC BY-SA) that a public copy would have to honour.

No LICENSE file. The user was told the repo is "all rights reserved" without one; adding a licence is their decision.

---

## 5. Every file in the repository

### Code (`src/`)

| File | Purpose |
|---|---|
| `src/__init__.py` | Makes `src` a package; run modules as `python -m src.<name>` from the repo root |
| `src/config.py` | **Single source of truth**: paths, CSV schema, data source switch, CRS, sampling rules, seed, grids, artifact names, `DROPPED_COLUMNS` |
| `src/make_synthetic.py` | Builds `data/processed/dataset_synthetic.csv`, a clearly labelled simulated dataset with the exact schema |
| `src/get_open_data.py` | No-account downloads: `boundary`, `dem`, `lulc`, `soil`, `rainfall` (CHIRPS, default 2009 to 2024), `faults`, `roads` (tiled resumable Overpass); `--list` shows sizes only; `boundary` also builds the state and district layers |
| `src/check_dem.py` | Validates DEM tiles before mosaicking: count, source mixing, voids inside the state, missing tiles |
| `src/check_layers.py` | Validates every derived raster against the `dem.tif` grid: alignment, physical ranges, constant layers, distance layers that are mostly 0 |
| `src/label_categories.py` | Step 2g: QGIS CSV export to `dataset.csv`; strips band suffixes, maps WorldCover and SoilGrids codes to names, **labels SoilGrids code 0 as "No soil (rock or ice)"**, -9999 to missing, aspect -1 on flat, validates the schema |
| `src/eda.py` | Step 3: missing values, class separation, quality checks (including one-sided category leak risk), five figures, text report |
| `src/preprocess.py` | Step 4: drop water rows, fill missing, aspect to sine/cosine, one-hot, VIF, stratified split, scaler on train only, SMOTE on train only; `prepare_for_prediction()` for the dashboard and Phase 3 |
| `src/train_svm.py` | Step 5: RBF grid search plus linear kernel, **SMOTE inside each CV fold** via imblearn pipeline, probability refit |
| `src/train_rf.py` | Step 6: grid search with SMOTE inside folds, impurity and permutation importance, figure |
| `src/evaluate.py` | Step 7: metrics at 0.5 and Youden threshold, ROC/confusion/PR figures, bootstrap AUC difference, written verdict |
| `src/viz.py` | Shared plot style; Okabe-Ito blue/vermillion class colours; synthetic watermark on saved figures |
| `src/artifacts.py` | Merges each step's section into `models/metadata.json`; writes and loads `feature_names.json` |
| `src/demo_map.py` | Step 9: scores every Rudraprayag cell from the aligned rasters (water skipped) in 250,000-row chunks through `prepare_for_prediction`, five fixed-break zones, writes `data/processed/susceptibility_rudraprayag_<model>.tif`, `outputs/demo_map_rudraprayag.html` and a `demo_map` metadata section; reports values and classes outside training, and projects full-state time; `--model svm` for the SVM version |
| `dashboard/app.py` | Step 8: Streamlit app with Overview, Model Comparison, Predict and Rudraprayag Map pages; reads exit artifacts and saved figures only |
| `.streamlit/config.toml` | Light theme with Okabe-Ito blue controls, usage statistics off |
| `verify_setup.py` | Environment check: per-package OK/FAIL, GDAL raster and vector IO, PROJ, the ML chain, packages loaded from outside the env |

### Documents and other tracked files

| File | Purpose |
|---|---|
| `PROJECT_HANDOFF.md` | This briefing |
| `README.md` | Project overview, clone and Windows setup, failure table, pipeline command table, schema, exit artifacts, solo working order |
| `CONTRIBUTING.md` | Solo git workflow, why data stays out of git, notebook conflicts, commit messages |
| `docs/01_data_sourcing.md` | Step 1: every source, portal click paths, fallbacks with verified sizes, the DEM decision, registration delays |
| `docs/02_qgis_processing.md` | Step 2: every QGIS sub-step click by click, rehearsed on real data, with expected numbers and error tables |
| `docs/data_sources_log.md` | Provenance table: source, file, resolution, date, licence and caveats for each factor |
| `docs/PROJECT_STATUS.md` | Living status document |
| `docs/literature_review.md` | Primary reference Chauhan, Gupta and Dixit (2025), read in full text; side-by-side comparison and this project's defensible contribution; method references; unread papers kept separate |
| `notebooks/01_eda.ipynb` | Thin notebook calling `src/eda.py` |
| `environment.yml` | Conda spec with minor-version pins |
| `environment.lock.yml` | Exact resolved versions; install from this |
| `requirements.txt` | pip fallback with the same versions |
| `.gitignore`, `.gitattributes` | Ignore rules; LF normalisation and nbstripout filter |
| `uttarakhand.qgz` | The user's QGIS project |
| `data/processed/dataset_synthetic.csv` + `.README.txt` | 3,600-row synthetic dataset and its label |
| `data/processed/quickosm_extents/roads_part_1..6.gpkg` | Six rectangles for the manual QuickOSM route |
| `outputs/figures/*.png` (9) | EDA, feature importance, ROC, confusion matrices, precision-recall; all watermarked synthetic |
| `outputs/eda_report.txt`, `outputs/evaluation_report.txt` | Text reports (synthetic) |

`models/` holds only `.gitkeep` in git. `outputs/demo_map_*.html` and `.claude/` (the local preview launcher) are ignored on purpose.

---

## 6. Data status with exact paths (local, not in git)

### Raw downloads, `C:\Projects\landslide-uttarakhand\data\raw\`

| Folder | Contents | Size | Status |
|---|---|---|---|
| `boundary/` | `geoBoundaries-IND-ADM1.geojson`, `geoBoundaries-IND-ADM2.geojson` | 91 MB | used |
| `dem/` | 14 × `Copernicus_DSM_COG_10_N??_00_E0??_00_DEM.tif` | 554 MB | used, verified void free |
| `dem_srtm_unused/` | 12 SRTM tiles plus `WHY_UNUSED.txt` | 298 MB | rejected, kept for the report |
| `lulc/` | 5 × `ESA_WorldCover_10m_2021_v200_*_Map.tif` | 451 MB of tiles | used |
| `soil/` | `soilgrids_wrb_mostprobable.tif`, `soilgrids_wrb_legend.json` | 0.45 MB | used |
| `geology/` | `gem_active_faults_harmonized.geojson` | 10.6 MB | used, weak |
| `landslides/` | `global_landslide_catalog_NASA.shp` (+ .dbf .prj .shx .zip) | 3.6 MB zip | **provisional** |
| `osm/roads_tiles/` | 17 cached Overpass tile JSON files | 103 MB | cache, deletable |
| `rainfall/` | `chirps-v2.0.2009.tif` to `chirps-v2.0.2024.tif`, 16 files (2005 to 2008 deleted by the user) | 880 MB | used |

### Vector layers, `data\shapefiles\` (EPSG:32644)

| File | Contents |
|---|---|
| `uttarakhand_boundary.gpkg` | State outline, 53,418 km2 (official 53,483) |
| `uttarakhand_districts.gpkg` | 13 districts, ASCII names in `district`; Rudraprayag 1,936 km2 |
| `roads.gpkg` | 27,312 OSM segments, 45,736 km (36,894 inside the state, 10 km margin beyond) |
| `faults.gpkg` | 8 GEM faults within 50 km of the state (anticline removed), 519 km |

### Derived rasters, `data\processed\`, all verified on one grid

Grid: **11,123 × 10,135 cells, 30 m, EPSG:32644, extent 170670 to 504360 E, 3177720 to 3481770 N.**

| File | Range | Notes |
|---|---|---|
| `dem.tif` | 184 to 7,800.55 m | Real GeoTIFF, 138 MB, DEFLATE |
| `slope.tif` | 0 to 80.16° | GRASS r.slope.aspect |
| `aspect.tif` | -1 to 360 | converted from GRASS convention; 4,107,242 flat cells |
| `curvature.tif` | -6.61 to 6.74 | profile curvature × 100 |
| `twi.tif` | 1.30 to 32.63 | GRASS r.watershed topographic index, multiple flow direction; Float64, NoData NaN, 448 MB; headless whole-state rehearsal copied in unchanged (527 s) |
| `dist_roads.tif` | 0 to 100,360 m | |
| `dist_streams.tif` | 0 to 111,522 m | r.watershed, threshold 1,000 cells, redone after an all-zero first attempt |
| `dist_faults.tif` | 0 to 275,434 m | |
| `lulc.tif` | codes 10 to 100 | Mode resampling |
| `soil.tif` | codes 0 to 29 | nearest neighbour; code 0 kept intact |
| `rainfall.tif` | 390 to 2,520 mm over the grid; 506 to 2,519 inside the state | mean of 2009 to 2024, bilinear, 60 MB; intermediate `rain_mean.tif` (EPSG:4326, 0.05°) |

**Intermediates also in `data\processed\`** (not needed downstream, deletable only with the user's agreement): `aspect_grass.tif`, `curvature_raw.tif`, `streams.tif`, `streams_raw.tif`, `drainage.tif`, `roads_rast.tif`, `faults_rast.tif`, `dem_rudraprayag.tif`, `dem.tif.vrt`, `dem_utm.tif.vrt`, `dem_merged.vrt`, `faults_clip.gpkg`, `faults_no_fold.gpkg`, `state_buffer_50km.gpkg`, `rudraprayag_boundary.gpkg`, `prepared.joblib`. `aspect.tif`, `curvature.tif` and the three `dist_*.tif` are uncompressed (~431 MB each) and could be recompressed losslessly. The folder totals 3.7 GB.

### Models, `models\` (trained on synthetic data)

`svm_model.pkl` (373 KB), `rf_model.pkl` (8.8 MB), `scaler.pkl`, `feature_names.json` (30 features, including `twi` since 14 September), `metadata.json` (every section written by Steps 4 to 7, including `data_source: synthetic`).

---

## 7. QGIS: done and remaining

### Done (all verified with `python -m src.check_layers`)

| Sub-step | Output | Key settings |
|---|---|---|
| 2a DEM mosaic | `dem.tif` | virtual raster of 14 tiles, warp to 32644 at 30 m bilinear, clip to state |
| 2b terrain | `slope.tif`, `aspect.tif`, `curvature.tif` | r.slope.aspect; aspect conversion expression; curvature × 100 |
| 2c roads | `dist_roads.tif` | `python -m src.get_open_data roads`, rasterise (burn 1, NoData 0, Byte), proximity (target 1, georeferenced units) |
| 2c streams | `dist_streams.tif` | r.watershed threshold 1000, single flow direction, disk swap; `"streams@1" > 0`; proximity target 1 |
| 2c faults | `dist_faults.tif` | clip in lat/long first, 50 km buffer, remove anticline, reproject, rasterise, proximity |
| land cover | `lulc.tif` | VRT with "separate band" unticked, warp Mode, extent from dem, 30 m, `-ovr NONE` |
| soil | `soil.tif` | warp nearest neighbour, NoData left empty |
| rainfall | `rainfall.tif` | cell statistics mean of 16 CHIRPS years, warp bilinear to the dem grid (section 8) |

### Remaining, in order

1. **Rainfall**: done on 14 September and verified (section 8).
2. **Lithology**: needs Bhukosh. If it never arrives, add `lithology` to `DROPPED_COLUMNS` in `src/config.py` with the reason and record the drop in the README.
3. **2d landslide points**: reproject, clip, polygons to points with `native:pointonsurface`, delete duplicates, add `landslide = 1`.
4. **2e stable points**: 500 m buffer around landslides, water mask from `lulc.tif` code 80, difference, `native:randompointsinpolygons` with 2 × positives and 500 m minimum spacing, `landslide = 0`.
5. **2f extraction**: merge points, `native:rastersampling` per raster with the prefixes in `docs/02_qgis_processing.md`, lithology by spatial join.
6. **2g export**: CSV without geometry to `data/processed/dataset_raw.csv`, then `python -m src.label_categories data/processed/dataset_raw.csv`.

### QGIS project hygiene (last checked 13 September)

The `dem` layer in `uttarakhand.qgz` pointed at `dem.tif.vrt` instead of `dem.tif`, and `streams_raw` carried a 65,536-class palette that bloated the project file. Both were reported to the user; whether they fixed them is unknown.

---

## 8. Rainfall processing (done 14 September 2026, verified)

Full click-by-click steps are in `docs/02_qgis_processing.md` under **"Rainfall raster (CHIRPS)"**. Rehearsed on the real files on 14 September, then run by the user the same day.

**Verification of the user's run:** `check_layers` shows 10 of 10 layers aligned. Inside the state: minimum 506 mm, median 1,448 mm, maximum 2,519 mm, no NoData; every district median within 1 mm of the rehearsal. `rain_mean.tif` is identical (difference 0.000 mm) to an independently computed 2009 to 2024 mean, so the right 16 years were used. The only deviation is `PREDICTOR=2` instead of 3, which affects compression only (60 MB instead of 65 MB), not values.

**Use only 2009 to 2024 (16 files).** Over Uttarakhand, the 2005 to 2008 average is 42.7 percent below 2009 to 2024, its spatial pattern matches at only r = 0.52, and 2009 (a nationwide drought year) scores above all four. That is a shift in the CHIRPS record, not weather.

1. **Cell statistics** (`native:cellstatistics`): the 16 layers, Statistic **Mean**, Ignore NoData ticked, reference layer `chirps-v2.0.2009` (not dem), output NoData -9999, save `data/processed/rain_mean.tif`. About 12 s.
2. **Warp**: input `rain_mean`, 4326 to **32644**, **Bilinear**, NoData -9999, resolution 30, extent from `dem`, Float32, multithreaded, `COMPRESS=DEFLATE` and `PREDICTOR=3`, save `data/processed/rainfall.tif`. About 17 s, 65 MB.
3. **Verify**: `python -m src.check_layers` must show 10 layers aligned.

**Expected inside the state:** minimum 505 mm, median 1,448 mm, maximum 2,520 mm, no NoData. District medians: Dehradun 1,854 (wettest), Nainital 1,593, Tehri Garhwal 1,538, Rudraprayag 1,381, Pithoragarh 1,346, Chamoli 1,278 (driest). Rainfall falls above 3,000 m (rain shadow).

**CHIRPS over IMD:** CHIRPS has 2,000 cells inside the state against 80 IMD grid points. Stated limitations: satellite rainfall underestimates orographic rain; true resolution about 5.5 km; an annual mean does not capture the short bursts that trigger landslides.

---

## 9. The GSI landslide inventory: situation and fallback

**This is the project's main blocker.** Without a real inventory there are no real positive samples.

- **BhuSanket** (bhusanket.gsi.gov.in) shows the inventory in a map viewer with no download button. Behind it sits an ArcGIS service, `gisserver/rest/services/Hosted/India_All_Landslided/FeatureServer/0`, holding **31,551 landslide points nationally**. Requested directly it answers **"Token Required"**; only the site's own proxy can read it. **We deliberately did not pull data through that proxy**: it routes around an access control and would not be defensible in a viva. Do not do it in a later session either.
- **Bhukosh** (bhukosh.gsi.gov.in): the user **has not registered yet**. The in-app browser could not load the site. Registration is the legitimate route to the inventory and to lithology. The user was given field-by-field registration guidance, including a purpose statement to paste.
- A **faculty request to GSI on college letterhead** was recommended in parallel.

### Provisional inventory on disk

NASA Global Landslide Catalog via HDX (CC BY), `data/raw/landslides/global_landslide_catalog_NASA.shp`: 11,033 records worldwide, **205 inside Uttarakhand** (Uttarkashi 51, Chamoli 41, Pithoragarh 20, Rudraprayag 19). Location accuracy: 1 km 28, 5 km 57, 10 km 27, 25 km 40, 50 km 35, unknown 16. **Only 85 points are accurate to 5 km or better**, which is not enough for a defensible final result at 30 m.

### Other options

- NASA High Mountain Asia Landslide Catalog v2 (NSIDC): about 2,800 events across High Mountain Asia, needs a free NASA Earthdata login.
- NASA COOLR server returned 503 on 12 September.
- data.gov.in holds only parliamentary tables about landslides, no spatial inventory.

### Decision point: day 10, about Friday 25 September 2026

If there is still no GSI data, **digitise landslide scars for Rudraprayag by hand** in Google Earth (100 to 200 polygons in about a day; a standard, publishable method) and scope the Phase 2 result to that district, which is also the Step 9 demo district.

---

## 10. Decisions made, with reasons

| Decision | Reason |
|---|---|
| Repo in `C:\Projects`, not OneDrive | OneDrive locks `.git` files and syncs gigabytes of rasters |
| Miniforge conda, Python 3.11, lock file | GDAL, GEOS and PROJ as one matched binary set; exact patch pins were unsolvable, so minor pins plus a lock |
| **Copernicus GLO-30, not SRTM** | SRTM left 766 km2 of voids inside the state (476 in Uttarkashi) above 4,000 m, plus 2 missing tiles |
| geoBoundaries boundary for now | Survey of India needs a login; swap in the official boundary at the same paths if obtained |
| EPSG:32644 statewide | metric grid; 0.1 percent scale error at the west edge beats a seam through the study area |
| 1:2 landslide to stable points | 1:1 leaves SMOTE nothing to do; wider ratios make imbalance dominate and slow SVM |
| 500 m buffer when sampling stable points | ground beside a mapped landslide is not stable (about 17 cells) |
| Exclude water from stable points | a lake is not stable terrain |
| SMOTE after the split **and inside CV folds** | anything else scores memorisation; measured CV 0.92 against test 0.69 before the fix |
| Scaler fitted on training data only; one pipeline for both models | required for SVM, harmless for RF |
| Aspect as sine and cosine, flat as (0, 0) | aspect is circular |
| Drop water rows in Step 4 | Step 2e excludes water, so a water point can only be a landslide |
| AUC as the headline metric | accuracy is near useless at a 1:2 balance |
| Roads: tiled Overpass download, 10 km margin, road classes only | QuickOSM timed out on 61,260 segments; border points may be nearest roads in Nepal or Himachal; tracks are not road cuts |
| Streams derived from the DEM, threshold 1,000 cells | aligned with terrain; 0.9 km2 catchment |
| Faults: clip in lat/long, 50 km area, anticline removed | global reprojection gave 30 faults infinite coordinates; 4 faults inside the state versus 9 within 50 km |
| Mode for land cover, nearest for soil, bilinear for rainfall | Mode when shrinking classes, nearest when enlarging classes, bilinear for continuous values; never average class codes |
| Soil code 0 kept as "No soil (rock or ice)" | it is SoilGrids fill (11.3 percent of the state, median 5,224 m); missing would let Step 4 call glaciers Cambisols |
| CHIRPS, 2009 to 2024 only | 25 times more cells than IMD; 2005 to 2008 are inconsistent |
| Synthetic data until the real CSV | Steps 3 to 7 finished and tested early; switching is one line |
| Seed 42 everywhere | reproducibility |
| TWI added to the schema, TRI left out (14 September, user's decision on measured evidence) | whole state: TWI rank correlation with slope -0.51, VIF 1.64; TRI rank correlation with slope 0.993, VIF 21.2. Both used by Chauhan et al. (2025) |
| Risk zones at fixed breaks 0.2, 0.4, 0.6, 0.8 | natural breaks and quantiles are recomputed per map, so a zone would mean different scores on different runs and models; quantiles force 20 percent into every zone |
| Zone colours: one vermillion hue, light to dark | ordered classes need a sequential ramp, not green to red (fails colour-blind readers); matches the landslide colour in every figure; validated as an ordinal ramp (light end 2.19:1 on the basemap) |
| Water cells skipped on the map | models never saw water (Step 2e and Step 4), so any score there would be invented |
| Synthetic class bridge in `demo_map.py`, synthetic runs only | the simulated dataset's class names (Forest, Glacier) differ from WorldCover and SoilGrids; without the bridge every cell would silently score as the reference class |

---

## 11. ML results so far (SYNTHETIC data, not findings about Uttarakhand)

### Preprocessing

Retrained 14 September after adding TWI. 3,600 rows in, 5 water rows dropped, 3,595 used. Missing filled: twi 8 and rainfall 17 (median), soil_type 64, lithology 39 (most frequent). 3 categorical columns to 20 dummies; **30 features**; **no VIF drops** (highest lithology_Phyllite 5.86). Split: train 2,516 (836 landslide), test 1,079 (359 landslide). SMOTE on training: 1,680 / 836 to 1,680 / 1,680. Test untouched: 720 / 359.

### Models

| | SVM (RBF) | Random Forest |
|---|---|---|
| Best parameters | C=10, gamma=0.01 | max_depth 10, n_estimators 200, min_samples_split 2 |
| CV AUC | 0.8653 | 0.8956 |
| **Test AUC** | 0.8554 | **0.8827** |
| Average precision | 0.7235 | 0.7814 |
| Accuracy / precision / recall / F1 at 0.5 | 0.769 / 0.627 / 0.755 / 0.685 | 0.789 / 0.649 / 0.794 / 0.714 |
| Landslides missed | 88 of 359 | 74 of 359 |
| Youden threshold | 0.34 (recall 0.866) | 0.46 (recall 0.847) |

Linear SVM test AUC 0.8409, so RBF beats linear by **+0.0145**, just past the 0.01 the verdict treats as meaningful (before TWI it was +0.0090). RF minus SVM AUC: **+0.0271**, bootstrap 95 percent interval **+0.0137 to +0.0416** (separable).

RF top features (impurity / permutation): slope 0.2478 / 0.1236, rainfall 0.1699 / 0.0584, elevation 0.1310 / 0.0197, dist_roads 0.0677 / 0.0123, curvature 0.0610 / 0.0079. twi ranks 6th of 30 by impurity (0.0493) and 9th by permutation (0.0020). In the synthetic data twi barely separates the classes (point-biserial r 0.03): the simulated wetness effect is small next to slope, so this says nothing about real data.

Before TWI (29 features, for the record): SVM test 0.8304, RF 0.8682, gap +0.0379 (+0.0234 to +0.0529).

---

## 12. Known issues and fixes

### Fixed

| Problem | Fix |
|---|---|
| SMOTE leaking inside cross-validation (SVM CV 0.9199, test 0.6884, chose gamma=1) | SMOTE inside an imblearn pipeline in both trainers |
| `dist_streams.tif` 0 in all 112.7 million cells | proximity rerun with target value 1 on the binary streams layer |
| `check_layers` passed that all-zero layer | now fails constant layers and distance layers more than half zero |
| `check_layers` limit of 200 km would fail correct `dist_faults` | raised to 500 km (grid diagonal about 452 km) |
| Soil code 0 read as Acrisols, reported earlier as 8 percent | labelled No soil (rock or ice); data log corrected |
| GEM global reprojection gave infinite coordinates | clip in lat/long first |
| Step 2a saved as `dem.tif.vrt` | converted to a real GeoTIFF; guide and checker warn |
| Old pip numpy shadowing the env | `PYTHONNOUSERSITE=1`; `verify_setup.py` fails if it recurs |
| Exact conda pins unsolvable | minor pins plus lock file |
| Accented state name in geoBoundaries | accents folded before matching |
| GRASS aspect convention | conversion expression |
| Water-class leak | water rows dropped in Step 4 |
| Uttarakhand assumed in Geofabrik northern zone | it is in central-zone (10 towns tested) |
| CHIRPS 2005 to 2008 inconsistency | 2009 to 2024 only; downloader default changed |
| GitHub repo had an unrelated initial commit | merged with `--allow-unrelated-histories`, README kept and retitled |
| Commits only local | origin added, pushed, push after every commit |

### Open

- **GSI inventory** not obtained; provisional NASA points too sparse and inaccurate (section 9).
- **Lithology** missing, needs Bhukosh.
- **`dist_faults` is weak**: only 4.8 percent of the state within 5 km of a fault, 61 percent beyond 50 km. It behaves like a regional gradient and could act as a disguised location. Replace with GSI structural lines if possible; if it ranks suspiciously high on real data, drop it via `DROPPED_COLUMNS`. Measured 14 September: every cell in Rudraprayag is 55.7 to 127.1 km from the nearest GEM fault (median 96.3 km), even though the Main Central Thrust crosses the district, because GEM holds active faults only. **Full real-feature VIF on a whole-state grid sample (14 September):**
  - Elevation is 14.5, above the threshold, because it tracks `dist_faults` (rank correlation 0.90). Without `dist_faults` elevation falls to 7.8.
  - Step 4's rule would drop elevation, the wrong column. Decide before the real run whether to drop `dist_faults` through `DROPPED_COLUMNS`.
  - `lulc_Tree cover` (10.1) is only high because Step 4 uses the first class alphabetically as the reference; with the most common class as the reference it falls well below 10.
  - TWI is 1.73.
- **Random train/test split** ignores spatial autocorrelation, so scores are likely optimistic; stated in the evaluation report.
- **Stable points mean "no recorded landslide"**, not "cannot fail"; stated in the evaluation report.
- **`data/processed/` holds 3.7 GB**, much of it intermediates and uncompressed rasters. Cleanup offered, never done without the user's go-ahead.
- **QGIS project hygiene** items in section 7 may still be outstanding.

---

## 13. Config settings (`src/config.py`)

```
DEFAULT_DATA_SOURCE = 'synthetic'     # change to 'real' when data/processed/dataset.csv exists
RANDOM_STATE = 42                     TEST_SIZE = 0.3                 CV_FOLDS = 5
VIF_THRESHOLD = 10.0                  SMOTE_SAMPLING_STRATEGY = 1.0   SMOTE_K_NEIGHBORS = 5
NEG_TO_POS_RATIO = 2                  NEGATIVE_BUFFER_M = 500
PROJECT_CRS = 'EPSG:32644'            GEOGRAPHIC_CRS = 'EPSG:4326'    DEM_RESOLUTION_M = 30
N_JOBS = -1                           PRIMARY_CV_METRIC = 'roc_auc'
DEMO_DISTRICT = 'Rudraprayag'         RISK_ZONES = ['Very Low', 'Low', 'Moderate', 'High', 'Very High']
RISK_ZONE_BREAKS = [0.2, 0.4, 0.6, 0.8]   # fixed equal breaks; config.risk_zone(score) names the zone
DROPPED_COLUMNS = {}
SVM_RBF_PARAM_GRID = {'C': [0.1, 1, 10, 100], 'gamma': [1, 0.1, 0.01, 0.001]}
SVM_LINEAR_PARAM_GRID = {'C': [0.1, 1, 10, 100]}
RF_PARAM_GRID = {'n_estimators': [100, 200, 300], 'max_depth': [None, 10, 20], 'min_samples_split': [2, 5, 10]}
SCHEMA_COLUMNS = ['landslide', 'slope', 'aspect', 'elevation', 'curvature', 'twi', 'rainfall',
                  'soil_type', 'lithology', 'lulc', 'dist_roads', 'dist_streams', 'dist_faults']   # twi added 14 Sep
```

The environment variable `LSM_DATA_SOURCE` overrides the data source for one run. Exit artifact names (`models/svm_model.pkl`, `rf_model.pkl`, `scaler.pkl`, `feature_names.json`, `metadata.json`, `data/processed/dataset.csv`) are a fixed contract with Phase 3; never rename them.

---

## 14. How to verify everything works

From the repo root:

```
conda activate landslide
python verify_setup.py               # must end with READY, 0 warnings
python -m src.check_dem              # 14 tiles, 14 Copernicus, all checks passed
python -m src.check_layers           # 11 layers aligned (twi included), nothing missing; exit 0
python -m src.make_synthetic         # 3,600 rows, 1,200 landslide, 2,400 stable
python -m src.eda                    # 5 figures + outputs/eda_report.txt
python -m src.preprocess             # 30 features, SMOTE 1,680/1,680, test 720/359
python -m src.train_svm              # RBF CV 0.8653, test 0.8554
python -m src.train_rf               # CV 0.8956, test 0.8827
python -m src.evaluate               # RF wins, interval +0.0137 to +0.0416
python -m src.demo_map               # 2,145,236 cells scored, about 20 s, map in outputs/
streamlit run dashboard/app.py       # four pages at http://localhost:8501
git status -sb                       # clean, main...origin/main
```

`check_layers` was last run on 14 September 2026 and passed all 11 layers. Training scripts spawn worker processes; on Windows they must stay under `if __name__ == "__main__":`.

---

## 15. Next steps in priority order

1. **User: register on Bhukosh**, and ask the project guide to request the GSI inventory in writing. This unblocks the inventory and lithology, and approval takes days.
2. ~~User: rainfall processing in QGIS~~: done 14 September, `check_layers` 10 of 10.
3. **Done 14 September. Claude: Step 8 dashboard**, `dashboard/app.py`, three pages (four were built) (Overview; Model Comparison with metrics and the ROC figure; Predict with sliders using `prepare_for_prediction()` and both models). Must run with `streamlit run dashboard/app.py`. Function over polish. Builds on synthetic models now.
4. **Done 14 September (`src/demo_map.py`). Claude: Step 9 groundwork**: a script that predicts RF susceptibility over the Rudraprayag grid from the aligned rasters, classifies into the 5 risk zones, renders folium to `outputs/demo_map_rudraprayag.html`, and reports pixel count, time taken and the projected time for the whole state. It can be built and timed now; the real result needs real models.
5. **Day 10, about 25 September: inventory decision** (GSI, or hand-digitised Rudraprayag).
5a. **Done 14 September: TWI added to the schema at the user's request.** Recommended on measured evidence (whole state: VIF 1.64, rank correlation with slope -0.51); TRI not (rank correlation 0.993 with slope, VIF 21.2). The whole-state TWI rehearsal output was copied unchanged to `data/processed/twi.tif`; `state_tri.tif` stayed in the session scratchpad. Steps are in `docs/02_qgis_processing.md` under "TWI and TRI rasters". Updated: config, check_layers, eda, make_synthetic, demo_map, dashboard, the 2f table, README and the data log; Steps 3 to 7 and the Rudraprayag RF map rerun on synthetic data.
6. **User: 2d to 2g** (landslide points, stable points, extraction, export), then `python -m src.label_categories`.
7. Drop any column that cannot be produced (`lithology`, possibly `dist_faults`) through `DROPPED_COLUMNS`, and record why.
8. Set `DEFAULT_DATA_SOURCE = 'real'`, rerun Steps 3 to 7, then Step 9 on real models.
9. Report and viva preparation; keep `docs/PROJECT_STATUS.md` current.

## 16. Timeline

| Working days | Dates (approx.) | Plan |
|---|---|---|
| 1 to 2 | 14 to 15 Sep | Bhukosh registration and GSI request; rainfall raster |
| 3 to 6 | 16 to 21 Sep | Step 8 dashboard and Step 9 groundwork; chase Bhukosh |
| 7 to 10 | 22 to 25 Sep | inventory decision on day 10 |
| 11 to 15 | 28 Sep to 5 Oct | 2d to 2g, dataset.csv, switch to real data, rerun Steps 3 to 7 and 9 |
| 16 to 22 | 6 to 14 Oct | report, figures, limitations, viva preparation |
| 23 to 25 | 15, 16 and 19 Oct | buffer; **deadline Monday 19 October** (2 October is a holiday) |

## 17. How this user likes to work

- Explain **why** before code; every choice gets defended in a viva.
- QGIS guidance is **beginner level, click by click**, with expected numbers and a common-errors table.
- **Rehearse QGIS steps headless on the real data before writing instructions**; several traps were only found that way.
- Label essential versus optional; recommend one option and explain the trade-off rather than listing many.
- Be honest about results and limitations; correct earlier mistakes openly.
- Commit and push every change to GitHub; keep the repository free of data, models and licensed layers.
- Hold the Phase 2 and Phase 3 boundary.
