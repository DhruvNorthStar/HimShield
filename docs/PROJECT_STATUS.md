# Project status

Last updated: 14 September 2026, end of the second session. Update this file whenever a decision is made or a dataset arrives. For a full briefing, see [PROJECT_HANDOFF.md](../PROJECT_HANDOFF.md).

## 1. Snapshot

| | |
|---|---|
| Project | Landslide Susceptibility Mapping for Uttarakhand: SVM vs Random Forest |
| Phase | 2 of 3. **Complete on synthetic data**: pipeline, dashboard and Rudraprayag demo map. The real-data run is pending the GSI landslide inventory |
| Deadline | **Monday 19 October 2026**: 25 working days from 13 September, with Gandhi Jayanti (2 October) a college holiday |
| Repo | https://github.com/DhruvNorthStar/HimShield (public; the repository keeps its original name), pushed after every commit |
| Local copy | `C:\Projects\landslide-uttarakhand` |
| Environment | conda env `landslide`, Python 3.11.16 |
| QGIS | 3.44.12 LTR, GRASS provider enabled |
| Data source in use | **synthetic**, until the real CSV exists |
| Complete on synthetic data | Steps 0, 0.5, 1, 3, 4, 5, 6, 7, **8 (dashboard)**, **9 (Rudraprayag demo map, RF and SVM)** |
| Done in QGIS | 2a, 2b, 2c (roads, streams, faults), land cover, soil, rainfall, plus `twi.tif`: **11 layers, all aligned** |
| Pending | lithology, landslide points, stable points, extraction; then rerun Steps 3 to 9 on real data |
| Team | one person |

## 2. Steps 8 and 9: complete on synthetic data

| Step | State |
|---|---|
| **8 Dashboard** | ✅ `streamlit run dashboard/app.py`, four pages: Overview, Model Comparison, Predict, Rudraprayag Map. Browser-tested on 14 September after the final retrain: every page loads, no server errors, the Predict page shows the TWI slider and no fault-distance slider. The homepage carries a **"SYNTHETIC DATA: RESULTS ARE NOT FINAL"** banner, every page a faint "SYNTHETIC DATA" watermark, and the other pages a warning strip; all three disappear automatically when the data source is switched to real |
| **9 Demo map, Random Forest** | ✅ `python -m src.demo_map`, built on the current models: 2,145,236 cells scored (6,105 water cells skipped) in 13.8 s, 19.5 s end to end. Zones: Very Low 61.9%, Low 29.9%, Moderate 7.1%, High 1.0%, Very High 0.0%. No input outside the training range except under 2% of cells. Whole state projected at about 6 min of scoring, and only in tiles (a single pass needs about 14 GB) |
| **9 Demo map, SVM** | ✅ `python -m src.demo_map --model svm`, rebuilt on the current models: 2,145,236 cells scored in 305.8 s (7,016 cells per second, about 22 times slower than RF), 311.6 s end to end. Zones: Very Low 77.8%, Low 15.8%, Moderate 5.0%, High 1.3%, Very High 0.1%; median score 0.076. **The earlier result, every cell at 0.000, is gone.** It was traced to `dist_faults` alone, which sat 13 to 30 standard deviations beyond the synthetic training data, and that column is now dropped. Whole state projected at about 141 min of scoring |

Both maps use Phyllite as lithology on every cell until a lithology layer exists, and both are synthetic: they test the pipeline and say nothing about Rudraprayag.

## 3. Current feature list: 29 features (`models/feature_names.json`)

In the order the models expect:

1. slope
2. elevation
3. curvature
4. twi
5. rainfall
6. dist_roads
7. dist_streams
8. aspect_sin
9. aspect_cos
10. soil_type_Fluvisols
11. soil_type_Glacier
12. soil_type_Leptosols
13. soil_type_Luvisols
14. soil_type_Regosols
15. lithology_Alluvium
16. lithology_Conglomerate
17. lithology_Gneiss
18. lithology_Granite
19. lithology_Limestone
20. lithology_Quartzite
21. lithology_Sandstone
22. lithology_Schist
23. lithology_Shale
24. lulc_Agriculture
25. lulc_Barren
26. lulc_Builtup
27. lulc_Grassland
28. lulc_Scrub
29. lulc_Snow

**Breakdown:** 7 numeric factors, aspect as sine and cosine, and one-hot columns for soil (5), lithology (9) and land cover (6).

**Reference classes:** each categorical factor leaves out its most frequent class, which is encoded as all zeros. In the synthetic data these are Cambisols, Phyllite and Forest.

**Not in the list:** `dist_faults` (dropped, section 5).

**With real data:** the category names come from WorldCover and SoilGrids, so the one-hot part of this list will change.

## 4. Current results (synthetic data, not findings about Uttarakhand)

Held-out test set: 1,079 points, 359 of them landslides, never resampled or used in tuning.

| | SVM (RBF) | Random Forest |
|---|---|---|
| **Test AUC** | **0.8541** | **0.8767** |
| CV AUC | 0.8678 | 0.8916 |
| Average precision | 0.7182 | 0.7704 |
| Recall at 0.5 | 0.752 (89 landslides missed) | 0.730 (97 missed) |
| Recall at the Youden threshold | 0.844 (threshold 0.38) | 0.905 (threshold 0.32) |
| Best parameters | C=10, gamma=0.01 | unlimited depth, 300 trees, min split 10 |

- **RF minus SVM AUC: +0.022**, bootstrap 95% interval **+0.008 to +0.039** (1,000 resamples; exact values +0.0224, +0.0082 to +0.0386). The interval excludes zero, so RF ranks better by more than test-set noise.
- **A split decision at 0.5:** SVM misses fewer landslides at that threshold, while RF catches more at each model's Youden threshold.
- **RBF beats a linear SVM kernel by +0.0126.**
- **VIF:** highest 3.29 (elevation), no feature dropped.
- **TWI:** ranks 6th of 29 in RF impurity importance and 7th by permutation.

How the synthetic results moved on 14 September:

| Run | Features | SVM test AUC | RF test AUC | RF minus SVM (95% interval) |
|---|---|---|---|---|
| Original | 29 | 0.8304 | 0.8682 | +0.0379 (+0.0234 to +0.0529) |
| TWI added | 30 | 0.8554 | 0.8827 | +0.0271 (+0.0137 to +0.0416) |
| dist_faults dropped | 29 | 0.8577 | 0.8862 | +0.0284 (+0.0140 to +0.0430) |
| Most frequent class as one-hot reference (**current**) | 29 | **0.8541** | **0.8767** | **+0.0224 (+0.0082 to +0.0386)** |

The last change moved RF by less than one standard error of AUC on this test set (about 0.012), and the grid search picked different RF settings, so read that shift as noise.

## 5. Feature decisions made on 14 September

| Decision | Evidence |
|---|---|
| **TWI added** (`twi`) | Topographic wetness index from `dem.tif`, GRASS `r.watershed`, multiple flow direction. Whole-state rank correlation with slope -0.51 and VIF 1.64 on its own; VIF 1.73 on the full real feature set. `check_layers` passes it: same 11,123 × 10,135 grid, 30 m, EPSG:32644, values 1.30 to 32.63, 0.12% NoData inside the state on the border rim. Used by Chauhan et al. (2025) |
| **TRI not added** | Rank correlation with slope 0.993 and VIF 21.2 across the state: at 30 m it is almost a copy of slope |
| **`dist_faults` dropped** through `DROPPED_COLUMNS` | See the next list. The raster and the CSV column are still produced; restore the column if GSI fault lines arrive from Bhukosh |
| **One-hot reference = most frequent class** of soil, lithology and land cover | The old rule left out the alphabetically first class. For land cover that is "Bare/sparse vegetation", 8.5% of the state, which pushed `lulc_Tree cover` to VIF 10.1 on the real grid. With Tree cover as the reference no land-cover column exceeds 4.7. On synthetic data the highest VIF fell from 5.65 to 3.29 |

**Why `dist_faults` was dropped** (VIF measured on a whole-state grid sample of 588,997 cells from the real rasters):
- **Elevation's VIF was 14.48**, above the threshold of 10.
- **`dist_faults` itself had a VIF of 8.87**, below the threshold. The drop was a judgement, not an automatic VIF result.
- Elevation and `dist_faults` have a rank correlation of **0.90**. Removing `dist_faults` brings elevation's VIF down to **7.82**.
- Step 4's automatic rule would have dropped **elevation**, a direct physical factor.
- The fault layer is the weak one:
  - GEM Global Active Faults holds only 8 faults within 50 km of the state and misses the Main Central Thrust.
  - Every Rudraprayag cell is **55.7 to 127.1 km** from a mapped fault (median 96.3 km).
  - Only 4.8% of the state lies within 5 km of a fault.
- Caveat: Step 4 computes VIF on sample points, not grid cells, so check again once `dataset.csv` exists.

## 6. Derived layers

All on one grid: 11,123 × 10,135 cells, 30 m, EPSG:32644.

| Layer | Range | Notes |
|---|---|---|
| dem | 184 to 7,800.55 m | Copernicus GLO-30 |
| slope | 0 to 80.16° | |
| aspect | -1 to 360 | 4,107,242 flat cells |
| curvature | -6.61 to 6.74 | profile curvature × 100 |
| twi | 1.30 to 32.63 | r.watershed topographic index, multiple flow direction; **added 14 September** |
| dist_roads | 0 to 100,360 m | 27,312 OSM segments, 10 km border margin |
| dist_streams | 0 to 111,522 m | r.watershed threshold 1,000 cells |
| dist_faults | 0 to 275,434 m | 8 GEM faults; **dropped from the models 14 September** (raster kept) |
| lulc | codes 10 to 100 | Mode resampling |
| soil | codes 0 to 29 | nearest neighbour; code 0 = no soil |
| rainfall | 390 to 2,520 mm over the grid, 506 to 2,519 inside the state | CHIRPS mean 2009 to 2024, bilinear |

## 7. Data status

| Factor | Status |
|---|---|
| DEM, boundary, land cover, soil, roads, rainfall, TWI | processed and verified |
| Faults | processed; dropped from the models (section 5) |
| **Landslide inventory** | **blocking.** Provisional NASA GLC: 205 points in the state, only 85 accurate to 5 km. The GSI inventory needs Bhukosh |
| Lithology | missing: needs Bhukosh |

## 8. Other work on 14 September

| Item | Result |
|---|---|
| `rainfall.tif` | ✅ verified: aligned; inside the state 506 to 2,519 mm, median 1,448 mm, no NoData; `rain_mean.tif` identical to an independent 2009 to 2024 mean |
| `check_layers` | ✅ all 11 layers aligned, nothing missing |
| `verify_setup.py` | ✅ READY, 0 warnings |
| Literature review | ✅ started: [literature_review.md](literature_review.md). Primary reference Chauhan, Gupta and Dixit (2025), *Geoenvironmental Disasters* 12:2, read in full text: 7,182 GSI points from Bhukosh, 16 factors at 30 m, stratified random 70/30 split, RF AUC 90.94%. Its tables still need checking in the PDF |
| Project title | Changed to "Landslide Susceptibility Mapping for Uttarakhand" in the dashboard and documents |
| Bhukosh | ⏳ user registering, and the project guide's letter to GSI going out |

## 9. Open issues

- **GSI landslide inventory**, the one blocker for real results. Decision on day 10 (Friday 25 September): GSI data, or hand-digitised Rudraprayag scars.
- **Lithology** may have to be dropped through `DROPPED_COLUMNS` if Bhukosh never delivers.
- **Random train/test split** ignores spatial autocorrelation, so scores are likely optimistic; stated in the evaluation report.
- **The `dem` layer in `uttarakhand.qgz`** still points at `dem.tif.vrt`; the user will repoint it in QGIS.
- **`data/processed/` holds about 3.8 GB**, much of it intermediates; cleanup needs the user's go-ahead.

## 10. Next steps

1. User: Bhukosh registration and the guide's letter to GSI.
2. Inventory decision on day 10, Friday 25 September.
3. Landslide points, stable points, extraction, export, `label_categories`.
4. Switch `DEFAULT_DATA_SOURCE` to real, rerun Steps 3 to 7, rebuild both demo maps, and re-check VIF on the real sample points.
