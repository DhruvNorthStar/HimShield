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
| Done in QGIS | 2a, 2b, 2c (roads, streams, faults), land cover, soil, rainfall: **all 10 rasters** |
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
| TWI and TRI | ✅ rehearsed on Rudraprayag and the whole state (TWI 527 s, TRI 22 s), steps in `02_qgis_processing.md`. Whole state: TWI rank correlation with slope -0.51, VIF 1.64 (adds information); TRI rank correlation with slope **0.993**, VIF 21.2 (duplicates slope). Rudraprayag agrees (-0.39 and 1.65; 0.989 and 16.4). Recommendation: build TWI and add it to the schema, skip TRI. **Decision pending with the user** |
| Step 8 dashboard | ✅ `streamlit run dashboard/app.py`: Overview, Model Comparison, Predict, Rudraprayag Map. Every page loaded and the Predict controls tested in a browser, no server errors |
| Step 9 groundwork | ✅ `python -m src.demo_map`: Random Forest scored 2,145,236 cells (6,105 water cells skipped) in 13.6 s, 19.8 s end to end; whole state projected at about 6 to 7 min of scoring, 9 to 10 min end to end, but only in tiles (a single pass needs about 14 GB). `--model svm`: 444 s for the same cells (4,827 cells per second, 31 times slower than RF), about 204 min projected for the state. **The synthetic SVM scored every cell 0.000 (all Very Low) while RF spread normally (median 0.247).** Tested: swapping only `dist_faults` for a typical training value restores SVM scores (median 0.117), and keeping only the real `dist_faults` drives them to 0. Real distances there (56 to 127 km) sit 13 to 30 standard deviations beyond the synthetic training data; an RBF kernel decays towards its intercept, trees saturate. A synthetic-data artefact, but `demo_map` now warns when most of the district is out of range |

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
| dist_roads | 0 to 100,360 m | 27,312 OSM segments, 10 km border margin |
| dist_streams | 0 to 111,522 m | r.watershed threshold 1,000 cells |
| dist_faults | 0 to 275,434 m | 8 GEM faults; weak factor |
| lulc | codes 10 to 100 | Mode resampling |
| soil | codes 0 to 29 | nearest neighbour; code 0 = no soil |
| rainfall | 390 to 2,520 mm over the grid, 506 to 2,519 inside the state | CHIRPS mean 2009 to 2024, bilinear |

## 4. Results so far (synthetic data, not findings about Uttarakhand)

| | SVM (RBF) | Random Forest |
|---|---|---|
| Best parameters | C=10, gamma=0.01 | depth 10, 300 trees, min split 2 |
| CV AUC | 0.8602 | 0.8896 |
| **Test AUC** | 0.8304 | **0.8682** |
| Recall at 0.5 | 0.732 | 0.793 |
| Landslides missed | 96 of 358 | 74 of 358 |

RF wins by 0.0379 AUC (bootstrap 95% interval +0.0234 to +0.0529). RBF beats linear SVM by only +0.0090.

## 5. Data status

| Factor | Status |
|---|---|
| DEM, boundary, land cover, soil, roads, faults, rainfall | processed and verified |
| Landslide inventory | **provisional**: NASA GLC, 205 points in the state, only 85 accurate to 5 km. GSI inventory needs Bhukosh |
| Lithology | missing: needs Bhukosh |

## 6. Open issues

- GSI inventory blocking; decision on day 10 (Friday 25 September): GSI data, or hand-digitised Rudraprayag scars.
- Lithology may have to be dropped through `DROPPED_COLUMNS`.
- Schema decision: add `twi` (recommended, measured) and leave out `tri`. Adding a column means updating config, the checker, the synthetic generator, the map script, the dashboard and the Step 2f table, then retraining Steps 3 to 7 on synthetic data.
- `dist_faults` is weak (4.8% of the state within 5 km of a fault, 61% beyond 50 km) and could act as a disguised location; review its importance on real data. **Measured 14 September: inside Rudraprayag the nearest GEM fault is 55.7 to 127.1 km away (median 96.3 km)**, although the Main Central Thrust crosses the district; GEM lists active faults only. In the demo district the layer is a regional gradient, not a fault proximity. GSI structural lines from Bhukosh would fix this; otherwise drop it through `DROPPED_COLUMNS`.
- `data/processed/` holds about 3.8 GB, much of it intermediates; cleanup needs the user's go-ahead.

## 7. Next steps

1. User: Bhukosh registration and the guide's letter to GSI (14 September).
2. Step 8 dashboard and Step 9 groundwork on synthetic models (in progress).
3. Inventory decision on day 10, Friday 25 September.
4. Landslide points, stable points, extraction, export, `label_categories`.
5. Switch to real data, rerun Steps 3 to 7, then Step 9.
