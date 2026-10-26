# Architecture, provenance and scientific workflow

## Existing components

```text
Trusted CSV + saved metadata/scaler/feature order
    -> preserved SVM / RF / XGBoost
    -> manual assessment and original held-out benchmark

Saved evaluation metadata/reports/figures -> benchmark pages
Saved RF SHAP summary + six figures      -> explainability
Saved statewide RF / dedicated RF-SVM rasters + HTML
    -> existing map modes and in-memory static fallback
Preserved GIS factors + saved SVM/XGBoost + original transform
    -> explicit isolated inference -> private validated statewide rasters
    -> read-only completed-product gate -> Explorer
Private 2025 ABDB + saved statewide RF class raster
    -> bounded cell-centre masks/counts + private image previews
```

`src/config.py` defines benchmark paths/settings. `src/artifacts.py` guards writes; `src/provenance.py` inventories artifacts/content dependencies. The two orchestrators use fingerprints rather than timestamp-only freshness. Missing/stale benchmarks are blocked, not silently regenerated.

`dashboard_v2/app.py` registers six native Streamlit pages. It reuses Phase 2 loaders/transforms by excluding `dashboard/app.py`'s final bare `main()` call without rewriting that file. `ui.py` scopes navy/teal styling and green navigation; `benchmark_pages.py`, `assessment.py`, `explainability.py`, `explorer.py`, `district_views.py`, `image_map.py` separate presentation responsibilities. `statewide_maps.py` verifies and displays additional completed products without loading an estimator or running inference. [Dashboard design](dashboard_design.md) documents routes/components.

Existing models/data and map assets are cached. Official geometry/counts/previews use bounded single-worker processing. The first district coverage scan is deferred until requested or a derived district opens. HTML caching avoids repeated disk reads but not browser payload costs. Launching the app does not train, compute new SHAP or publish new rasters.

`src/statewide_inference.py` is a separate explicit writer, not a dashboard callback or a replacement legacy pipeline. It reuses the original raster-to-row and saved preprocessing functions, requires an RF-reproducing pilot, retains immutable window checkpoints and publishes only complete validated products through the existing experiment guard. `src/statewide_contract.py` shares lightweight input/path definitions with the consumer. All new rasters and receipts stay in ignored `outputs/experiments/statewide-models-v1/`; no source GIS copy or benchmark-manifest rewrite is needed. See [generation and provenance](statewide_inference.md).

## Benchmark contract and original method

Saved models: `models/svm_model.pkl`, `models/rf_model.pkl`, `models/xgb_model.pkl`. Shared preprocessing: `models/scaler.pkl`, `models/feature_names.json`, `models/metadata.json`. `data/processed/prepared.joblib` preserves split IDs/labels/matrices; `data/processed/dataset.csv` provides manual presets/context. All models use the same ordered 23 encoded features. [Artifact protection](artifact_protection.md) explains the 216-entry inventory and identities.

The original eleven conditioning factors are:

| Input | Meaning / existing unit |
| --- | --- |
| `slope` | Terrain slope, degrees |
| `aspect` | Direction from north, degrees; −1 for flat terrain |
| `elevation` | Metres above sea level |
| `curvature` | Profile curvature, original unit 1/100 m |
| `twi` | Topographic wetness index, ln(a / tan slope) |
| `rainfall` | Mean annual rainfall, mm/year |
| `ndvi` | Vegetation index, −1 to 1 |
| `dist_roads` | Distance to mapped road, metres |
| `dist_streams` | Distance to derived stream, metres |
| `soil_type` | Original SoilGrids category name |
| `lulc` | Original WorldCover category name |

The target `landslide` is 1 for recorded GSI positives and 0 for sampled negatives; it is not an input. Coordinate/event IDs never enter model predictors. Excluded `lithology`/`dist_faults` remain documented in `src/config.py`. Original category groups below 50 rows are merged into Other; Cambisols and Tree cover are the saved reference classes. The existing feature JSON and metadata, rather than a manually invented encoding, govern prediction.

Original preparation removes 20 water rows from 15,189, fills missing values, merges rare categories, encodes aspect/one-hot classes and performs VIF analysis before splitting. Flat aspect becomes (0,0). The seed-42 stratified 70/30 split leaves 4,551 test rows; scaling fits outer training only. Original tuning uses five-fold stratified ROC-AUC grids with SMOTE on training folds only. Global category/imputation/VIF choices and reused outer-training scaling limit leakage independence. These are preserved limitations, not changes to methodology.

Results/retrospective thresholds come from saved metadata. Test-selected Youden thresholds are not independent deployment validation. RF/XGBoost's conditional random-test AUC-gap interval includes zero, without establishing equivalence or superiority. Manual scores are relative susceptibility outputs, not calibrated event probabilities.

## Sources and limitations

| Component | Provenance and interpretation |
| --- | --- |
| Positives | GSI inventory through bharatlas; 5,063 retained points; road-survey/coordinate limitations |
| Negatives | 10,126 seed-42 pseudo-absence points; original 500 m separation/water exclusion; no record is not proven stable |
| Terrain/streams | Copernicus GLO-30 and derived terrain/stream distances, EPSG:32644 grid |
| Rainfall | CHIRPS 2009–2024 mean, native roughly 5.5 km, not triggers/fine-scale new information |
| Vegetation | Sentinel-2 L2A Oct–Nov 2023 median via Earth Engine, original scene-cloud filtering |
| Land cover/soil | ESA WorldCover 2021 and SoilGrids WRB; original category mappings |
| Roads | OpenStreetMap; may encode survey bias as well as model association |
| Original map boundaries | Earlier geoBoundaries inputs and preserved footprints |
| Optional districts | Same-release local Survey of India 2025 ABDB; does not replace benchmark boundaries |

Dates, rejected inputs, source-specific licences and attribution are in [data sources](data_sources_log.md), [decisions](decisions.md) and [local districts](local_district_views.md). A provenance log is not blanket redistribution permission. NASA GLC is provisional overlay/fallback, not the training inventory. Lithology was unavailable; faults were excluded for missing key structures. Repeated cells, coarse coordinates, road concentration and class-dependent exclusions limit unseen-region claims.

## SHAP and map semantics

The saved RF SHAP summary records TreeExplainer, `tree_path_dependent`, no external background sample, seed 42 and 500 test points (166 landslide, 334 stable). The class-1 baseline is 0.499661 in model-output space. Contributions reconstruct the recorded model score, not regional event prevalence. Six saved SHAP figures and RF/XGBoost importance are separate products; no XGBoost SHAP or new assessment-specific explanation is implied.

The five fixed classes use breaks 0.2/0.4/0.6/0.8: Very Low, Low, Moderate, High, Very High. Equality enters the next interval; 1.0 stays Very High. Colours remain `#d4edda`, `#a1d99b`, `#fd8d3c`, `#e31a1c`, `#67000d`. Statewide 30 m source versus approximately 90 m web cells are distinct. Dedicated Rudraprayag and official-mask RF products have different footprints and legitimate count differences.

Official masks use original pixel centres (`all_touched=False`) in bounded 128-row strips, without arbitrary assignment, hole filling or NoData interpolation. Counts reconcile: 58,839,256 assigned + 106,620 unassigned = 58,945,876 scored statewide cells. Official-state NoData within the raster is 506,492; double assignments/state-centre gaps are zero. Outside-raster polygon area is separately labelled.

Official coordinates stay server-side. In-memory PNGs carry navy outlines; separate unstyled images preserve class inspection. Previews sample existing classes at a labelled spacing with maximum side 1,000 pixels, not a site survey. Matching private inputs and loopback sessions are mandatory. Image-only design does not authorize public redistribution.

## Separate spatial infrastructure

The unchanged [protocol](spatial_validation_protocol.md) and `configs/spatialcv-10km-buffer2km-v1.json` specify five outer spatial folds, 10 km blocks, 2 km exclusions around test locations/block extents, cell-centre/event grouping and three spatial inner folds. All models share memberships; learned preprocessing, encoding/VIF/scaling and SMOTE are fold-contained. Thresholds use training-side inner OOF predictions.

The random-group control deliberately has zero outer buffer and the same buffered spatial inner-fold policy. Do not claim its outer folds satisfy the spatial protocol's 2 km guarantee. Resources are supervised conservatively/serially; results remain under `outputs/experiments/spatialcv-10km-buffer2km-v1/`, separate from benchmarks.

**Returned spatial/control results are now independently verified.** [Verified results](spatial_validation_results.md) describe the separate nested experiment and its limitations. `artifacts/spatial_validation_results.json` holds aggregate-only fold statistics with a pinned checksum; `dashboard_v2/spatial_results.py` validates the checksum, frozen config and statistics before rendering. Full models/coordinates/row records remain in the private external review. The original deployment models, raster/SHAP products and frozen protocol remain unchanged; no training or calibration is run during integration.
