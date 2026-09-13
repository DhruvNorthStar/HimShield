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
| Built | Steps 0, 0.5, 1, 3, 4, 5, 6, 7 |
| Done in QGIS | 2a, 2b, 2c (roads, streams, faults), land cover, soil, rainfall: **all 10 rasters** |
| Pending | lithology, landslide points, stable points, extraction; Steps 8 and 9 |
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
- `dist_faults` is weak (4.8% of the state within 5 km of a fault, 61% beyond 50 km) and could act as a disguised location; review its importance on real data.
- `data/processed/` holds about 3.8 GB, much of it intermediates; cleanup needs the user's go-ahead.

## 7. Next steps

1. User: Bhukosh registration and the guide's letter to GSI (14 September).
2. Step 8 dashboard and Step 9 groundwork on synthetic models (in progress).
3. Inventory decision on day 10, Friday 25 September.
4. Landslide points, stable points, extraction, export, `label_categories`.
5. Switch to real data, rerun Steps 3 to 7, then Step 9.
