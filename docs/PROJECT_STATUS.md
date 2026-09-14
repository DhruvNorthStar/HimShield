# Project status

Last updated: 14 September 2026, second session. Update this file whenever a decision is made or a dataset arrives. For a full briefing, see [PROJECT_HANDOFF.md](../PROJECT_HANDOFF.md).

## 1. Snapshot

| | |
|---|---|
| Project | HimShield: landslide susceptibility mapping, Uttarakhand, SVM vs Random Forest |
| Phase | 2 of 3, about 75 percent complete |
| Deadline | **Monday 19 October 2026**: 25 working days from 13 September, with Gandhi Jayanti (2 October) a college holiday |
| Repo | https://github.com/DhruvNorthStar/HimShield (public), pushed after every commit |
| Local copy | `C:\Projects\landslide-uttarakhand` |
| Environment | conda env `landslide`, Python 3.11.16 |
| QGIS | 3.44.12 LTR, GRASS provider enabled |
| Data source in use | **synthetic**, until the real CSV exists |
| Built | Steps 0, 0.5, 1, 3, 4, 5, 6, 7, **8 (dashboard)**, **9 groundwork (Rudraprayag map script)** |
| Done in QGIS | 2a, 2b, 2c (roads, streams, faults), land cover, soil, rainfall: **all 10 rasters**, plus `twi.tif` (11 layers, all aligned) |
| Pending | lithology, landslide points, stable points, extraction; Step 9 on real models |
| Team | one person |

## 2. Progress on 14 September 2026

| Item | Result |
|---|---|
| `lulc.tif` | ✅ verified: aligned, codes 10 to 100, class shares match the tested run exactly (tree cover 53.82%, grassland 17.25%, snow and ice 7.82%, water 0.57%) |
| `soil.tif` | ✅ verified: aligned, codes 0 to 29, within 0.05 points of the tested run (Cambisols 45.38%, Luvisols 21.08%, Leptosols 17.38%, no soil 11.27%) |
| `dist_roads.tif` | ✅ verified: 0 to 100,360 m |
| `dist_streams.tif` | ✅ verified: 0 to 111,522 m (redone after an all-zero first attempt) |
| `dist_faults.tif` | ✅ verified: 0 to 275,434 m |
| CHIRPS rainfall | ✅ downloaded; 2009 to 2024 kept (16 files, 880 MB), 2005 to 2008 deleted |
| `rainfall.tif` | ✅ verified: aligned; inside the state 506 to 2,519 mm, median 1,448 mm, no NoData; district medians within 1 mm of the rehearsal; `rain_mean.tif` identical to an independent 2009 to 2024 mean |
| `check_layers` | ✅ passing **all 10 layers**, nothing missing |
| `verify_setup.py` | ✅ READY, 0 warnings (rechecked at the start of the second session) |
| Deadline | ✅ confirmed: Monday 19 October 2026 |
| Bhukosh | ⏳ user registering today, and the project guide's letter to GSI goes out today |
| Literature review | ✅ started: [literature_review.md](literature_review.md), primary reference Chauhan, Gupta and Dixit (2025), *Geoenvironmental Disasters* 12:2, read in full text. Verified there: 7,182 GSI points from Bhukosh, 16 factors at 30 m, stratified random 70/30 split, RF AUC 90.94% (XGBoost 91.36%). Not reported there: how non-landslide points were drawn, class balancing, SVM. Tables still to check in the PDF |
| TWI and TRI | ✅ rehearsed on Rudraprayag and the whole state (TWI 527 s, TRI 22 s), steps in `02_qgis_processing.md`. Whole state: TWI rank correlation with slope -0.51, VIF 1.64 (adds information); TRI rank correlation with slope **0.993**, VIF 21.2 (duplicates slope). Rudraprayag agrees (-0.39 and 1.65; 0.989 and 16.4). **TWI added to the schema on 14 September** (the rehearsed whole-state `twi.tif` copied into `data/processed/`); TRI left out. Synthetic Steps 3 to 7 and the Rudraprayag RF map rerun with 30 features |
| Step 8 dashboard | ✅ `streamlit run dashboard/app.py`: Overview, Model Comparison, Predict, Rudraprayag Map. Every page loaded and the Predict controls tested in a browser, no server errors |
| Step 9 groundwork | ✅ `python -m src.demo_map`: Random Forest scored 2,145,236 cells (6,105 water cells skipped) in 13.6 s, 19.8 s end to end (after retraining with TWI: 9.4 s and 16.5 s); whole state projected at about 4 to 7 min of scoring, 8 to 10 min end to end, but only in tiles (a single pass needs about 14 GB). `--model svm`: 444 s for the same cells (4,827 cells per second, 31 times slower than RF), about 204 min projected for the state. **The synthetic SVM scored every cell 0.000 (all Very Low) while RF spread normally (median 0.247).** Tested: swapping only `dist_faults` for a typical training value restores SVM scores (median 0.117), and keeping only the real `dist_faults` drives them to 0. Real distances there (56 to 127 km) sit 13 to 30 standard deviations beyond the synthetic training data; an RBF kernel decays towards its intercept, trees saturate. A synthetic-data artefact, but `demo_map` now warns when most of the district is out of range |

Also found and fixed today:

- **SoilGrids code 0 is not Acrisols.** It covers 11.3% of the state at a median elevation of 5,224 m, so it is glaciers and bare rock. `src/label_categories.py` now labels it "No soil (rock or ice)", and the earlier "Acrisols 8%" in the data log is corrected.
- **CHIRPS 2005 to 2008 are inconsistent.** 42.7% below 2009 to 2024, spatial match only r = 0.52, and 2009 (a drought year) scores above all four. Only 2009 to 2024 are used; the downloader now defaults to 2009.
- **Repository housekeeping.** Derived QGIS vector layers are ignored, the geoBoundaries-derived Rudraprayag outline was untracked, and the README, CONTRIBUTING and this file were brought in line with the public solo workflow.

## 3. Derived layers

All on one grid: 11,123 × 10,135 cells, 30 m, EPSG:32644.

| Layer | Range | Notes |
|---|---|---|
| dem | 184 to 7,800.55 m | Copernicus GLO-30 |
| slope | 0 to 80.16° | |
| aspect | -1 to 360 | 4,107,242 flat cells |
| curvature | -6.61 to 6.74 | profile curvature × 100 |
| twi | 1.30 to 32.63 | r.watershed topographic index, multiple flow direction; added 14 September |
| dist_roads | 0 to 100,360 m | 27,312 OSM segments, 10 km border margin |
| dist_streams | 0 to 111,522 m | r.watershed threshold 1,000 cells |
| dist_faults | 0 to 275,434 m | 8 GEM faults; weak factor; **dropped from the models 14 September** (raster kept) |
| lulc | codes 10 to 100 | Mode resampling |
| soil | codes 0 to 29 | nearest neighbour; code 0 = no soil |
| rainfall | 390 to 2,520 mm over the grid, 506 to 2,519 inside the state | CHIRPS mean 2009 to 2024, bilinear |

## 4. Results so far (synthetic data, not findings about Uttarakhand)

| | SVM (RBF) | Random Forest |
|---|---|---|
| Best parameters | C=10, gamma=0.01 | unlimited depth, 300 trees, min split 10 |
| CV AUC | 0.8678 | 0.8916 |
| **Test AUC** | 0.8541 | **0.8767** |
| Recall at 0.5 | 0.752 | 0.730 |
| Landslides missed | 89 of 359 | 97 of 359 |

Retrained 14 September with 29 features (TWI added, dist_faults dropped) and the most frequent class of each categorical factor as the one-hot reference (Cambisols, Phyllite, Forest). Highest VIF is now 3.29, down from 5.65.
- RF wins by 0.0224 AUC (bootstrap 95% interval +0.0082 to +0.0386), but at the 0.5 threshold SVM misses fewer landslides. At each model's Youden threshold RF catches more (90.5% against 84.4%).
- RBF beats linear SVM by +0.0126. twi ranks 6th of 29 in RF impurity importance, 7th by permutation.
- Earlier today: original SVM 0.8304 and RF 0.8682; with TWI, SVM 0.8554 and RF 0.8827; after dropping dist_faults, SVM 0.8577 and RF 0.8862. The last change moved RF by less than one standard error (about 0.012), so read it as noise.

## 5. Data status

| Factor | Status |
|---|---|
| DEM, boundary, land cover, soil, roads, faults, rainfall | processed and verified |
| Landslide inventory | **provisional**: NASA GLC, 205 points in the state, only 85 accurate to 5 km. GSI inventory needs Bhukosh |
| Lithology | missing: needs Bhukosh |

## 6. Open issues

- GSI inventory blocking; decision on day 10 (Friday 25 September): GSI data, or hand-digitised Rudraprayag scars.
- Lithology may have to be dropped through `DROPPED_COLUMNS`.
- **VIF on the full real feature set** (whole-state grid sample of 588,997 cells, 14 September; lithology not included). All values below are VIF:
  - **TWI 1.73.**
  - **Elevation 14.5**, above 10, because it tracks `dist_faults`: rank correlation **0.90**. Without `dist_faults`, elevation falls to 7.8.
  - `lulc_Tree cover` 10.1 is an encoding effect. With the most common class (Tree cover) as the reference instead of the first alphabetically, that column disappears and no land-cover column goes above 4.7. **Resolved 14 September at the user's request: Step 4 now leaves out the most frequent class of each categorical factor.**
  - **Step 4's rule would have dropped elevation, the wrong column.** Resolved on 14 September at the user's request: `dist_faults` is in `DROPPED_COLUMNS`; restore it if GSI fault lines arrive.
  - Caveat: Step 4 computes VIF on sample points, not grid cells, so real Step 4 values will differ.
- `dist_faults` is weak (4.8% of the state within 5 km of a fault, 61% beyond 50 km) and could act as a disguised location; review its importance on real data. **Measured 14 September: inside Rudraprayag the nearest GEM fault is 55.7 to 127.1 km away (median 96.3 km)**, although the Main Central Thrust crosses the district; GEM lists active faults only. In the demo district the layer is a regional gradient, not a fault proximity. GSI structural lines from Bhukosh would fix this; otherwise drop it through `DROPPED_COLUMNS`.
- `data/processed/` holds about 3.8 GB, much of it intermediates; cleanup needs the user's go-ahead.

## 7. Next steps

1. User: Bhukosh registration and the guide's letter to GSI (14 September).
2. Step 8 dashboard and Step 9 groundwork on synthetic models (in progress).
3. Inventory decision on day 10, Friday 25 September.
4. Landslide points, stable points, extraction, export, `label_categories`.
5. Switch to real data, rerun Steps 3 to 7, then Step 9.
