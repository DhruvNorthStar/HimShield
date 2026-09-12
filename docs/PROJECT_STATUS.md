# Project status

Last updated: 13 September 2026. Update this file whenever a decision is made or a dataset arrives.

## 1. Snapshot

| | |
|---|---|
| Project | Landslide susceptibility mapping, Uttarakhand: SVM vs Random Forest |
| Phase | 2 of 3, about 61 percent complete |
| Deadline | 25 working days from 13 September 2026, so roughly mid October |
| Repo | `C:\Projects\landslide-uttarakhand`, 15 commits on `main`, no remote yet |
| Environment | conda env `landslide`, Python 3.11.16 |
| QGIS | 3.44.12 LTR, GRASS provider enabled |
| Data source in use | **synthetic**, until the real CSV exists |
| Built | Steps 0, 0.5, 1, 3, 4, 5, 6, 7 |
| Done in QGIS | Steps 2a and 2b |
| Left | Steps 2c to 2g, 8, 9 |
| Team | one person |

Everything below runs end to end today:

```
conda activate landslide
python verify_setup.py          python -m src.check_dem       python -m src.check_layers
python -m src.make_synthetic    python -m src.eda             python -m src.preprocess
python -m src.train_svm         python -m src.train_rf        python -m src.evaluate
```

## 2. What is built

### Code, about 2,800 lines

| File | Lines | What it does |
|---|---|---|
| `src/config.py` | 179 | Every path, column name, seed, grid and artifact name |
| `src/make_synthetic.py` | 254 | The labelled synthetic dataset used until real data exists |
| `src/get_open_data.py` | 260 | Downloads no-account fallback data; builds boundary layers |
| `src/check_dem.py` | 148 | Validates DEM tiles before the mosaic |
| `src/check_layers.py` | 101 | Validates every derived raster against the dem.tif grid |
| `src/label_categories.py` | 149 | QGIS export to dataset.csv with the exact schema |
| `src/eda.py` | 362 | Step 3: reports, quality checks, five figures |
| `src/preprocess.py` | 262 | Step 4: missing values, encoding, VIF, split, scale, SMOTE |
| `src/train_svm.py` | 181 | Step 5: RBF grid search plus a linear kernel for comparison |
| `src/train_rf.py` | 151 | Step 6: grid search and two kinds of feature importance |
| `src/evaluate.py` | 336 | Step 7: metrics, three figures, bootstrap, written verdict |
| `src/viz.py` | 88 | Shared plot style, class colours, synthetic watermark |
| `src/artifacts.py` | 38 | Merges each step's section into metadata.json |
| `verify_setup.py` | 292 | Per-package OK/FAIL plus functional checks |

### Documents

`README.md` (176), `CONTRIBUTING.md` (104), `docs/01_data_sourcing.md` (284),
`docs/02_qgis_processing.md` (289), `docs/data_sources_log.md`, this file, and
`notebooks/01_eda.ipynb` (247).

### Artifacts produced

`models/`: `svm_model.pkl`, `rf_model.pkl`, `scaler.pkl`, `feature_names.json` (29 features),
`metadata.json` (every parameter, drop, score and timing).
`outputs/`: nine figures, `eda_report.txt`, `evaluation_report.txt`.

## 3. Results so far (synthetic data, so not findings about Uttarakhand)

| | SVM (RBF) | Random Forest |
|---|---|---|
| Best parameters | C=10, gamma=0.01 | depth 10, 300 trees, min split 2 |
| CV AUC | 0.8602 | 0.8896 |
| **Test AUC** | 0.8304 | **0.8682** |
| Average precision | 0.6694 | 0.7424 |
| Recall at 0.5 | 0.732 | 0.793 |
| Landslides missed | 96 of 358 | 74 of 358 |

Random Forest wins by 0.0379 AUC, with a bootstrap 95 percent interval of +0.0234 to +0.0529, so
the gap is larger than test-set noise. Inside the SVM, the RBF kernel beats a linear one by only
+0.0090, so the non-linearity argument is weak on this data and the verdict says so.

Preprocessing on the same data: 3,592 rows after dropping water, 29 features, no VIF drops
(highest 6.45), split 2,514 train and 1,078 test, SMOTE balanced training to 1,680/1,680 with the
test set untouched at 720/358.

## 4. Data status

| Factor | Status | Size |
|---|---|---|
| DEM | **have**, 14 Copernicus GLO-30 tiles, verified void free | 554 MB |
| Boundary | **have**, state and 13 districts in EPSG:32644 | 91 MB raw |
| Land cover | **have**, ESA WorldCover, 5 tiles | 451 MB |
| Soil | **have**, SoilGrids WRB, 6 classes present | 0.45 MB |
| Faults | **have but weak**: only 4 GEM lines cross the state | 10.6 MB |
| Landslide inventory | **provisional**: NASA GLC, 205 points in state, only 85 accurate to 5 km | 3.6 MB |
| Rainfall | missing: IMD yearly files, or the scripted CHIRPS fallback | 0.75 to 1.15 GB |
| Lithology | missing: needs Bhukosh, no usable open substitute | |
| Roads | missing: QuickOSM inside QGIS, part of Step 2c | small |
| SRTM (rejected) | archived with a note explaining why | 298 MB |

Derived in QGIS so far: `dem.tif` (11,123 x 10,135 at 30 m), `slope.tif`, `aspect.tif`,
`curvature.tif`, all verified on the same grid.

## 5. Problems found and fixed

Each of these is a viva answer, and most were invisible until something checked for them.

| Problem | How it showed up | Fix |
|---|---|---|
| SMOTE leaking inside cross-validation | SVM scored CV 0.9199 against test 0.6884 and chose the most overfit gamma | SMOTE moved inside each fold with an imblearn pipeline; CV and test now agree |
| Old `pip --user` numpy shadowing the env | Environment reported numpy 1.25 while conda had 2.2.6 | `PYTHONNOUSERSITE=1` on the env; `verify_setup.py` fails loudly if it recurs |
| SRTM voids and missing tiles | 766 km2 of the state had no elevation, 476 of it in Uttarkashi | switched to Copernicus GLO-30, void free |
| Step 2a saved as a VRT chain | `dem.tif.vrt` pointed back through three files to the raw tiles | converted to a real GeoTIFF, 138 MB; both docs and the checker now warn |
| Exact package pins unsolvable | shapely, rasterio and pyogrio need one shared GEOS build | minor-version pins plus `environment.lock.yml` |
| Accented state name | geoBoundaries writes "Uttarakhand" with a macron, so the lookup failed | accents folded before matching |
| GRASS aspect convention | GRASS counts anticlockwise from east, our schema wants compass bearings | conversion expression, documented in Step 2b |
| Water-class leak | every water point was a landslide, because Step 2e excludes water from stable points | those rows dropped in Step 4, with the reason recorded |
| Wrong OSM region assumed | Uttarakhand is in Geofabrik central-zone, not northern-zone | tested 10 towns against both zone outlines |

## 6. Decisions, and why

| # | Decision | Reason |
|---|---|---|
| 1 | Repo outside OneDrive | OneDrive locks `.git` files and syncs gigabytes of rasters |
| 2 | conda with Python 3.11 | one matched binary set for GDAL, GEOS and PROJ |
| 3 | Copernicus DEM, not SRTM | SRTM had 766 km2 of voids inside the state |
| 4 | EPSG:32644 statewide | metric grid; 0.1 percent scale error at the west edge beats a seam through the middle |
| 5 | 1:2 landslide to stable | 1:1 leaves SMOTE nothing to do; wider ratios dominate the problem |
| 6 | 500 m buffer when sampling stable points | ground beside a mapped landslide is not stable |
| 7 | SMOTE after the split and inside CV folds | anything else scores memorisation |
| 8 | Scale once for both models | required for SVM, harmless for RF, one pipeline to defend |
| 9 | Aspect as sine and cosine | it is circular: 359 and 1 degrees are neighbours |
| 10 | AUC as the headline metric | accuracy is near useless at a 1:2 balance |
| 11 | Synthetic data until the real CSV | lets Steps 3 to 8 be finished and tested now |
| 12 | Seed 42 everywhere | reproducibility |

## 7. What is left

**QGIS:** 2c (roads, streams, faults), then the other factor rasters, then 2d to 2g once the
inventory arrives. This is the bulk of the remaining work.

**Code:** Step 8 dashboard, Step 9 Rudraprayag demo map.

**Data:** the GSI inventory is the one blocker. Rainfall, lithology and roads are still to come,
and rainfall and roads both have working fallbacks.

**Then:** rerun everything on real data (hours, not days) and write the report.

## 8. The GSI inventory: what we found

BhuSanket shows the inventory in a map viewer with no download button. Behind it sits an ArcGIS
service holding 31,551 landslide points nationally, which answers "Token Required" when requested
directly. It is access controlled, and only the portal proxy can read it. We did not pull data
through that proxy: going around an access control is not defensible in a viva. The legitimate
routes are Bhukosh registration or a direct request to GSI.

## 9. Open questions

1. Bhukosh registration: not yet done. It is the only route to the real inventory.
2. Decision point on day 10, about 26 September: if there is no GSI data, digitise landslide scars
   for Rudraprayag by hand and scope Phase 2 to that district.
3. Survey of India boundary would be better than geoBoundaries for an Indian report, if obtainable.
