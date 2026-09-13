# Project status

Last updated: 14 September 2026. Update this file whenever a decision is made or a dataset arrives.

## 1. Snapshot

| | |
|---|---|
| Project | HimShield: landslide susceptibility mapping, Uttarakhand, SVM vs Random Forest |
| Phase | 2 of 3, about 70 percent complete |
| Deadline | 25 working days from 13 September 2026, so roughly mid October |
| Repo | https://github.com/DhruvNorthStar/HimShield (public), pushed after every commit |
| Local copy | `C:\Projects\landslide-uttarakhand` |
| Environment | conda env `landslide`, Python 3.11.16 |
| QGIS | 3.44.12 LTR, GRASS provider enabled |
| Data source in use | **synthetic**, until the real CSV exists |
| Built | Steps 0, 0.5, 1, 3, 4, 5, 6, 7 |
| Done in QGIS | 2a, 2b, 2c (roads, streams, faults), land cover and soil |
| Left | rainfall, lithology, landslide points, stable points, extraction; Steps 8 and 9 |
| Team | one person |

Everything below runs end to end today:

```
conda activate landslide
python verify_setup.py          python -m src.check_dem       python -m src.check_layers
python -m src.make_synthetic    python -m src.eda             python -m src.preprocess
python -m src.train_svm         python -m src.train_rf        python -m src.evaluate
```

## 2. What is built

### Code

| File | What it does |
|---|---|
| `src/config.py` | Every path, column name, seed, grid and artifact name |
| `src/make_synthetic.py` | The labelled synthetic dataset used until real data exists |
| `src/get_open_data.py` | No-account downloads: boundary, DEM, land cover, soil, rainfall, faults, tiled OSM roads |
| `src/check_dem.py` | Validates DEM tiles before the mosaic |
| `src/check_layers.py` | Validates every derived raster against the dem.tif grid, and fails constant or mostly-zero distance layers |
| `src/label_categories.py` | QGIS export to dataset.csv with the exact schema; labels soil code 0 as No soil (rock or ice) |
| `src/eda.py` | Step 3: reports, quality checks, five figures |
| `src/preprocess.py` | Step 4: missing values, encoding, VIF, split, scale, SMOTE |
| `src/train_svm.py` | Step 5: RBF grid search plus a linear kernel, SMOTE inside each CV fold |
| `src/train_rf.py` | Step 6: grid search, impurity and permutation importance |
| `src/evaluate.py` | Step 7: metrics, three figures, bootstrap comparison, written verdict |
| `src/viz.py`, `src/artifacts.py` | Shared plot style and watermark; metadata merging |
| `verify_setup.py` | Per-package OK/FAIL plus functional checks |

### Documents

`README.md`, `CONTRIBUTING.md`, `docs/01_data_sourcing.md`, `docs/02_qgis_processing.md` (every
QGIS step rehearsed on real data before it was written), `docs/data_sources_log.md`, this file,
`notebooks/01_eda.ipynb`, and the QGIS project `uttarakhand.qgz`.

## 3. Derived layers, verified 14 September 2026

All on one grid: 11,123 x 10,135 cells, 30 m, EPSG:32644. `python -m src.check_layers` passes.

| Layer | Range | Notes |
|---|---|---|
| dem | 184 to 7,800.55 m | Copernicus GLO-30 |
| slope | 0 to 80.16 degrees | |
| aspect | -1 to 360 | 4,107,242 flat cells (-1) |
| curvature | -6.61 to 6.74 | profile curvature x 100 |
| dist_roads | 0 to 100,360 m | 27,312 OSM segments, 45,736 km, 10 km margin past the border |
| dist_streams | 0 to 111,522 m | r.watershed, threshold 1,000 cells (0.9 km2) |
| dist_faults | 0 to 275,434 m | 8 GEM faults within 50 km; weak factor, see section 5 |
| lulc | codes 10 to 100 | Mode resampling; tree cover 53.8%, grassland 17.3%, snow and ice 7.8%, water 0.57% |
| soil | codes 0 to 29 | nearest neighbour; Cambisols 45.4%, Luvisols 21.1%, Leptosols 17.4%, no soil 11.3% |

## 4. Results so far (synthetic data, so not findings about Uttarakhand)

| | SVM (RBF) | Random Forest |
|---|---|---|
| Best parameters | C=10, gamma=0.01 | depth 10, 300 trees, min split 2 |
| CV AUC | 0.8602 | 0.8896 |
| **Test AUC** | 0.8304 | **0.8682** |
| Recall at 0.5 | 0.732 | 0.793 |
| Landslides missed | 96 of 358 | 74 of 358 |

Random Forest wins by 0.0379 AUC, bootstrap 95 percent interval +0.0234 to +0.0529. Inside the SVM,
the RBF kernel beats a linear one by only +0.0090.

## 5. Data status

| Factor | Status |
|---|---|
| DEM, boundary, land cover, soil, roads | **have**, processed and verified |
| Faults | **have but weak**: only 4.8% of the state lies within 5 km of a fault, 61% lies beyond 50 km. Replace with GSI structural lines if possible; if it ranks suspiciously high on real data, drop it |
| Landslide inventory | **provisional**: NASA GLC, 205 points in state, only 85 accurate to 5 km. The GSI inventory needs Bhukosh |
| Rainfall | missing: IMD yearly files, or `python -m src.get_open_data rainfall` (CHIRPS) |
| Lithology | missing: needs Bhukosh, no usable open substitute |

## 6. Problems found and fixed

| Problem | How it showed up | Fix |
|---|---|---|
| SMOTE leaking inside cross-validation | SVM CV 0.9199 against test 0.6884 | SMOTE moved inside each fold |
| `dist_streams` 0 in all 112.7 million cells | proximity run with no target value, so NoData counted as stream | rerun with target value 1 |
| `check_layers` passed that all-zero raster | 0 to 0 sits inside a legal range | now fails constant and mostly-zero distance layers |
| `check_layers` would fail a correct `dist_faults` | grid corners are 275 km from any fault, limit was 200 km | limit raised to 500 km, above the 452 km grid diagonal |
| Soil code 0 read as Acrisols | 11.3% of the state, median elevation 5,224 m | labelled No soil (rock or ice) |
| GEM faults broke on reprojection | 30 of 13,696 global faults got infinite coordinates | clip in latitude/longitude first |
| A fold listed among faults | one anticline inside the 50 km area | removed before rasterising |
| QuickOSM timed out | 61,260 road segments in one request | tiled, resumable Overpass download |
| SRTM voids and missing tiles | 766 km2 of the state with no elevation | switched to Copernicus GLO-30 |
| Step 2a saved as a VRT chain | `dem.tif.vrt` walked back to the raw tiles | converted to a real GeoTIFF |
| Old `pip --user` numpy shadowing the env | numpy 1.25 loaded instead of 2.2.6 | `PYTHONNOUSERSITE=1` |
| Accented state name | geoBoundaries writes Uttarakhand with a macron | accents folded before matching |
| GRASS aspect convention | anticlockwise from east | conversion expression in Step 2b |
| Water-class leak | every water point was a landslide | water rows dropped in Step 4 |

## 7. Decisions, and why

| Decision | Reason |
|---|---|
| Copernicus DEM, not SRTM | SRTM had 766 km2 of voids inside the state |
| EPSG:32644 statewide | metric grid; 0.1 percent scale error at the west edge beats a seam |
| 1:2 landslide to stable, 500 m buffer | 1:1 leaves SMOTE nothing to do; ground beside a landslide is not stable |
| SMOTE after the split and inside CV folds | anything else scores memorisation |
| Aspect as sine and cosine | it is circular |
| AUC as the headline metric | accuracy is near useless at a 1:2 balance |
| Roads with a 10 km border margin | a border point may be nearest a road in Nepal or Himachal |
| Stream threshold 1,000 cells | 0.9 km2 of catchment before a channel starts |
| Faults within 50 km, folds removed | faults are sparse; the nearest to eastern Pithoragarh is in Nepal |
| Mode for land cover, nearest for soil | Mode when shrinking 10 m to 30 m, nearest when enlarging 250 m to 30 m; never average class codes |
| Soil code 0 as its own class | marking it missing would let Step 4 call glaciers Cambisols |
| Synthetic data until the real CSV | Steps 3 to 8 finished and tested early |

## 8. Next steps

1. Register on **Bhukosh**. It is the only route to the real inventory and to lithology.
2. Rainfall raster: CHIRPS via the script, or IMD yearly files.
3. Landslide points and stable-point sampling, once an inventory is in hand.
4. Extraction and export to `dataset.csv`, then switch config to real data and rerun Steps 3 to 7.
5. Step 8 dashboard and Step 9 Rudraprayag demo map.

Decision point around 26 September: without GSI data, digitise landslide scars for Rudraprayag by hand
and scope Phase 2 to that district.
