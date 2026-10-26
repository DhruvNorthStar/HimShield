# Saved-model statewide inference

This optional local workflow creates new Uttarakhand SVM and XGBoost susceptibility products from the existing trained models. It does not train a model, update the held-out benchmark, replace a deployed model or modify the original RF map. Scores are relative model outputs, not calibrated landslide occurrence probabilities.

The writer is `src/statewide_inference.py`; the read-only dashboard consumer is `dashboard_v2/statewide_maps.py`. Both use the small path/input contract in `src/statewide_contract.py`. The Phase 2 dashboard and original producers are unchanged.

## Input and numerical contract

- Load the preserved `models/{rf,svm,xgb}_model.pkl`, scaler, 23 ordered feature names and preprocessing metadata. No spatial-validation fold weights are used.
- Verify inputs against the frozen benchmark inventory before scoring. Record the actual source, model, code, settings and environment fingerprints for each new run.
- Read the eleven active original factor rasters on the saved RF grid: elevation, slope, aspect, curvature, TWI, rainfall, NDVI, distance to roads, distance to streams, land cover and soil.
- Reuse `rows_for` and `prepare_for_prediction`, passing the original saved rare-category merges explicitly. Raw numeric preparation and scaled input remain float64. Soil code zero retains the original rock/ice category. Unretained categories retain the original reference/dummy behavior and are counted in receipts; no new encoding is fitted.
- Use the original positive-class score, cast to float32 before classifying with the unchanged breaks `[0.2, 0.4, 0.6, 0.8]`. Score NoData is `-9999`; class NoData is `0`. Class labels and colours remain unchanged.
- Recompute source readability, state pixel-centre membership and water exclusion for every inference window, and require exact agreement with the saved RF scored mask.

The reference grid is EPSG:32644 at 30 m: 10,134 rows by 11,123 columns, with 58,945,876 scored cells. A 30 m aligned grid does not make every source dataset natively 30 m or provide a site survey.

Some valid raster soil labels are not retained in the trained feature schema. The original encoding maps these to the all-zero/reference dummy representation. The new writer preserves that behavior and records category counts in private receipts; it does not learn a new category treatment. This remains a limitation when interpreting extrapolated terrain conditions.

## Pilot gate and resources

The pilot checks spread, bounded windows covering all five RF classes. It requires exact RF class reproduction and a maximum score difference no greater than `1e-7`, plus finite, in-range SVM/XGBoost outputs on the same transformed inputs. The completed pilot records observed timing, memory, input identities and grid geometry. A full run refuses a missing or stale pilot.

The default full run uses eight full-width rows per window, one worker, one native numerical thread and a 64 MiB GDAL cache. Between windows it checks a 600 MiB process-RSS ceiling, at least 128 MiB system memory available, and conservative free disk space. These are stop guards, not a reservation of memory. Keep the laptop plugged in and avoid concurrent heavy jobs. SVM scores every cell against its saved support vectors and can take several hours; a quick point prediction does not imply quick statewide inference.

## Explicit commands

These are scientific-output commands, not dashboard startup instructions. Run only for an approved new product when the corresponding final paths do not already exist. Keep the original saved artifact tree available and activate Conda so native DLL paths are inherited.

```powershell
conda activate landslide
$env:OMP_NUM_THREADS = '1'
$env:OPENBLAS_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
$env:NUMEXPR_NUM_THREADS = '1'
$env:LSM_EXPERIMENT_ID = 'statewide-models-v1'
Remove-Item Env:LSM_REBUILD -ErrorAction SilentlyContinue
Remove-Item Env:LSM_DATA_SOURCE -ErrorAction SilentlyContinue
python -m src.statewide_inference --pilot
python -m src.statewide_inference --model xgb
python -m src.statewide_inference --model svm
Remove-Item Env:LSM_EXPERIMENT_ID -ErrorAction SilentlyContinue
```

Check each command's exit status before running the next. Existing final outputs are protected; rerunning the pilot is not necessary after it has completed with matching provenance. There is no automatic benchmark overwrite or force option. Do not run the legacy training/evaluation pipeline to create these maps.

## Interruption and publication

Each attempt uses the existing artifact transaction guard. Compressed window arrays and JSON receipts are immutable, hashed, read back and validated inside retained private staging. A clean interruption leaves completed windows reusable. Resume explicitly with the same model and window settings, for example:

```powershell
conda activate landslide
$env:LSM_EXPERIMENT_ID = 'statewide-models-v1'
Remove-Item Env:LSM_REBUILD -ErrorAction SilentlyContinue
python -m src.statewide_inference --model svm --resume
Remove-Item Env:LSM_EXPERIMENT_ID -ErrorAction SilentlyContinue
```

Use the same activated environment and experiment selection as above. Resume rejects changed inputs, code, grid, configuration, bad chunks and conflicting window receipts. `--max-windows N` provides a deliberate bounded stop without publishing a partial map; the stop exits with code 2. A hard crash can leave `.writer.lock`; inspect its recorded process and attempt before recovery. Never automatically delete a lock or discard staging.

Only a complete set of windows is assembled. Full raster validation reads every output block, reconciles class counts, checks shape/CRS/transform/NoData/range/classification and requires the exact RF footprint. The original RF raster is read only. Publication uses no-clobber atomic file creation, with the completion manifest written last. Atomicity is per file: an interrupted publication is not a completed product and is not advertised by the dashboard.

Receipt timing separates summed model prediction calls from elapsed work through raster assembly. Its `total` field does not include the subsequent final read-back and publication checks; use the run log's observed start/end for end-to-end duration. Resume receipts retain scoring time from reused windows, while elapsed time describes the current attempt.

## Local product paths and display

| Product | Relative local directory | Final files |
| --- | --- | --- |
| SVM | `outputs/experiments/statewide-models-v1/rasters/svm/` | `probability.tif`, `zones.tif`, `receipt.json` |
| XGBoost | `outputs/experiments/statewide-models-v1/rasters/xgb/` | `probability.tif`, `zones.tif`, `receipt.json` |
| Shared provenance | `outputs/experiments/statewide-models-v1/` | `pilot.json`, `manifest.json`, retained private staging/checkpoints |

The dashboard exposes a new model only after the completion manifest, receipt, current input/code identities, raster hashes and headers agree. A filename or PASS label alone is insufficient. Integrity hashes are cached against file identity/change metadata to avoid hashing multi-GB inputs on every widget interaction; changed files invalidate availability.

Interactive new-model views embed only a bounded raster image over a basemap, rendered in memory. They do not export inventory points or official district vectors. Static/offline views use the existing saved-raster preview path. Display cells are reduced from the 30 m source grid; full-resolution statistics come from the validated product, not the display image. The existing RF HTML and dedicated Rudraprayag products retain their original behavior. The 13 official district views remain RF-only, local and subject to the separate [district requirements](local_district_views.md).

## Public distribution and recovery

All outputs, receipts, checkpoints and manifests in this experiment directory are ignored by Git. Do not force-add rasters, generated HTML, model weights, coordinate-bearing records or private official geometry. Public source code does not grant redistribution rights to its GIS inputs or generated maps. Restore authorized, verified inputs separately on another machine; missing products must produce accurate availability states rather than a substituted model map.

The original benchmark manifest is not rewritten to adopt these new files. Preserve its existing recovery copies, QGIS edits and real CSVs. New products can be left unavailable without changing original maps or predictions. Check new output hashes against their private receipts and verify the established benchmark separately with `python -m src.provenance verify --predictions`.

Run the full automated suite before a long inference job or after it finishes. The CLI regression guard snapshots the entire artifact tree, including experiment checkpoints; running that audit during active inference correctly notices those changing files and cannot establish a quiet-tree result. Do not relax the guard to hide concurrent writes.
