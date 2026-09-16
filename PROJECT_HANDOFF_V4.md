# PROJECT HANDOFF V4: Landslide Susceptibility Mapping for Uttarakhand

Written 17 September 2026 to move the work into a fresh Claude Code session. **Supersedes `PROJECT_HANDOFF_V3.md`** (16 September, written before any real-data work) and `PROJECT_HANDOFF.md` (14 September); both stay in the repo as history. Every number below was read from `models/metadata.json`, the logs or the files on 17 September. The reasons and measurements behind every decision are in `docs/decisions.md`: read it before changing anything.

## 0. Instructions for the new session (read before doing anything)

1. Read this file, then `docs/decisions.md`, `docs/PROJECT_STATUS.md` and `src/config.py`.
2. Run the commands in section 9 and report what they show. **Change nothing until the user says what to do next.**
3. **Phase 2 is complete on real data.** Do not retrain, widen grids or change sampling without the user asking. The user decided (17 September) that the grid-edge parameters and the 8 duplicate groups are stated limitations, not reasons to retrain: widening grids after seeing results is p-hacking.
4. **Never claim the models are better than Chauhan et al. (2025)** in any committed file, dashboard text or message meant for the report. Agreed wording: "AUCs comparable to Chauhan et al. (2025), with road-survey bias quantified (within 1 km of roads: RF 0.934, SVM 0.907)".
5. **Phase 2 / Phase 3 boundary.** Phase 3 (SHAP, full-state map, dashboard_v2) lives on branch `phase3-preparation`. Do not merge it unless the user asks. XGBoost is Phase 3 only. Spatial cross-validation is future work.
6. **Git:** work on `main`, commit, push after every commit, confirm with `git ls-remote origin refs/heads/main`. End every commit message with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`. Author `DhruvNorthStar <pandeydhruv92@gmail.com>` (chosen on purpose; the repo is public).
7. **Never commit data, models or licensed layers.** `data/processed/dataset.csv` and `dataset_raw.csv` are untracked **and not gitignored**, and the user decided they must not be committed: never `git add .` or `git commit -a`. `outputs/figures/shap/` and `outputs/susceptibility_map_uk.html` are untracked Phase 3 leftovers.
8. Never pull GSI data through the BhuSanket website proxy (decided 12 September).
9. How the user works: reason before code; one step at a time, report after each, wait when told to stop; honest reporting of results and of your own mistakes; one recommendation with its trade-off; confirm before anything irreversible or outside the request; flag contradictions in instructions before acting on them.

## 1. Snapshot

| | |
|---|---|
| Project | Landslide Susceptibility Mapping for Uttarakhand: SVM vs Random Forest. BCA final-year PBL, one person. The SVM vs RF comparison is the faculty requirement |
| Deadline | Final submission mid-October 2026 (no intermediate Phase 2 deadline; quality over speed) |
| Phase 2 | **Complete on real data**: GSI inventory, 12 aligned rasters with NDVI, full grid search, evaluation with near-road check, 4-page dashboard, both Rudraprayag maps, EDA, all docs. Only the report document is missing (section 8) |
| Phase 3 | Built on branch `phase3-preparation` against the synthetic models; not merged |
| Guide ("Sir") | Approved the project; was emailing GSI for extra data |
| Data source | `DEFAULT_DATA_SOURCE = "real"` in `src/config.py` |
| Local repo | `C:\Projects\landslide-uttarakhand` (outside OneDrive on purpose) |
| GitHub | https://github.com/DhruvNorthStar/HimShield (public, old repository name) |

### Git state (17 September, before this handoff's commit)

| Branch | Head | Pushed |
|---|---|---|
| `main` | `6d525e0 fix: evaluation verdict states measured results only` | yes |
| `phase3-preparation` | `f0a3fbc Add the Phase 3 master pipeline` | yes; 6 commits `main` lacks, and `main` has 20 the branch lacks (21 after this handoff) |

Real-data history on `main` (oldest first): `e19cb34` GSI in data log; `0584d1d`, `0ec6261` GSI cleaning; `29a8bf0` lithology dropped; `a9c9b43` stable points; `9951502`, `33767fe`, `be23c13` NDVI; `baf9c07` extraction; `6b9f9a9` rare-class merge and switch to real; `87f6cae` real ML results; `0ff60c1` demo map fix; `e3f3024` EDA; `b9d7727` dashboard text; `6378064` README; `54d994c` PROJECT_STATUS; `6d525e0` evaluation verdict; then the literature review and this handoff.

## 2. Results (real data)

Test set 4,551 points (1,513 landslides), 30% stratified, seed 42, never resampled.

| | SVM (RBF) | Random Forest |
|---|---|---|
| **Test AUC** | **0.9404** (95% 0.934 to 0.947) | **0.9604** (0.955 to 0.966) |
| 5-fold CV AUC | 0.9427 | 0.9618 |
| Average precision | 0.8814 | 0.9143 |
| Accuracy / precision / recall / F1 / specificity at 0.5 | 0.871 / 0.759 / 0.896 / 0.822 / 0.859 | 0.902 / 0.831 / 0.886 / 0.858 / 0.910 |
| Confusion at 0.5 (TN, FP, FN, TP) | 2,608, 430, 158, 1,355 | 2,766, 272, 172, 1,341 |
| Youden threshold | 0.52 | 0.52 |
| Best parameters | C 100, gamma 0.01 (edge of grid) | 300 trees (edge), max_depth None, min_samples_split 2 (edge) |
| Training time | 10 min 17 s (RBF 289 s, linear 277 s, refit 26 s) | 4 min 54 s |
| **AUC within 1 km of a road** (2,855 points, 1,440 landslides) | **0.907** | **0.934** |
| AUC beyond 1 km (1,696 points, 73 landslides) | 0.833 | 0.952 |

- RF minus SVM **+0.0199**, 95% bootstrap interval **+0.0157 to +0.0242**; within 1 km +0.027 (+0.020 to +0.035).
- Linear SVM test AUC 0.9265 (RBF +0.0139).
- RF importance, impurity / permutation: dist_roads 0.314 / +0.143, elevation 0.160 / +0.051, slope 0.117 / +0.042, ndvi 0.099 / +0.018, rainfall 0.058 / +0.008.
- EDA point-biserial r: dist_roads -0.34 (medians 30 m landslide vs 1,154 m stable), elevation -0.29, slope +0.29, dist_streams -0.21, rainfall +0.19, twi -0.12, ndvi +0.11, curvature -0.09, aspect -0.01.
- Rudraprayag maps (2,145,236 cells, fixed breaks 0.2/0.4/0.6/0.8): RF Very Low 69.1, Low 15.6, Moderate 7.7, High 4.3, Very High 3.2 % (25 s); SVM 65.8, 10.0, 9.3, 9.6, 5.3 % (661 s, 3,266 cells/s). State projection: RF about 11 min, SVM about 5 hours.
- Synthetic baseline (14 September, pipeline test only): SVM 0.8541, RF 0.8767, gap +0.0224. Kept locally in `models/synthetic_baseline_2026-09-14/`.
- Chauhan et al. (2025): RF 90.94%, XGBoost 91.36%, 7,182 GSI points from Bhukosh, 16 factors including geology. Side-by-side table in `docs/literature_review.md` section 2.1.

## 3. Data pipeline as built

| Step | Command | Result |
|---|---|---|
| 2d GSI points | `python -m src.clean_gsi` | `data/raw/landslides/GSI_Landslide_Inventory.shp.zip` (bharatlas.com geoportal, NDSAP, downloaded 15 Sep) -> 30,842 national -> 5,201 in state (spatial clip; STATE field gives 5,206) -> minus 2 repeat entries, 125 rows in 41 shared-coordinate groups of different landslides, 4 longitudes and 7 latitudes with 0 or 1 decimals -> **5,063** in `data/shapefiles/landslides.gpkg` (columns gsi_objectid, slide_no, landslide) |
| 2e Stable points | `python -m src.make_stable_points` | **10,126** in `non_landslides.gpkg`: uniform random, >= 500 m from all 6,144 GSI points near the state and from each other, 50 m clear of WorldCover water, every factor valid, seed 42 (reproducible, checked) |
| NDVI | Google Earth Engine, then `python -m src.warp_ndvi` | `COPERNICUS/S2_SR_HARMONIZED`, median 2023-10-01 to 2023-11-30, CLOUDY_PIXEL_PERCENTAGE < 15, scale 30 m, region [77.56, 28.71, 81.06, 31.47]. v1 missed 28.72 to 28.85 N, v2 missed 31.30 to 31.46 N; **v3** (`data/raw/ndvi/Uttarakhand_NDVI_2023_v3.tif`) covers the state and is warped bilinear to `data/processed/ndvi.tif` (NoData -9999) |
| 2f Extraction | `python -m src.extract_points` | 15,189 points x 12 rasters -> `data/shapefiles/all_points.gpkg`, `data/processed/dataset_raw.csv` (with point_id, x, y). 22 problem rows, all landslides: 20 on water, 2 on the NoData border rim (GSI-3492, GSI-3465) |
| 2g Dataset | `python -m src.label_categories data/processed/dataset_raw.csv` | `data/processed/dataset.csv`, 15,189 rows, 1:2 |
| 3 EDA | `python -m src.eda` | 9 s |
| 4 Preprocess | `python -m src.preprocess` | 20 water rows dropped, 2 rows median-filled, rare classes (< 50 rows) merged into Other, reference classes Cambisols / Tree cover, VIF dropped none (highest elevation 6.47, ndvi 5.08) -> **23 features**, train 10,618 / test 4,551 |
| 5, 6 Train | `python -m src.train_svm`, `python -m src.train_rf` | section 2 |
| 7 Evaluate | `python -m src.evaluate`, then `python -m src.near_road_check` | the verdict includes near-road AUCs only when they match the current models, so after retraining run evaluate, near_road_check, evaluate |
| 8 Dashboard | `streamlit run dashboard/app.py` | pages `/`, `/comparison`, `/predict`, `/map` |
| 9 Maps | `python -m src.demo_map` and `--model svm` | `outputs/demo_map_rudraprayag*.html` (gitignored), `data/processed/susceptibility_rudraprayag_{rf,svm}.tif` |

Rasters (all 11,123 x 10,135, 30 m, EPSG:32644, `check_layers` aligned): dem, slope, aspect, curvature, twi, rainfall, **ndvi**, dist_roads, dist_streams, dist_faults (not used), lulc, soil.

The 23 features in order: slope, elevation, curvature, twi, rainfall, ndvi, dist_roads, dist_streams, aspect_sin, aspect_cos, soil_type_Cryosols, soil_type_Fluvisols, soil_type_Leptosols, soil_type_Luvisols, soil_type_No soil (rock or ice), soil_type_Other, lulc_Bare/sparse vegetation, lulc_Built-up, lulc_Cropland, lulc_Grassland, lulc_Moss and lichen, lulc_Other, lulc_Snow and ice.

## 4. Decisions made since V3 (details and numbers in `docs/decisions.md`)

| Decision | Reason |
|---|---|
| GSI via bharatlas.com, NDSAP licence; NASA GLC overlay only | NASA locations 5 to 50 km off |
| Spatial clip over STATE field | the model samples where the point is |
| Drop whole shared-coordinate groups (keep 1 of the 2 true repeats) | 19 slides from 4 toposheets at one point: location unknown |
| Drop coordinates with 0 or 1 decimals (longitude and latitude) | about 10 km precision or worse |
| Stable points 500 m from every GSI point, including dropped ones; 500 m spacing; 50 m water buffer | conservative; follows the guide's Step 2e |
| Lithology dropped | no state geology layer; Bhukosh unavailable |
| NDVI added | VIF 5.11 at the points (under 10); overlaps land cover R2 0.78, stated |
| Synthetic NDVI noise 0.15 | matches the real overlap (R2 0.78, VIF 5.04); its own generator, other synthetic columns unchanged |
| Rare classes: row count < 50 into Other (rule only) | the user's first list merged classes by landslide count (label leak); the user chose the rule |
| Merge applied at prediction too (`prepare_for_prediction` reads it from metadata) | otherwise a merged class is scored as the reference class |
| CSVs not committed | public repo; `dataset_raw.csv` holds GSI coordinates |
| Grid-edge parameters, duplicates: limitations, no retraining | user decision 17 September |
| Road bias kept, measured with near-road check; sampling unchanged | user decision |
| Evaluation verdict states measured results only | the old "why RF wins" text was fixed prose, not measurement |

## 5. Limitations for the report

Road-survey bias (quantified); random split, spatial CV future work; grid-edge parameters; 20 duplicate landslide rows, 8 groups across train and test; no lithology, dist_faults dropped; NDVI overlaps land cover; classes almost only at stable points (Snow and ice 856 / 0, No soil 1,194 / 1, Cryosols 233 / 0, Fluvisols 256 / 0); stable = no recorded landslide; rainfall 16-year mean at 5.5 km; 58 GSI points at 2-decimal precision; 136 landslides within 50 m of water where stable points were not allowed; median fill computed before the split.

## 6. Environment

| Item | Value |
|---|---|
| Machine | Windows 11 Home, 7.8 GB RAM (often under 1 GB free; Edge and the Claude app use about 3 GB), 4-thread i3 |
| Conda | Miniforge `%USERPROFILE%\miniforge3`, env `landslide`, Python 3.11.16; shap and Phase 3 packages already installed |
| QGIS | 3.44.12 LTR, GRASS provider |
| Preview configs | `.claude/launch.json` (gitignored): `dashboard` (8501), `dashboard_v2` (8502), `maps` (http.server on `outputs/`, 8765) |

Known issues:
- Use `"$USERPROFILE/miniforge3/condabin/conda.bat" run -n landslide python -B ...`. For live logs of long runs add `--no-capture-output` and `PYTHONUNBUFFERED=1`, and run in the background.
- `conda run python -c` breaks on multi-line code: write a script to the session scratchpad. Scripts run from the scratchpad need `sys.path.insert(0, "C:/Projects/landslide-uttarakhand")`; use forward slashes in that path.
- Print ASCII only (GSI text fields crash cp1252 output): `sys.stdout.reconfigure(encoding="ascii", errors="backslashreplace")`.
- A threadpoolctl warning about Intel and LLVM OpenMP loaded together appears on every sklearn run; harmless so far.
- folium warns that CartoDB tiles need an API key; tested 17 September, the tiles still load.
- The in-app browser refuses `file://`; use the `maps` preview. Streamlit page slugs: `/comparison`, `/predict`, `/map`.
- Git warns "LF will be replaced by CRLF" on every commit; harmless (`.gitattributes`).
- Earth Engine exports: check the file's four edges against the state bounds (W 77.5723, S 28.7229, E 81.0453, N 31.4561) before warping.

## 7. Files

New scripts on `main` since V3: `src/clean_gsi.py`, `src/make_stable_points.py`, `src/extract_points.py`, `src/near_road_check.py`. Changed: `src/config.py` (ndvi, lithology dropped, rare-class settings, real), `src/preprocess.py` (rare-class merge), `src/make_synthetic.py` (ndvi), `src/check_layers.py`, `src/eda.py`, `src/demo_map.py`, `src/evaluate.py`, `dashboard/app.py`. New doc: `docs/decisions.md`. Rewritten: `README.md`, `docs/PROJECT_STATUS.md`; updated `docs/literature_review.md`, `docs/data_sources_log.md`, `docs/02_qgis_processing.md`.

Local only (not in git): `data/raw/` (including the GSI zip and NDVI v3, the hardest to replace; the user is backing them up), `data/processed/` (4.6 GB), `data/shapefiles/*.gpkg`, `models/` (real models plus `synthetic_baseline_2026-09-14/`), demo map HTML.

## 8. Pending

**Phase 2:**
1. The Phase 2 report document: not started. Ask the user for the college's format (Word, PDF, template) and whether they want a draft. Sources: README, `docs/decisions.md`, `docs/literature_review.md`, `docs/data_sources_log.md`, `docs/02_qgis_processing.md`, `outputs/*.txt`, `outputs/figures/`.
2. Backups of the GSI zip, NDVI v3 and `dataset.csv` (user, manual).

**Phase 3** (only when asked): merge `phase3-preparation` (recheck `verify_phase2.py`, `explain_shap.py`, `predict_raster_full.py`, `map_generator_full.py` and `dashboard_v2` against 23 features, NDVI, the rare-class merge and real metadata); full-state RF map (about 11 min, tiles); SHAP on the real RF; dashboard v2 (6 pages); XGBoost; spatial cross-validation.

**Housekeeping** (ask first): `data/processed/` intermediates; consider gitignoring the two dataset CSVs.

## 9. First commands for the new session

Run from `C:\Projects\landslide-uttarakhand` (Git Bash) and report:

```
"$USERPROFILE/miniforge3/condabin/conda.bat" run -n landslide python verify_setup.py
git status -sb && git log --oneline -5 && git ls-remote origin refs/heads/main refs/heads/phase3-preparation
"$USERPROFILE/miniforge3/condabin/conda.bat" run -n landslide python -m src.check_layers
"$USERPROFILE/miniforge3/condabin/conda.bat" run -n landslide python -B -c "import json; m=json.load(open('models/metadata.json')); e=m['evaluation']; print(m['data_source'], {k: v['auc'] for k, v in e['models'].items()}, e['auc_difference_rf_minus_svm'])"
```

Expect: READY; `main` equal to origin, untracked only the two dataset CSVs and the two Phase 3 leftovers; 12 layers aligned; `real {'SVM (RBF)': 0.9404, 'Random Forest': 0.9604} {'mean_difference': 0.0199, 'ci_low': 0.0157, 'ci_high': 0.0242, ...}`.
