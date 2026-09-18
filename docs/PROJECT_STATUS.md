# Project status

Last updated: 17 September 2026 on branch `phase3-preparation`, with the Phase 3 results (section 9). `main` holds Phase 2 only. Update this file whenever a step finishes or a decision is made. The reasons and measurements behind every item are in [decisions.md](decisions.md).

## 1. Snapshot

| | |
|---|---|
| Project | Landslide Susceptibility Mapping for Uttarakhand: SVM vs Random Forest |
| Phase | **2 of 3: complete on real data.** Pipeline, evaluation, dashboard and both Rudraprayag maps run on the GSI inventory. Phase 2 documentation is complete; the report document remains (section 7) |
| Deadline | Final submission mid-October 2026 |
| Repo | https://github.com/DhruvNorthStar/HimShield (public; the repository keeps its original name), pushed after every commit |
| Local copy | `C:\Projects\landslide-uttarakhand` |
| Environment | conda env `landslide`, Python 3.11.16; QGIS 3.44.12 LTR with GRASS |
| Data source in use | **real** (`DEFAULT_DATA_SOURCE = "real"`, `data/processed/dataset.csv`) |
| Branches | `main` (Phase 2); `phase3-preparation` (Phase 3, not merged) |
| Team | one person |

## 2. Key results (real data)

| | SVM (RBF) | Random Forest |
|---|---|---|
| **Test AUC** | **0.9404** | **0.9604** |
| 5-fold CV AUC | 0.9427 | 0.9618 |
| Average precision | 0.881 | 0.914 |
| Accuracy / precision / recall / F1 at 0.5 | 0.871 / 0.759 / 0.896 / 0.822 | 0.902 / 0.831 / 0.886 / 0.858 |
| Confusion at 0.5 (stable cleared, false alarms, missed, caught) | 2,608 / 430 / 158 / 1,355 | 2,766 / 272 / 172 / 1,341 |
| Best parameters | C 100, gamma 0.01 | 300 trees, max_depth None, min_samples_split 2 |
| Training time (full grid, 5-fold CV) | 10 min 17 s | 4 min 54 s |
| **AUC within 1 km of a road** | **0.907** | **0.934** |
| AUC beyond 1 km (73 landslides) | 0.833 | 0.952 |

- RF minus SVM AUC **+0.0199**, 95% bootstrap interval **+0.0157 to +0.0242** (excludes zero). Within 1 km of a road: +0.027 (+0.020 to +0.035).
- Linear SVM test AUC 0.9265: the RBF kernel adds +0.0139.
- RF importance (impurity / permutation): dist_roads 0.314 / +0.143, elevation 0.160 / +0.051, slope 0.117 / +0.042, ndvi 0.099 / +0.018, rainfall 0.058 / +0.008.
- Wording for the report: "AUCs comparable to Chauhan et al. (2025), with road-survey bias quantified by a near-road check (RF 0.934 within 1 km of roads)". No claim of higher accuracy.

| Data | Count |
|---|---|
| Features (model inputs) | **23** |
| Rows in `dataset.csv` | 15,189 (5,063 landslide, 10,126 stable) |
| Rows used after preprocessing | **15,169** (20 water rows dropped) |
| Training rows | 10,618 (3,530 landslide), SMOTE inside CV folds |
| Test rows | 4,551 (1,513 landslide), never resampled |

## 3. Completed steps

| Step | Status | Result |
|---|---|---|
| 0 Environment, git, repo | ✅ | `verify_setup.py` READY |
| 1 Data sourcing | ✅ | DEM, rainfall, land cover, soil, roads, boundaries, GSI inventory, NDVI. Provenance in [data_sources_log.md](data_sources_log.md) |
| 2a to 2c Terrain, roads, streams, faults, TWI, rainfall, land cover, soil | ✅ | rasters on one grid |
| NDVI (Sentinel-2, Google Earth Engine) | ✅ | export v3 installed: full coverage, VIF 5.11 at the points. v1 and v2 each missed a strip of the state and were not used |
| All rasters aligned | ✅ | `check_layers`: **12 layers**, 11,123 x 10,135 cells, 30 m, EPSG:32644 |
| 2d GSI landslide points (`clean_gsi`) | ✅ | 5,201 in the state, **5,063** after removing repeat entries, shared-coordinate groups and coarse coordinates |
| 2e Stable points (`make_stable_points`) | ✅ | **10,126**, seed 42, 500 m from every GSI point and each other, 50 m clear of water; even spread across districts |
| 2f Raster extraction (`extract_points`) | ✅ | 15,189 points x 12 rasters; 22 problem rows, all landslides (20 on water, 2 on the border rim) |
| 2g `dataset.csv` (`label_categories`) | ✅ | 15,189 rows, 1:2, schema validated |
| 3 EDA | ✅ | run on real data; strongest separation dist_roads (r = -0.34), elevation (-0.29), slope (+0.29) |
| 4 Preprocessing | ✅ | rare classes merged (under 50 rows), **23 features**, VIF dropped none (highest elevation 6.47) |
| 5 SVM | ✅ | test AUC **0.9404** |
| 6 Random Forest | ✅ | test AUC **0.9604** |
| 7 Evaluation | ✅ | bootstrap gap interval, confusion matrices, ROC and precision-recall figures |
| 7b Near-road check (`near_road_check`) | ✅ | RF 0.934 and SVM 0.907 within 1 km of a road |
| 8 Dashboard | ✅ | four pages on the real models, browser-checked 17 September; synthetic banner gone; outdated text fixed |
| 9 Rudraprayag maps | ✅ | RF: High + Very High 7.5% of the district (25 s); SVM: 14.9% (11 min) |
| README | ✅ | rewritten with real results (`6378064`) |
| Decisions log | ✅ | [decisions.md](decisions.md), every step since 16 September |
| Data sources log | ✅ | GSI and NDVI rows complete |
| Evaluation report | ✅ | verdict states measured results only, with near-road AUCs (`6d525e0`) |
| Dashboard method text | ✅ | "How the pipeline works" follows the real order (`6d525e0`) |
| Literature review | ✅ | real results side by side with Chauhan et al. (2025), agreed wording, 11 factors / 23 inputs |
| Handoff | ✅ | `PROJECT_HANDOFF_V4.md` replaces V3 |
| Reproducibility | ✅ | `src/warp_ndvi.py` rebuilds `ndvi.tif` pixel for pixel; `make_stable_points` rerun gives identical points; `python run_phase2.py` runs the 14 Python steps (tested: dry run, skip logic, stop on failure, missing inputs) |

## 4. Dropped and merged

| Item | Decision |
|---|---|
| `dist_faults` | dropped 14 September: GEM misses the Main Central Thrust; tracks elevation (rank r 0.90) |
| `lithology` | dropped 16 September: Bhukosh unavailable. Chauhan et al. (2025) used GSI geology via Bhukosh; this study could not access it |
| TRI | never added: rank correlation 0.993 with slope, VIF 21.2 |
| Rare classes | merged into "Other": soil Chernozems, Podzols, Regosols, Vertisols; land cover Herbaceous wetland, Shrubland |
| NASA Global Landslide Catalog | not used for training (location accuracy); map overlay only |

## 5. Limitations to state in the report

- **Road-survey bias:** landslide points lie a median 30 m from a road, stable points 1,154 m. Quantified by the near-road check.
- **Random train/test split:** spatially close points fall on both sides, so scores are likely optimistic. Spatial cross-validation is future work.
- **Best parameters on the edge of the grid** (SVM C 100, RF 300 trees and min_samples_split 2). Stated as a limitation; grids were not widened after seeing the results.
- **Duplicates:** 20 landslide rows share a 30 m cell; 8 groups span train and test (at most 8 of 4,551 test rows). Not retrained.
- **No lithology;** distance to faults dropped.
- **NDVI overlaps land cover** (R2 0.78 at the points); some classes occur almost only at stable points (Snow and ice 856 / 0).
- **Stable means "no recorded landslide".**
- **Rainfall** is a 16-year annual mean at about 5.5 km.
- 58 kept GSI points have 2-decimal coordinates (about 1 km); 136 landslide points lie within 50 m of water, where stable points were not allowed.

## 6. Synthetic baseline (pipeline test, not findings)

The pipeline was built and tested on a synthetic dataset first (3,600 rows, 29 features including lithology). Final synthetic run on 14 September: SVM 0.8541, RF 0.8767, gap +0.0224 (+0.0082 to +0.0386). The same ranking held on real data. The synthetic models and metadata are kept locally in `models/synthetic_baseline_2026-09-14/` (not in git).

## 7. Pending

### Phase 2, still to do

| Item | Status |
|---|---|
| Phase 2 report document | not started; format to confirm with the college |
| Backups of the GSI zip, NDVI v3 and `dataset.csv` outside the laptop | user, manual |

### Phase 3

See section 9.

## 8. Housekeeping

- `data/processed/` holds about 4.3 GB, much of it intermediates; cleanup needs the user's go-ahead.
- `data/processed/dataset.csv` and `dataset_raw.csv` are untracked and not gitignored: never `git add .` on `main`.
- `outputs/figures/shap/`, `outputs/susceptibility_map_uk.html` and the `susceptibility_uk_*.tif` rasters are Phase 3 outputs: gitignored on `phase3-preparation`, untracked on `main`.

## 9. Phase 3 (branch `phase3-preparation`, not merged into `main`)

`main` was merged into the branch on 17 September (`c7eeb4e`), so Phase 3 runs on the real models; `main` itself is unchanged until Phase 2 is submitted. Details and numbers: [decisions.md](decisions.md), "Phase 3 results on the real models".

### Complete

| Item | Status | Result |
|---|---|---|
| Phase 2 audit (`verify_phase2.py`) | ✅ | 59 checks, 59 OK, 0 FAIL |
| Rudraprayag raster, real models (`predict_raster_full.py --district rudraprayag`) | ✅ | 23.5 s, peak 0.78 GB; identical to the Phase 2 RF map cell for cell |
| SHAP explainability (`explain_shap.py`) | ✅ | 500 test points in 78 s; ranking dist_roads, elevation, slope, ndvi (matches RF permutation top 4) |
| Full state raster (`predict_raster_full.py --state --yes`) | ✅ | 58,945,876 cells in 9.1 min, peak 0.80 GB; **High + Very High 7.8%** (4,099 km2) |
| State web map (`map_generator_full.py`) | ✅ | 6.99 MB; all 5,063 GSI points; browser-checked after marker, label, popup and title fixes |
| Dashboard v2, 6 pages (`streamlit run dashboard_v2/app.py`) | ✅ | every page checked on real data; Explainability caption corrected |
| `run_phase3.py` | ✅ | estimates updated to the real runs; XGBoost and three-model evaluation added as steps 0b and 0c; dry run shows every step up to date |
| **XGBoost (third model)** (`train_xgboost.py`) | ✅ | 114 s grid search; test AUC **0.9616** (CV 0.9629); minus RF +0.0012 (-0.0005 to +0.0030), **not separable**; minus SVM +0.0211 (+0.0170 to +0.0258). Within 1 km of a road 0.937 |

The state's 7.8% High + Very High is not comparable with Chauhan et al.'s 18.47%: fixed breaks (0.2 / 0.4 / 0.6 / 0.8) here, natural breaks recomputed per map there.

### Pending

| Item | Notes |
|---|---|
| Spatial cross-validation | measures how optimistic the random split is |
| Phase 3 report | not started |
| Merge `phase3-preparation` into `main` | only after Phase 2 is submitted |
| SVM state map (optional) | about 5 hours at 3,266 cells/s |
