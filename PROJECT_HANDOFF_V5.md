# PROJECT HANDOFF V5: Landslide Susceptibility Mapping for Uttarakhand

Written 17 September 2026 and updated 18 September (scheme 4 theme, XGBoost), on branch `phase3-preparation`. **Supersedes V4 for the current state.** V4
(`PROJECT_HANDOFF_V4.md`) stays the full reference for Phase 2: results, data pipeline, decisions, limitations,
environment and Windows quirks. This file adds what changed after V4: the Phase 3 run on the real models. Every
number was read from the logs, `models/metadata.json` or `outputs/figures/shap/shap_summary.json`. Reasons and
measurements: `docs/decisions.md`.

## 0. Instructions for the new session

1. Read this file, then V4 sections 0 to 6, then `docs/decisions.md` (last two sections) and `docs/PROJECT_STATUS.md`.
2. Run the commands in section 5 and report. **Change nothing until the user says what to do next.**
3. All V4 rules still hold: no retraining or grid widening without the user asking; never claim better accuracy
   than Chauhan et al. (2025) (agreed wording: "AUCs comparable to Chauhan et al. (2025), with road-survey bias
   quantified (within 1 km of roads: RF 0.934, SVM 0.907)"); never commit data, models or the dataset CSVs; push
   after every commit; end commit messages with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
4. **Branches.** `main` holds Phase 2 only and **must not change until Phase 2 is submitted**. Phase 3 work happens
   on `phase3-preparation`. Merging `main` into the branch is allowed (done once, `c7eeb4e`); merging the branch
   into `main` is not, until the user says so.
5. Do not describe the state map's 7.8% High + Very High as different terrain from Chauhan et al.'s 18.47%: the
   zoning rules differ (fixed breaks here, natural breaks there).

## 1. Snapshot

| | |
|---|---|
| Phase 2 | Complete on real data, on `main` at `720caf8`: RF test AUC 0.9604, SVM 0.9404, gap +0.0199 (+0.0157 to +0.0242), 23 features, 15,169 rows, `run_phase2.py` reproduces everything byte for byte. Report document not written yet |
| Phase 3 | Complete on real data on `phase3-preparation`: audit, Rudraprayag raster, SHAP, full state raster, state web map, dashboard v2, scheme 4 theme, XGBoost as a third model (test AUC 0.9616; minus RF +0.0012, -0.0005 to +0.0030, not separable). **Phase 3 is complete** |
| Pending | Spatial cross-validation, Phase 3 report, Phase 2 report, merge into `main` after Phase 2 submission (Commit A `a174f61` of the theme is the Phase 2 part to carry over) |
| Deadline | Final submission mid-October 2026 |

Branch history after V4: `c7eeb4e` merge of `main` into the branch; `481fdbe` state map markers, labels, popups,
title; then the Phase 3 completion commit (dashboard v2 caption, verify code check, run_phase3 estimates, docs,
this file).

## 2. Phase 3 results

| Step | Command | Result |
|---|---|---|
| Audit | `python src/verify_phase2.py` | 59 OK, 0 WARN, 0 FAIL (now also parses `dashboard_v2/app.py`, `run_phase2.py`, `run_phase3.py`) |
| Rudraprayag raster | `python src/predict_raster_full.py --district rudraprayag` | 2,145,236 cells, 23.5 s, peak 0.78 GB; identical to the Phase 2 RF map cell for cell (max difference 0.0) |
| SHAP | `python src/explain_shap.py` | 500 held-out test points (cap in the script), 78 s (real forest 57 MB, about 4x the synthetic 19 s). Mean abs SHAP: dist_roads 0.192, elevation 0.100, slope 0.091, ndvi 0.054, dist_streams 0.035, rainfall 0.029. Top 4 match RF permutation importance; 5 and 6 swap |
| State raster | `python src/predict_raster_full.py --state --yes` | 58,945,876 cells scored (334,365 water skipped), 548 s, peak 0.80 GB. Very Low 71.1, Low 13.8, Moderate 7.4, High 4.7, Very High 3.1 %; **High + Very High 7.8% (4,099 km2)**. `susceptibility_uk_probability.tif` 150.7 MB, `_zones.tif` 5.9 MB |
| State web map | `python src/map_generator_full.py` | `outputs/susceptibility_map_uk.html` 6.99 MB: zones at about 90 m, districts, 5,063 GSI points (radius 4, navy `#0d1b2a` with a white outline), popups "GSI record / Slide / District", page title. Browser-checked |
| Dashboard v2 | `streamlit run dashboard_v2/app.py` (port 8502 in `.claude/launch.json`) | 6 pages: `/`, `/comparison`, `/predict`, `/map`, `/explainability`, `/state-map`; all checked on real data, no errors, no synthetic-era wording |
| Orchestrator | `python run_phase3.py --dry-run` | verify always runs; SHAP, state raster and web map skip as up to date |

All outputs are gitignored: `data/processed/susceptibility_*`, `outputs/figures/shap/`, `outputs/susceptibility_map_uk.html`.

**XGBoost (18 September):** `python -m src.train_xgboost`, test AUC 0.9616 (CV 0.9629), 100 trees, depth 5, learning rate 0.1, subsample 0.8, 114 s. Minus RF +0.0012 (-0.0005 to +0.0030), not separable; minus SVM +0.0211, separable. Report the two tree ensembles as performing alike. Purple `#6a1b9a`, dotted. Details in `docs/decisions.md`.

## 3. Things to know

- **Colours (scheme 4, 18 September):** zones light to dark `#d4edda`, `#a1d99b`, `#fd8d3c`, `#e31a1c`, `#67000d`
  (lightness steps at least 10 L*, colour-blind separation at least 19); models RF `#1565c0` solid, SVM `#dc3545`
  dashed, XGBoost `#6a1b9a` dotted; state map markers navy. Light basemap is Esri World Light Gray (CartoDB now
  needs an API key).
- **SHAP beeswarm:** dist_roads is very skewed, so almost every dot is coloured "low"; use
  `shap_dependence_1_dist_roads.png` for the road effect.
- **Streamlit 404s:** opening a page URL directly (for example `/state-map`) logs 404s for `<page>/_stcore/health`
  before Streamlit retries at the root; harmless.
- **Browser checks:** open the web map through the `maps` preview (port 8765); the in-app browser refuses
  `file://`. In a very narrow window the map starts zoomed out; at normal width it fits the state.
- **Timings on the project laptop:** SVM state map would take about 5 hours (3,266 cells/s); not run.

## 4. Pending

1. Spatial cross-validation (future work in Phase 2; candidate for Phase 3).
2. Phase 3 report, and the Phase 2 report (format to confirm with the college).
3. Merge `phase3-preparation` into `main`, only after Phase 2 is submitted; then run `python src/verify_phase2.py`
   and `python run_phase3.py --dry-run` on `main`.
4. From V4: check Chauhan et al. tables and citations against the PDF; user backups; offline screenshots.

## 5. First commands for the new session

```
git status -sb && git branch --show-current && git log --oneline -3 phase3-preparation && git log --oneline -1 main
git ls-remote origin refs/heads/main refs/heads/phase3-preparation
"$USERPROFILE/miniforge3/condabin/conda.bat" run -n landslide python -B src/verify_phase2.py
"$USERPROFILE/miniforge3/condabin/conda.bat" run -n landslide python -B run_phase3.py --dry-run
```

Expect: on `phase3-preparation`, clean apart from the two untracked dataset CSVs; `main` at `720caf8` locally and
on GitHub; the audit 59 OK, 0 FAIL; the dry run with verify RUN and XGBoost, the three-model evaluation, SHAP, state raster and web map SKIP.
