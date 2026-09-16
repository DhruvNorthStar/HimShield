# PROJECT HANDOFF V3: Landslide Susceptibility Mapping for Uttarakhand

Written 16 September 2026 to move the work into a fresh Claude Code session. This file supersedes `PROJECT_HANDOFF.md` (still in the repo, older). Every fact below was checked on disk or in git on 16 September.

---

## 0. Instructions for the new session (read before doing anything)

1. Read this whole file. Then run the five commands in section 7 and report what they show. **Do not change anything until the user says what to do next.**
2. **Hold the Phase 2 / Phase 3 boundary.** Phase 2 is SVM vs Random Forest, the 4-page dashboard, and the Rudraprayag demo map. Phase 3 (full-state prediction, SHAP, dashboard_v2) lives only on the branch `phase3-preparation`. Do not merge it unless the user asks.
3. **Git workflow:** work on `main` unless told otherwise, commit, **push after every commit**, confirm with `git ls-remote origin refs/heads/<branch>`. End every commit message with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`. Author is `DhruvNorthStar <pandeydhruv92@gmail.com>` (the user chose this on purpose; the repo is public).
4. **Never commit data, models or licensed layers** (see `.gitignore`). On `main`, `outputs/figures/shap/` and `outputs/susceptibility_map_uk.html` are untracked leftovers from Phase 3 testing: **never `git add .` on main**.
5. **Never pull GSI data through the BhuSanket website proxy** (it routes around an access control and is not defensible in a viva). This was decided on 12 September and stands.
6. **Rehearse QGIS steps headless on the real data before writing instructions** (section 10), and give QGIS guidance click by click with expected numbers.
7. The user wants the reason before the code, honest reporting of results and mistakes, one recommendation with its trade-off rather than a list, and to confirm before anything irreversible or outside the request.

---

## 1. Snapshot

| | |
|---|---|
| Project | **Landslide Susceptibility Mapping for Uttarakhand**: SVM vs Random Forest. BCA final-year PBL, one person (GitHub `DhruvNorthStar`). The SVM vs RF comparison is the faculty requirement |
| Deadline | **Monday 19 October 2026**: 25 working days from 13 Sep, Mon to Fri, Gandhi Jayanti (2 Oct) a college holiday. 16 Sep is day 3 |
| Phase 2 | **Complete on synthetic data** (pipeline, dashboard, demo map). **Real-data run not started**: the GSI inventory has arrived (section 3) but Steps 2d to 2g are not done |
| Phase 3 | Built and tested on branch `phase3-preparation`, not merged (section 8) |
| Data source in use | `DEFAULT_DATA_SOURCE = "synthetic"` in `src/config.py` |
| Sir meeting | Phase 2 was to be presented to the guide on 16 Sep. Outcome not known to this handoff: **ask the user** |
| Local repo | `C:\Projects\landslide-uttarakhand` (outside OneDrive on purpose) |
| GitHub | https://github.com/DhruvNorthStar/HimShield (public; the repository keeps its old name, the project title changed on 14 Sep) |

### Git state (16 Sep, before this handoff commit)

| Branch | Last commit | Pushed |
|---|---|---|
| `main` (checked out) | `d9fbb0c fix: dashboard cache refreshes after retraining` | yes, equals `origin/main` |
| `phase3-preparation` | `f0a3fbc Add the Phase 3 master pipeline` | yes, equals `origin/phase3-preparation` |

This handoff is committed on `main` on top of `d9fbb0c`. `main` has 2 commits the branch lacks (`aa9a9ef` QGIS dem fix, `d9fbb0c` dashboard cache fix); the branch has 6 commits `main` lacks (section 8). They touch different files, so a merge should be clean.

Recent `main` history:
```
d9fbb0c fix: dashboard cache refreshes after retraining
aa9a9ef fix: point dem layer to dem.tif not the vrt chain
d6b0d92 docs: update Step 9 with corrected SVM map result and both map zone shares
2c638e9 Phase 2 complete on synthetic data: dashboard, demo map, 29 features, RF AUC 0.8767, SVM AUC 0.8541
b584d8b Use the most frequent class as the one-hot reference and retrain
348ee35 Drop dist_faults from the models and retrain on synthetic data
b214e30 Add TWI to the feature schema and retrain on synthetic data
87e9654 Save the QGIS project after rainfall processing
d48336a Add the literature review and tested TWI and TRI steps
bdf655d Record Step 8 and 9 results and warn when map inputs are out of range
c7ee23d Add the Step 8 dashboard and the Step 9 Rudraprayag map script
8ac9455 Record the rainfall raster as done and confirm the 19 October deadline
```

---

## 2. Complete project status

### 2.1 Tracked files on `main`

| Path | Purpose |
|---|---|
| `PROJECT_HANDOFF_V3.md` | this file |
| `PROJECT_HANDOFF.md` | older briefing (14 Sep); keep, but this file is current |
| `README.md`, `CONTRIBUTING.md` | overview, Windows setup, pipeline commands, schema, dropped columns; solo git workflow |
| `docs/01_data_sourcing.md` | Step 1: sources, portals, fallbacks, the DEM decision |
| `docs/02_qgis_processing.md` | Step 2 click by click, rehearsed on real data: 2a DEM, 2b terrain, 2c roads/streams/faults, TWI and TRI, rainfall, land cover and soil, **2d landslide points, 2e stable points, 2f extraction, 2g export** |
| `docs/data_sources_log.md` | provenance per dataset (report data section) |
| `docs/PROJECT_STATUS.md` | living status document (last updated 14 Sep; see section 4.9 for stale lines) |
| `docs/literature_review.md` | primary reference Chauhan, Gupta and Dixit (2025), comparison table, defensible contribution, TWI/TRI measurements |
| `src/config.py` | single source of truth: paths, schema, `DROPPED_COLUMNS`, seed, grids, risk zones |
| `src/get_open_data.py` | no-account downloads: boundary, dem, lulc, soil, rainfall, faults, roads |
| `src/check_dem.py`, `src/check_layers.py` | DEM tile check; every raster on the dem.tif grid with sane ranges |
| `src/label_categories.py` | Step 2g: QGIS CSV to `data/processed/dataset.csv` |
| `src/make_synthetic.py` | synthetic dataset with the exact schema |
| `src/eda.py`, `src/preprocess.py`, `src/train_svm.py`, `src/train_rf.py`, `src/evaluate.py` | Steps 3 to 7 |
| `src/demo_map.py` | Step 9 Rudraprayag map (`--model svm` for SVM) |
| `src/viz.py`, `src/artifacts.py` | figure style and watermark; metadata and feature-name writers |
| `dashboard/app.py` | Step 8, 4 pages: Overview, Model Comparison, Predict, Rudraprayag Map |
| `verify_setup.py` | environment check, must print READY |
| `notebooks/01_eda.ipynb` | thin notebook over `src/eda.py` |
| `environment.yml`, `environment.lock.yml`, `requirements.txt` | Phase 2 environment (install from the lock) |
| `.gitignore`, `.gitattributes`, `.streamlit/config.toml` | ignore rules; LF + nbstripout; light theme, usage stats off |
| `uttarakhand.qgz` | QGIS project; `dem` layer now points at `data/processed/dem.tif` (fixed 15 Sep) |
| `data/processed/dataset_synthetic.csv` (+ `.README.txt`) | 3,600 synthetic rows (1,200 landslide, 2,400 stable) |
| `data/processed/quickosm_extents/roads_part_1..6.gpkg` | QuickOSM rectangles |
| `outputs/eda_report.txt`, `outputs/evaluation_report.txt`, `outputs/figures/*.png` (9) | synthetic reports and figures, watermarked |
| `dashboard/.gitkeep`, `models/.gitkeep`, `notebooks/.gitkeep`, `data/*/.gitkeep`, `src/__init__.py` | placeholders |

### 2.2 The raster stack: 11 layers, all aligned (`check_layers` passed on 15 Sep)

Grid for every layer: **11,123 x 10,135 cells, 30 m, EPSG:32644, extent 170670 to 504360 E, 3177720 to 3481770 N.** Files in `data/processed/`.

| Layer | File | Range | Size | Notes |
|---|---|---|---|---|
| elevation | `dem.tif` | 184 to 7,800.55 m | 145 MB | Copernicus GLO-30, 14 tiles, bilinear to 30 m, Float32, NoData -9999 |
| slope | `slope.tif` | 0 to 80.16 deg | 274 MB | GRASS r.slope.aspect |
| aspect | `aspect.tif` | -1 to 360 | 451 MB | GRASS convention converted; 4,107,242 flat cells = -1 |
| curvature | `curvature.tif` | -6.61 to 6.74 | 451 MB | profile curvature x 100 |
| twi | `twi.tif` | 1.30 to 32.63 | 448 MB | GRASS r.watershed topographic index, multiple flow direction; Float64, NoData NaN (0.12% inside the state, border rim); added 14 Sep |
| rainfall | `rainfall.tif` | 390 to 2,520 mm (grid); 506 to 2,519 inside the state | 60 MB | CHIRPS mean 2009 to 2024, bilinear |
| dist_roads | `dist_roads.tif` | 0 to 100,360 m | 451 MB | OSM roads, 10 km margin |
| dist_streams | `dist_streams.tif` | 0 to 111,522 m | 451 MB | streams from r.watershed threshold 1,000 cells |
| dist_faults | `dist_faults.tif` | 0 to 275,434 m | 451 MB | 8 GEM faults; **dropped from the models** (section 5) |
| lulc | `lulc.tif` | codes 10 to 100 | 15 MB | ESA WorldCover 2021, Mode resampling |
| soil | `soil.tif` | codes 0 to 29 | 5 MB | SoilGrids WRB, nearest; code 0 = "No soil (rock or ice)" |

Not built: **lithology** (needs a GSI geology map), **NDVI** (not started), TRI (measured and rejected). Intermediates also in `data/processed/` (deletable only with the user's agreement): `aspect_grass.tif`, `curvature_raw.tif`, `streams.tif`, `streams_raw.tif`, `drainage.tif`, `roads_rast.tif`, `faults_rast.tif`, `rain_mean.tif`, `dem_rudraprayag.tif`, `dem*.vrt`, `faults_clip.gpkg`, `faults_no_fold.gpkg`, `state_buffer_50km.gpkg`, `rudraprayag_boundary.gpkg`, `prepared.joblib`. `data/processed/` totals 4.3 GB.

Vectors in `data/shapefiles/` (EPSG:32644): `uttarakhand_boundary.gpkg` (53,418 km2), `uttarakhand_districts.gpkg` (13 districts, field `district`; Rudraprayag 1,936 km2), `roads.gpkg` (27,312 segments), `faults.gpkg` (8 GEM faults). **`landslides.gpkg` and `non_landslides.gpkg` do not exist yet.**

### 2.3 Models (`models/`, SYNTHETIC data, not findings about Uttarakhand)

Files: `svm_model.pkl`, `rf_model.pkl`, `scaler.pkl`, `feature_names.json` (29 features), `metadata.json`. Trained 14 Sep 18:59 to 19:01.

| | SVM (RBF) | Random Forest |
|---|---|---|
| **Test AUC** | **0.8541** | **0.8767** |
| CV AUC | 0.8678 | 0.8916 |
| Average precision | 0.7182 | 0.7704 |
| Accuracy / precision / recall / F1 at 0.5 | 0.767 / 0.625 / 0.752 / 0.683 | 0.789 / 0.667 / 0.730 / 0.697 |
| Landslides missed at 0.5 | 89 of 359 | 97 of 359 |
| Youden threshold (recall) | 0.38 (0.844) | 0.32 (0.905) |
| Best parameters | C=10, gamma=0.01 | max_depth None, n_estimators 300, min_samples_split 10 |

- RF minus SVM AUC **+0.022** (bootstrap mean +0.0224; point difference +0.0226), 95% interval **+0.0082 to +0.0386**, separable. Linear SVM test AUC 0.8414, RBF gain +0.0126.
- Test set 1,079 rows (359 landslide), never resampled. Train 2,516 (836 landslide), SMOTE to 1,680/1,680 inside folds.
- Highest VIF 3.29 (elevation), nothing dropped. Reference classes: soil Cambisols, lithology Phyllite, land cover Forest.
- RF top features (impurity / permutation): slope 0.2400 / 0.1180, rainfall 0.1605 / 0.0551, elevation 0.1298 / 0.0224, dist_roads 0.0767 / 0.0120, curvature 0.0703 / 0.0098; twi 6th and 7th of 29.

**The 29 features, in order:** slope, elevation, curvature, twi, rainfall, dist_roads, dist_streams, aspect_sin, aspect_cos, soil_type_Fluvisols, soil_type_Glacier, soil_type_Leptosols, soil_type_Luvisols, soil_type_Regosols, lithology_Alluvium, lithology_Conglomerate, lithology_Gneiss, lithology_Granite, lithology_Limestone, lithology_Quartzite, lithology_Sandstone, lithology_Schist, lithology_Shale, lulc_Agriculture, lulc_Barren, lulc_Builtup, lulc_Grassland, lulc_Scrub, lulc_Snow. (Category names are synthetic; with real data they become WorldCover and SoilGrids names and the list changes.)

History of the synthetic runs on 14 Sep:

| Run | Features | SVM | RF | RF minus SVM (95%) |
|---|---|---|---|---|
| Original | 29 | 0.8304 | 0.8682 | +0.0379 (+0.0234 to +0.0529) |
| TWI added | 30 | 0.8554 | 0.8827 | +0.0271 (+0.0137 to +0.0416) |
| dist_faults dropped | 29 | 0.8577 | 0.8862 | +0.0284 (+0.0140 to +0.0430) |
| Most frequent class as reference (current) | 29 | 0.8541 | 0.8767 | +0.0224 (+0.0082 to +0.0386) |

### 2.4 Dashboard and demo maps (Phase 2, on `main`)

- `streamlit run dashboard/app.py` (port 8501): 4 pages, browser-tested 15 Sep, no errors. Title "Landslide Susceptibility Mapping for Uttarakhand"; homepage "SYNTHETIC DATA: RESULTS ARE NOT FINAL" banner, watermark on every page. Cache bug fixed 15 Sep (loaders take `stamp`, not `_stamp`).
- `outputs/demo_map_rudraprayag.html` (RF, 19.5 s): zones Very Low 61.9%, Low 29.9%, Moderate 7.1%, High 1.0%, Very High 0.0%; 2,145,236 cells scored, 6,105 water skipped.
- `outputs/demo_map_rudraprayag_svm.html` (305.8 s): Very Low 77.8%, Low 15.8%, Moderate 5.0%, High 1.3%, Very High 0.1%.
- **Both maps need internet** (Leaflet from CDNs and basemap tiles). The Phase 2 dashboard has no offline fallback; `dashboard_v2` does.

---

## 3. GSI landslide inventory status

| | |
|---|---|
| File | `data/raw/landslides/GSI_Landslide_Inventory.shp.zip` (5.2 MB, dated 15 Sep 2026 23:51). Inside: `.shp`, `.shx`, `.dbf` (184 MB), `.prj` |
| Provenance | **Not recorded yet.** Before it is used, write the download route, date and terms into `docs/data_sources_log.md` and confirm it did not come through the BhuSanket proxy (section 0, rule 5). Ask the user how it was obtained |
| CRS | WGS 84 geographic (CRS84, longitude/latitude) |
| Geometry | **30,842 points**, all India, no empty geometries |
| Inside Uttarakhand | **5,201** points (point within the state boundary) |
| Per district | Garhwal 811, Uttarkashi 699, Tehri Garhwal 661, Chamoli 643, Nainital 402, Bageshwar 369, Almora 352, Dehradun 351, Pithoragarh 343, **Rudraprayag 310**, Champawat 242, Hardwar 9, Udham Singh Nagar 0 |
| Duplicates | 86 duplicate geometries inside the state, so about 5,115 unique points |
| Useful fields | `SLIDE_NO`, `STATE`, `DISTRICT`, `MATERIAL_T` (Rock, Debris, Rock cum Debris, Earth, Soil), `MOVEMENT_T` (Slide, Flow, Fall, ...), `TRIGGERING` (mostly rainfall), `INITIATION` (year, 0 = unknown), `ACTIVITY`, `LS_AREA`, `GEOLOGY` (free text), plus `LONGITUDE`/`LATITUDE` |
| Processing done | **None.** Only inspected read-only on 16 Sep |

**Warning for feature design:** `GEOLOGY`, `LANDUSE_LA`, `GEOMORPHOL` and similar attributes exist only at landslide points, never at stable points, so they must **never** become model features (perfect class leak). Lithology still needs a geology map that covers the whole state.

Comparison: Chauhan et al. (2025) used 7,182 GSI points for Uttarakhand (polygons converted to points, landslides under 900 m2 removed). This file is points only, so no polygon step and no area filter are needed.

**Still to do with it:** record provenance; Step 2d (section 4.2); decide the NASA question (4.6); regenerate everything on real data (4.8).

---

## 4. Pending tasks in priority order

### 4.1 Record GSI provenance (first, 10 minutes)
Add a row to `docs/data_sources_log.md` replacing the provisional NASA-only situation: source (Bhukosh download or official request), date 15 Sep 2026, file, 30,842 points national / 5,201 in the state, terms of use. Commit.

### 4.2 Step 2d: landslide points (QGIS or a script; rehearse headless first)
From `docs/02_qgis_processing.md` section 2d, adapted to a point file:
1. Unzip `GSI_Landslide_Inventory.shp.zip` (or load `zip://...!GSI_Landslide_Inventory.shp`). The layer CRS is WGS 84 geographic.
2. Reproject to **EPSG:32644**.
3. `native:clip` to `data/shapefiles/uttarakhand_boundary.gpkg` (expect **5,201**).
4. It is already points: skip `native:pointonsurface`.
5. `native:deleteduplicategeometries` (expect about **5,115**; 86 duplicates).
6. Field calculator: integer `landslide` = 1. Keep an id field (`SLIDE_NO`) for traceability; drop the attribute columns from any feature use.
7. Save `data/shapefiles/landslides.gpkg`, note the count.

Expected dataset size at 1:2: about **5,115 landslide + 10,230 stable = 15,345 rows**, about 10,700 training rows. SVM grid search at that size will take many minutes on this i3 (`train_svm.py` warns above 8,000 rows); plan for it.

### 4.3 Step 2e: stable (non-landslide) points
1. `native:buffer` the landslide points by **500 m**, dissolve.
2. Water mask: Raster Calculator `"lulc@1" = 80`, `gdal:polygonize`, buffer 50 m.
3. `native:difference`: state boundary minus landslide buffers, minus water polygons.
4. `native:randompointsinpolygons`: **2 x landslide count** points, **minimum distance 500 m**.
5. Field calculator `landslide` = 0. Save `data/shapefiles/non_landslides.gpkg`.

### 4.4 Step 2f: extract raster values
1. `native:mergevectorlayers` the two files into `all_points.gpkg` (EPSG:32644); count = positives + negatives; `landslide` only 1 and 0.
2. `native:rastersampling` once per raster, chaining outputs, prefixes exactly: `slope.tif`->`slope`, `aspect.tif`->`aspect`, `dem.tif`->`elevation`, `curvature.tif`->`curvature`, `twi.tif`->`twi`, `rainfall.tif`->`rainfall`, `dist_roads.tif`->`dist_roads`, `dist_streams.tif`->`dist_streams`, `dist_faults.tif`->`dist_faults` (still extracted; the models ignore it), `lulc.tif`->`lulc`, `soil.tif`->`soil`. QGIS appends `1`; `label_categories.py` strips it.
3. Lithology by `native:joinattributesbylocation` (predicate within) **only if a geology polygon layer exists**; otherwise decide 4.7.
4. Check the attribute table: no all-NULL column; slope 0 to about 75; elevation about 200 to 7,800; distances from 0; rainfall hundreds to a few thousand; few NULLs, near the edges.

### 4.5 Step 2g: export and label
1. Export `all_points` as CSV, no geometry: `data/processed/dataset_raw.csv`.
2. `python -m src.label_categories data/processed/dataset_raw.csv` (maps codes to names, renames columns, -9999 to missing, validates the schema) writes `data/processed/dataset.csv`.
3. Set `DEFAULT_DATA_SOURCE = "real"` in `src/config.py`; commit config (the CSV stays untracked unless the user decides otherwise).

### 4.6 GSI + NASA merge: PROPOSAL, not decided
Recommendation: **train on GSI only; keep NASA as a map overlay, not training data.**
- NASA GLC in the state: 205 points; location accuracy 1 km 28, 5 km 57, 10 km 27, 25 km 40, 50 km 35, unknown 16. At a 30 m grid, a point placed 5 to 50 km wrong samples the wrong slope entirely: label noise, not signal.
- GSI gives about 5,115 points with field-surveyed locations, 25 times the NASA count.
- If more positives are wanted: add only NASA points with accuracy "1km" (28) that lie more than 500 m from every GSI point, flag them with a `source` field, and report the count. Negligible gain; probably not worth defending.
- Map overlay: `src/map_generator_full.py` (branch) switches automatically to `data/shapefiles/landslides.gpkg` once 2d creates it.

### 4.7 Lithology: decision pending
The `lithology` column is in the schema but no whole-state geology layer exists. Options: (a) get the GSI geology map from Bhukosh (1:2M or finer) and use the spatial join in 4.4; (b) add `lithology` to `DROPPED_COLUMNS` with the reason and record it in the README. Do not use the GSI inventory's `GEOLOGY` text (landslide-only, leak). For full-state prediction (Phase 3) lithology would also need a `lithology.tif` on the dem grid plus a code change in `src/demo_map.py` `RASTERS`.

### 4.8 NDVI: PROPOSAL, not started
Chauhan et al. (2025) used Sentinel-2 NDVI at 10 m. Proposed route:
1. Source: Sentinel-2 L2A from the Copernicus Data Space Ecosystem (free account), one cloud-free dry-season median composite (for example October 2023 to March 2024); NDVI = (B8 - B4) / (B8 + B4). Alternative with no scene handling: MODIS MOD13Q1 250 m (NASA Earthdata login), coarser.
2. Warp to the dem grid: EPSG:32644, 30 m, **average** resampling (continuous value), extent from `dem`, Float32, DEFLATE.
3. Before adding it, measure it as TWI and TRI were measured: rank correlation and VIF against the current factors on a whole-state grid sample. It may overlap with land cover (Tree cover). Add only if VIF stays well under 10.
4. If added, the schema change touches: `src/config.py` (`SCHEMA_COLUMNS`, `NUMERIC_FEATURES`, `FEATURE_UNITS`), `src/check_layers.py`, `src/eda.py` ranges, `src/make_synthetic.py`, `src/demo_map.py` `RASTERS`, `dashboard/app.py` `FACTORS` and `INPUT_GROUPS`, the 2f table in the guide, README schema, data log; then retrain.
Ask the user before starting: it needs a download account and adds a factor late.

### 4.9 Real ML pipeline (after 4.5)
```
python -m src.check_layers
python -m src.eda
python -m src.preprocess
python -m src.train_svm        (long at ~10,700 rows; warn the user first)
python -m src.train_rf
python -m src.evaluate
python -m src.demo_map
python -m src.demo_map --model svm
streamlit run dashboard/app.py
```
Then: re-check VIF on the real sample points (confirm the `dist_faults` drop still holds; note the new reference classes, likely Tree cover for land cover); read EDA leak warnings; update `docs/PROJECT_STATUS.md`, README metrics, and `docs/literature_review.md` (real AUCs, compare with Chauhan et al. RF 90.94%, which used a different inventory handling and split). The synthetic watermark and banners disappear automatically.

Stale lines to fix in `docs/PROJECT_STATUS.md` when next editing it: "The dem layer in uttarakhand.qgz still points at dem.tif.vrt" (fixed 15 Sep), the open-issue about the Phase 2 dashboard cache (fixed 15 Sep), "GSI inventory blocking" (arrived 15 Sep).

### 4.10 Phase 2 report
**No report document exists in the repository** (only `outputs/eda_report.txt` and `outputs/evaluation_report.txt`). Material ready for it: `docs/literature_review.md`, `docs/data_sources_log.md`, `docs/02_qgis_processing.md` (methods), decisions in section 5 below, figures in `outputs/figures/`. Ask the user where the report is being written and what format the college wants. Timeline plan: report writing 6 to 14 Oct, buffer 15, 16, 19 Oct.

### 4.11 Housekeeping (ask first; nothing urgent)
- `data/raw/lulc/` holds five `ESA_WorldCover_* - Copy.tif` duplicates (about 470 MB) created outside the pipeline.
- `data/processed/` intermediates (4.3 GB total); five 451 MB rasters could be recompressed losslessly.
- Merge or cherry-pick nothing into `phase3-preparation` unless asked; it lacks `aa9a9ef` and `d9fbb0c`.

---

## 5. Decisions made, with reasons

| Decision | Reason |
|---|---|
| Repo in `C:\Projects`, not OneDrive | OneDrive locks `.git` and syncs gigabytes of rasters |
| Miniforge conda, Python 3.11, lock file | GDAL, GEOS and PROJ as one matched binary set; exact pins unsolvable, so minor pins plus a lock |
| Copernicus GLO-30, not SRTM | SRTM left 766 km2 of voids inside the state (476 in Uttarkashi) and 2 missing tiles (`data/raw/dem_srtm_unused/WHY_UNUSED.txt`) |
| geoBoundaries boundary | Survey of India needs a login; swap in the official boundary at the same paths if obtained |
| EPSG:32644 for everything, 30 m | metric grid; 0.1% scale error at the west edge beats a zone seam through the state |
| Soil code 0 = "No soil (rock or ice)" | SoilGrids fill: 11.3% of the state at median 5,224 m; calling it missing would fill glaciers with Cambisols |
| CHIRPS 2009 to 2024 only | 2005 to 2008 sit 42.7% lower, pattern r = 0.52, and drought year 2009 beats all four: a record shift. CHIRPS has about 2,000 cells in the state against 80 IMD points |
| Mode for land cover, nearest for soil, bilinear for rainfall | never average class codes |
| Roads: tiled Overpass, 10 km margin, road classes only | QuickOSM timed out; border cells need roads beyond the border; tracks are not road cuts |
| Streams from the DEM, threshold 1,000 cells (0.9 km2) | aligned with terrain |
| Faults: clip in lat/long first, 50 km area, anticline removed | global reprojection produced infinite coordinates |
| **TWI added (14 Sep)** | whole state: rank correlation with slope -0.51, VIF 1.64 (1.73 on the full real feature set); adds wetness information |
| **TRI rejected (14 Sep)** | rank correlation with slope 0.993, VIF 21.2: a copy of slope at 30 m |
| **`dist_faults` dropped (14 Sep)** | on a whole-state grid sample elevation VIF was 14.48 because elevation tracks dist_faults (rank r 0.90); without it elevation falls to 7.82. dist_faults' own VIF was 8.87, **under 10**: the drop is a judgement, not an automatic VIF result. Step 4's rule would have dropped elevation (VIF 14.44) instead. GEM holds 8 faults near the state and misses the Main Central Thrust: every Rudraprayag cell is 55.7 to 127.1 km from a mapped fault. Restore if GSI fault lines arrive |
| **One-hot reference = most frequent class (14 Sep)** | pandas `drop_first` used the alphabetically first class ("Bare/sparse vegetation", 8.5% of the state), pushing `lulc_Tree cover` to VIF 10.1; with Tree cover as reference no land-cover column exceeds 4.7. Applied to soil, lithology and land cover; recorded in `metadata.json` `preprocessing.categorical_reference_levels` |
| VIF threshold 10, drop worst one at a time | standard; removing one feature often rescues its partner |
| Aspect as sine and cosine, flat = (0, 0) | aspect is circular |
| 1:2 landslide to stable points | 1:1 leaves SMOTE nothing to do; wider ratios let imbalance dominate and slow SVM |
| 500 m buffer around landslides for stable points | ground beside a landslide is not stable (about 17 cells) |
| Water excluded from stable points; water rows dropped in Step 4 | a lake is not stable terrain; a water row could then only be a landslide (leak) |
| Stratified 70/30 split, seed 42 everywhere | reproducibility |
| Scaler fitted on training rows only | the test set must stand in for unseen data |
| **SMOTE after the split and inside each CV fold** (imblearn pipeline) | resampling before CV measured CV 0.92 vs test 0.69 and picked gamma=1 (memorisation) |
| AUC as headline, plus average precision; metrics at 0.5 and Youden | accuracy is near useless at 1:2 (always "stable" scores 67%) |
| Bootstrap 95% interval on the RF-SVM AUC gap (1,000 resamples) | a model is "better" only if the interval excludes zero |
| Linear SVM fitted as a check | tests, rather than assumes, that RBF non-linearity helps |
| Risk zones at fixed breaks 0.2 / 0.4 / 0.6 / 0.8 | natural breaks and quantiles change per map and model; fixed breaks compare directly |
| Map colours: one vermillion ramp, light to dark | ordered classes; green-to-red fails colour-blind readers; validated; same on district and state maps |
| Water cells skipped on maps; synthetic class bridge only while synthetic | models never saw water; synthetic class names differ from WorldCover/SoilGrids |
| Synthetic data first | Steps 3 to 9 built and tested before real data; switching is one config line |
| No GSI data via the BhuSanket proxy | it circumvents an access control |

Known limitations to state in the report: stable means "no recorded landslide"; random split ignores spatial autocorrelation (scores likely optimistic); rainfall is a 16-year annual mean at about 5.5 km; lithology missing; `dist_faults` weak.

---

## 6. Environment

| Item | Value |
|---|---|
| Machine | Windows 11 Home, 7.7 to 8.2 GB RAM (often only about 1 GB free), 4-thread i3 |
| Conda | Miniforge at `%USERPROFILE%\miniforge3`, conda 26.7.2 |
| Environment | **`landslide`**, Python 3.11.16 |
| Core | numpy 2.2.6, pandas 2.3.3, scipy 1.15.2, scikit-learn 1.7.2, imbalanced-learn 0.14.2, statsmodels 0.14.6, joblib 1.5.3 |
| Geo | rasterio 1.4.4, libgdal-core 3.12.3, geopandas 1.1.4, shapely 2.1.2, pyproj 3.7.2, pyogrio 0.11.1 |
| Viz and apps | matplotlib 3.10.9, seaborn 0.13.2, folium 0.20.0, streamlit 1.49.1, altair 5.5.0, pillow 11.3.0 |
| Phase 3 additions (in the same env) | shap 0.51.0, numba 0.67.0, llvmlite 0.49.0, cloudpickle 3.1.2, slicer 0.0.8, tqdm 4.70.1 (pinned in `environment.phase3.yml`, branch only); psutil 7.2.2 already present |
| Tools | nbstripout 0.8.2 (filter installed), ipykernel 6.29.5 |
| QGIS | 3.44.12 LTR at `C:\Program Files\QGIS 3.44.12`, GRASS provider enabled in the user's profile |

### Known Windows issues (all hit already)
- **Always activate the env** or use `conda run -n landslide`. A stale `pip --user` numpy 1.25 in `AppData\Roaming\Python\Python311` shadows the env when `python.exe` is called directly (use `-s`). The env sets `PYTHONNOUSERSITE=1`.
- `conda run ... python -c` breaks on multi-line code **and eats `%` characters**; write a script file in the session scratchpad instead.
- `conda run` re-prints output in cp1252: printing non-ASCII (Indian place names, GSI text fields) crashes it. Print ASCII only, or `sys.stdout.reconfigure(encoding="ascii", errors="backslashreplace")`.
- `conda run` prints "ERROR conda.cli.main_run ... failed" whenever the script exits non-zero; that is the wrapper, not a new error.
- Bash tool is Git Bash; PowerShell is 5.1 (strips double quotes to native programs).
- Training scripts must keep code under `if __name__ == "__main__":` (n_jobs=-1 worker processes).
- Streamlit preview servers sometimes survive a stop: check `Get-CimInstance Win32_Process -Filter "Name='python.exe'"` and stop only processes whose command line is ours.
- The in-app browser refuses `file://` pages; serve `outputs/` with `python -m http.server --bind 127.0.0.1`.
- GDAL block cache can take about 410 MB unseen; Phase 3 scripts cap `GDAL_CACHEMAX=256`.
- Pillow 13 (due 15 Oct 2026) removes `Image.fromarray(..., mode=...)`; `map_generator_full.py` already uses `Image.frombytes`.

### Headless QGIS (how every QGIS step was rehearsed)
```
cd "/c/Program Files/QGIS 3.44.12/bin"
echo '{"inputs": {...}}' | ./qgis_process-qgis-ltr.bat run <algorithm> -
```
Launcher `qgis_process-qgis-ltr.bat`. GRASS algorithms need a throwaway profile folder with `profiles/default/QGIS/QGIS3.ini` containing `[PythonPlugins]` `grassprovider=true`, pointed to by `QGIS_CUSTOM_CONFIG_PATH`; delete it afterwards; never edit the user's profile. Use forward-slash paths in the JSON (backslashes break it). Extent string `"170670,504360,3177720,3481770 [EPSG:32644]"`. PyQGIS scripts run with `"/c/Program Files/QGIS 3.44.12/bin/python-qgis-ltr.bat" script.py`. Rehearse in the scratchpad, never over `data/processed/`.

---

## 7. Exact first commands for the new session

Run from `C:\Projects\landslide-uttarakhand` (Git Bash) and report the output:

```
"$USERPROFILE/miniforge3/condabin/conda.bat" run -n landslide python verify_setup.py
```
Expect `READY: all checks passed (0 warning(s)).`

```
git status -sb && git log --oneline -3 && git ls-remote origin refs/heads/main refs/heads/phase3-preparation
```
Expect `## main...origin/main`, untracked `outputs/figures/shap/` and `outputs/susceptibility_map_uk.html` only, local main equal to origin.

```
"$USERPROFILE/miniforge3/condabin/conda.bat" run -n landslide python -m src.check_layers
```
Expect 11 layers aligned, exit 0.

```
"$USERPROFILE/miniforge3/condabin/conda.bat" run -n landslide python -B -c "import json; m=json.load(open('models/metadata.json')); e=m['evaluation']; print(m['data_source'], {k: v['auc'] for k, v in e['models'].items()}, e['auc_difference_rf_minus_svm'])"
```
Expect `synthetic {'SVM (RBF)': 0.8541, 'Random Forest': 0.8767} {... 'ci_low': 0.0082, 'ci_high': 0.0386 ...}`.

```
ls -la data/raw/landslides/ data/shapefiles/
```
Expect `GSI_Landslide_Inventory.shp.zip` present and **no** `landslides.gpkg` yet (unless the user has since run Step 2d).

### Key paths
- Repo `C:\Projects\landslide-uttarakhand`; config `src/config.py`; guide `docs/02_qgis_processing.md`; status `docs/PROJECT_STATUS.md`
- GSI zip `data/raw/landslides/GSI_Landslide_Inventory.shp.zip`; NASA `data/raw/landslides/global_landslide_catalog_NASA.shp`
- Rasters `data/processed/*.tif`; boundaries `data/shapefiles/uttarakhand_boundary.gpkg`, `uttarakhand_districts.gpkg`
- Step 2 outputs to create: `data/shapefiles/landslides.gpkg`, `data/shapefiles/non_landslides.gpkg`, `data/processed/dataset_raw.csv`, `data/processed/dataset.csv`
- Models `models/`; figures `outputs/figures/`; demo maps `outputs/demo_map_rudraprayag.html`, `outputs/demo_map_rudraprayag_svm.html`

### Commands for the user
- Phase 2 dashboard: `conda activate landslide` then `streamlit run dashboard/app.py` (http://localhost:8501)
- Rudraprayag map: `start outputs\demo_map_rudraprayag.html` (needs internet)
- Show the Phase 3 branch: `git branch -a`

---

## 8. Phase 3 status (branch `phase3-preparation`, head `f0a3fbc`, pushed)

| Commit | File | What it does and how it was tested |
|---|---|---|
| `34e9841` | `src/verify_phase2.py` | 60 read-only checks (env, artifacts, models load, feature contract, metadata, sample prediction, AUC recomputed from `prepared.joblib`, rasters on grid, code parses); synthetic: 58 OK, 2 WARN, 0 FAIL; exits 1 on FAIL (tested with real data selected) |
| `00b9bba` | `src/explain_shap.py`, `environment.phase3.yml`, `.gitignore` | SHAP TreeExplainer on RF, 500 stratified held-out points, 18.8 s, additivity error 1.7e-14, top 7 match permutation ranking; beeswarm, bar, 3 dependence, force plot to `outputs/figures/shap/` (ignored on the branch) |
| `919c04b` | `src/predict_raster_full.py` | strip-chunked RF prediction, `--district NAME` or `--state` (warns, needs `--yes`), `--estimate-only`; outputs `data/processed/susceptibility_<area>_probability.tif` and `_zones.tif`; Rudraprayag identical to the Phase 2 map cell for cell; 19.5 s; peak memory planned 0.72 GB vs measured 0.72 GB; state projected about 8 min, about 59.4 million cells; **state never run** |
| `6a6976d` | `src/map_generator_full.py` | `outputs/susceptibility_map_uk.html`; palette-PNG zones, click lookup, layers (zones, landslides, districts, state, OSM/satellite); fallback to Rudraprayag when the state raster is missing (0.97 MB, browser-tested); switches to `landslides.gpkg` automatically |
| `0c40b07` | `dashboard_v2/app.py` | 6 pages reusing `dashboard/app.py` (loaded without its `main()` call): Overview, Model Comparison, Predict (RF vs SVM probability bars), Rudraprayag Map, Explainability, Full State Map; offline static-map fallback (`?offline=1` to test); browser-tested |
| `f0a3fbc` | `run_phase3.py` | runs verify, SHAP, state raster (asks [y/N]), map; skips up-to-date steps; `--dry-run`, `--yes`, `--force`; exit codes 0/1/2/3/130; tested |

Not on the branch yet: `aa9a9ef` and `d9fbb0c` from `main`.

**Run Phase 3 when ready** (after the real models exist on `main` and are merged, or on the branch for testing):
```
conda env update -n landslide -f environment.phase3.yml   (only on a machine without shap)
python run_phase3.py --dry-run
python run_phase3.py
streamlit run dashboard_v2/app.py
```

**Merge plan** (only when the user asks, normally after Phase 2 is submitted and the models on main are retrained on real data):
```
git checkout main
git merge phase3-preparation
python src/verify_phase2.py
streamlit run dashboard_v2/app.py
```
`verify_phase2.py` fails by design if `DEFAULT_DATA_SOURCE = "real"` while models are still synthetic. Lithology needs a raster before full-state prediction can use a real value (section 4.7).

---

## 9. Data sources

| Dataset | Source | File path | Status | Licence |
|---|---|---|---|---|
| State and district boundaries | geoBoundaries gbOpen IND ADM1/ADM2, https://github.com/wmgeolab/geoBoundaries (via `python -m src.get_open_data boundary`) | `data/raw/boundary/geoBoundaries-IND-ADM1.geojson`, `-ADM2.geojson`; built `data/shapefiles/uttarakhand_boundary.gpkg`, `uttarakhand_districts.gpkg` | used | ODbL 1.0 |
| DEM | Copernicus DEM GLO-30, https://copernicus-dem-30m.s3.amazonaws.com | `data/raw/dem/Copernicus_DSM_COG_10_*.tif` (14 tiles); `data/processed/dem.tif` | used | Copernicus licence, attribution |
| SRTM (rejected) | SRTM 1 arc-second | `data/raw/dem_srtm_unused/` (12 tiles, `WHY_UNUSED.txt`) | not used | public domain |
| Land cover | ESA WorldCover 2021 v200, https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ | `data/raw/lulc/ESA_WorldCover_10m_2021_v200_*_Map.tif` (5 tiles, plus 5 "- Copy" duplicates); `data/processed/lulc.tif` | used | CC BY 4.0 |
| Soil | ISRIC SoilGrids WRB most probable, https://maps.isric.org (WCS), legend https://files.isric.org/soilgrids/latest/data/wrb/MostProbable.rat.json | `data/raw/soil/soilgrids_wrb_mostprobable.tif`, `soilgrids_wrb_legend.json`; `data/processed/soil.tif` | used | CC BY 4.0 |
| Rainfall | CHIRPS v2.0 annual, https://data.chc.ucsb.edu/products/CHIRPS-2.0/global_annual/tifs/ | `data/raw/rainfall/chirps-v2.0.2009.tif` to `2024.tif`; `data/processed/rainfall.tif` | used | free; cite Funk et al. 2015 |
| Roads | OpenStreetMap via Overpass, https://overpass-api.de/api/interpreter (mirror maps.mail.ru) | cache `data/raw/osm/roads_tiles/`; `data/shapefiles/roads.gpkg`; `data/processed/dist_roads.tif` | used | ODbL 1.0 |
| Faults | GEM Global Active Faults, https://github.com/GEMScienceTools/gem-global-active-faults | `data/raw/geology/gem_active_faults_harmonized.geojson`; `data/shapefiles/faults.gpkg`; `data/processed/dist_faults.tif` | built, dropped from models | CC BY-SA 4.0 |
| Streams, slope, aspect, curvature, TWI | derived from `dem.tif` with GRASS | `data/processed/*.tif` | used | as the DEM |
| **GSI landslide inventory** | Geological Survey of India (Bhukosh, https://bhukosh.gsi.gov.in); **route to be recorded** | `data/raw/landslides/GSI_Landslide_Inventory.shp.zip` | **arrived 15 Sep, unprocessed** | GSI terms, to record |
| NASA Global Landslide Catalog | NASA GLC via HDX (data.humdata.org) | `data/raw/landslides/global_landslide_catalog_NASA.shp` (+ zip) | provisional; 205 in state; map overlay | CC BY |
| Lithology | GSI geology map via Bhukosh | none | **missing** | - |
| NDVI | Sentinel-2 (Copernicus Data Space) or MODIS MOD13Q1 | none | **not started, proposal only** | - |
| Primary literature | Chauhan V, Gupta L, Dixit J (2025) Geoenvironmental Disasters 12:2, https://doi.org/10.1186/s40677-024-00307-3 | `docs/literature_review.md` | read in full text | open access |

---

## 10. How this user likes to work

- Explain why before code; every choice gets defended in a viva.
- QGIS guidance click by click with expected numbers and an errors table; rehearse headless on the real data first.
- Label essential versus optional; recommend one option with its trade-off.
- Be honest about results, limitations and your own earlier mistakes; correct them openly.
- Commit and push every change; keep data, models and licensed layers out of git.
- When the user says stop, stop background work too, and change nothing until they say proceed.
- One file or one fix at a time when they ask for it; test, report, wait.
